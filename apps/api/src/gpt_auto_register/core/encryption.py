import base64
import hashlib
import hmac
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator

from gpt_auto_register.core.config import get_settings

PREFIX = "enc:v1:"
SETTING_KEY = "__encrypted_v1__"
KEY_VERIFIER = "gpt-auto-register-master-key-v1"


class MasterKeyError(RuntimeError):
    pass


@lru_cache
def master_key() -> bytes:
    settings = get_settings()
    settings.ensure_runtime_directories()
    path = settings.resolved_master_key_file
    if path.exists():
        encoded = path.read_bytes().strip()
        if len(encoded) == 32:
            path.chmod(0o600)
            return encoded
        try:
            value = base64.urlsafe_b64decode(encoded)
        except Exception as error:
            raise MasterKeyError(f"invalid master key file: {path}") from error
        if len(value) != 32:
            raise MasterKeyError(f"master key must contain exactly 32 bytes: {path}")
        path.chmod(0o600)
        return value
    value = os.urandom(32)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(base64.urlsafe_b64encode(value))
    except FileExistsError:
        master_key.cache_clear()
        return master_key()
    return value


def encrypt_text(value: str) -> str:
    if value.startswith(PREFIX):
        return value
    nonce = os.urandom(12)
    encrypted = AESGCM(master_key()).encrypt(nonce, value.encode("utf-8"), PREFIX.encode())
    payload = base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")
    return PREFIX + payload


def decrypt_text(value: str) -> str:
    if not value.startswith(PREFIX):
        raise MasterKeyError("sensitive database value is not encrypted")
    try:
        payload = base64.urlsafe_b64decode(value.removeprefix(PREFIX))
        decrypted = AESGCM(master_key()).decrypt(payload[:12], payload[12:], PREFIX.encode())
    except (InvalidTag, ValueError) as error:
        raise MasterKeyError("master key does not match encrypted database values") from error
    return decrypted.decode("utf-8")


def secret_fingerprint(value: str) -> str:
    key = hmac.new(master_key(), b"fingerprint-v1", hashlib.sha256).digest()
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def protect_setting(value: dict[str, Any]) -> dict[str, str]:
    return {SETTING_KEY: encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))}


def reveal_setting(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get(SETTING_KEY), str):
        raise MasterKeyError("sensitive setting is not encrypted")
    decoded = json.loads(decrypt_text(value[SETTING_KEY]))
    if not isinstance(decoded, dict):
        raise MasterKeyError("sensitive setting payload is invalid")
    return decoded


class EncryptedText(TypeDecorator[str]):
    impl = Text
    cache_ok = True
    python_type = str

    def process_bind_param(self, value: str | None, _dialect: object) -> str | None:
        return encrypt_text(value) if value else None

    def process_result_value(self, value: str | None, _dialect: object) -> str | None:
        return decrypt_text(value) if value is not None else None


class EncryptedJSON(TypeDecorator[dict[str, Any]]):
    impl = Text
    cache_ok = True
    python_type = dict

    def process_bind_param(self, value: dict[str, Any] | None, _dialect: object) -> str | None:
        if value is None:
            return None
        return encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    def process_result_value(self, value: str | None, _dialect: object) -> dict[str, Any] | None:
        if value is None:
            return None
        decoded = json.loads(decrypt_text(value))
        if not isinstance(decoded, dict):
            raise MasterKeyError("encrypted JSON payload is invalid")
        return decoded


def ensure_master_key(session: Any) -> None:
    from gpt_auto_register.db.models.auth import SetupState

    state = session.get(SetupState, 1)
    if state is None:
        state = SetupState(id=1, initialized=False)
        session.add(state)
        session.flush()
    if state.master_key_verifier is None:
        state.master_key_verifier = encrypt_text(KEY_VERIFIER)
        session.commit()
        return
    if decrypt_text(state.master_key_verifier) != KEY_VERIFIER:
        raise MasterKeyError("master key verification failed")
