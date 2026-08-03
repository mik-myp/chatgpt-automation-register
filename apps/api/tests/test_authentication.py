from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from gpt_auto_register.core.config import Settings
from gpt_auto_register.core.encryption import MasterKeyError, decrypt_text, encrypt_text
from gpt_auto_register.core.local_access import origin_matches_request_host
from gpt_auto_register.core.security import token_hash
from gpt_auto_register.db.base import Base, utc_now
from gpt_auto_register.db.models.auth import SetupState, UserSession
from gpt_auto_register.db.session import get_db
from gpt_auto_register.main import create_app

ORIGIN = "http://localhost:5173"
SETUP_TOKEN = "s" * 48


def request_with_origin(origin: str, host: str = "register.example.com") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/login",
            "raw_path": b"/api/auth/login",
            "query_string": b"",
            "headers": [
                (b"host", host.encode()),
                (b"origin", origin.encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
        }
    )


@pytest.fixture
def auth_client() -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(SetupState(id=1, initialized=False))
        session.commit()
        application = create_app(authentication_enabled=True)
        application.state.setup_token = SETUP_TOKEN
        application.state.setup_token_expires_at = utc_now() + timedelta(minutes=30)

        def override_db() -> Generator[Session, None, None]:
            yield session

        application.dependency_overrides[get_db] = override_db
        client = TestClient(application)
        yield client, session
        client.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_initialize_login_csrf_and_logout(auth_client: tuple[TestClient, Session]) -> None:
    client, session = auth_client
    initialized = client.post(
        "/api/setup/initialize",
        headers={"origin": ORIGIN},
        json={"token": SETUP_TOKEN, "username": "admin", "password": "correct horse battery"},
    )
    assert initialized.status_code == 200
    csrf = initialized.json()["csrf_token"]
    database_session = session.scalar(select(UserSession))
    assert database_session is not None
    assert database_session.token_hash != client.cookies.get("gpt_auto_session")
    assert len(database_session.token_hash) == 64

    assert client.get("/api/auth/session").status_code == 200
    assert client.get("/api/settings/data/export").status_code == 403
    assert (
        client.get(
            "/api/settings/data/export",
            headers={"X-Reauth-Password": "correct horse battery"},
        ).status_code
        == 200
    )
    assert client.post("/api/auth/logout", headers={"origin": ORIGIN}).status_code == 403
    logged_out = client.post(
        "/api/auth/logout",
        headers={"origin": ORIGIN, "x-csrf-token": csrf},
    )
    assert logged_out.status_code == 204
    assert client.get("/api/auth/session").status_code == 401


def test_expired_setup_token_is_rejected(auth_client: tuple[TestClient, Session]) -> None:
    client, _session = auth_client
    client.app.state.setup_token_expires_at = utc_now() - timedelta(seconds=1)
    response = client.post(
        "/api/setup/initialize",
        headers={"origin": ORIGIN},
        json={"token": SETUP_TOKEN, "username": "admin", "password": "correct horse battery"},
    )
    assert response.status_code == 403


def test_login_rate_limit(auth_client: tuple[TestClient, Session]) -> None:
    client, _session = auth_client
    initialized = client.post(
        "/api/setup/initialize",
        headers={"origin": ORIGIN},
        json={"token": SETUP_TOKEN, "username": "admin", "password": "correct horse battery"},
    )
    csrf = initialized.json()["csrf_token"]
    client.post(
        "/api/auth/logout",
        headers={"origin": ORIGIN, "x-csrf-token": csrf},
    )
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login",
                headers={"origin": ORIGIN},
                json={"username": "admin", "password": "wrong"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login",
            headers={"origin": ORIGIN},
            json={"username": "admin", "password": "wrong"},
        ).status_code
        == 429
    )


def test_encryption_rejects_tampered_ciphertext() -> None:
    ciphertext = encrypt_text("sensitive-value")
    assert ciphertext.startswith("enc:v1:")
    assert "sensitive-value" not in ciphertext
    assert decrypt_text(ciphertext) == "sensitive-value"
    with pytest.raises(MasterKeyError):
        decrypt_text(ciphertext[:-2] + "aa")
    assert token_hash("session-value") != "session-value"


def test_production_origin_validation_uses_request_host() -> None:
    assert origin_matches_request_host(request_with_origin("https://register.example.com"))
    assert origin_matches_request_host(
        request_with_origin("http://127.0.0.1:8000", "127.0.0.1:8000")
    )
    assert not origin_matches_request_host(request_with_origin("https://evil.example.com"))
    assert not origin_matches_request_host(request_with_origin("null"))


def test_production_cookie_is_not_forced_secure() -> None:
    settings = Settings(environment="production", database_url="sqlite+pysqlite:///:memory:")
    assert not settings.session_cookie_secure
