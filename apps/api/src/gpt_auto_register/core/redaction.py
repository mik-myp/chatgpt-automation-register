from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = {
    "access_token",
    "accesstoken",
    "api_key",
    "authorization",
    "cookie",
    "cookie_header",
    "fixed_password",
    "id_token",
    "password",
    "refresh_token",
    "refreshtoken",
    "session_token",
    "sessiontoken",
    "totp_secret",
}
_KEY_VALUE = re.compile(
    r"(?i)(?P<prefix>\b(?:access[_-]?token|refresh[_-]?token|session[_-]?token|"
    r"id[_-]?token|api[_-]?key|authorization|cookie(?:_header)?|fixed[_-]?password|"
    r"password|totp[_-]?secret)\b\s*[:=]\s*)(?P<quote>[\"']?)(?P<value>[^\s,;\"'}]+)(?P=quote)"
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_OTP = re.compile(
    r"(?i)(?P<prefix>\b(?:otp|one[- ]?time(?: password)?|verification code|"
    r"验证码|校验码|动态码)\b[^\r\n\d]{0,24})(?P<value>\d{6})(?!\d)"
)


def is_sensitive_key(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9_]", "", str(key).strip().lower().replace("-", "_"))
    return normalized in _SENSITIVE_KEYS


def redact_text(value: str, *, limit: int | None = None) -> str:
    text = _BEARER.sub(r"\1" + REDACTED, value)
    text = _KEY_VALUE.sub(lambda match: f"{match.group('prefix')}{REDACTED}", text)
    text = _OTP.sub(lambda match: f"{match.group('prefix')}{REDACTED}", text)
    if limit is not None and len(text) > limit:
        return text[: max(0, limit - 1)] + "…"
    return text


def redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(key) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_value(item) for item in value]
    return value
