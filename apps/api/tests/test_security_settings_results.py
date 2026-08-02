from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import Credential


def test_security_settings_defaults_and_update(client: TestClient) -> None:
    current = client.get("/api/settings").json()
    assert current["registration"]["password_mode"] == "random"
    assert current["registration"]["enable_authenticator_mfa"] is False

    current["registration"]["password_mode"] = "fixed"
    current["registration"]["fixed_password"] = "known-password"
    current["registration"]["enable_authenticator_mfa"] = True
    current["mail"]["cf_admin_token"] = ""
    current["sms"]["api_key"] = ""
    for target in ("cpa", "sub2api"):
        current["export"][target]["key"] = ""
    response = client.put("/api/settings", json=current)

    assert response.status_code == 200
    assert response.json()["registration"]["password_mode"] == "fixed"
    assert response.json()["registration"]["fixed_password"] == "known-password"
    assert response.json()["registration"]["enable_authenticator_mfa"] is True


def test_result_exposes_security_status_and_credentials(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(
        Credential(
            email="secure@example.com",
            password="password",
            totp_secret="JBSWY3DPEHPK3PXP",
            metadata_json={
                "account_security": {
                    "password": {"status": "set"},
                    "mfa": {"status": "enabled"},
                }
            },
        )
    )
    db_session.commit()

    summary = client.get("/api/results").json()["items"][0]
    assert summary["password_status"] == "set"
    assert summary["mfa_status"] == "enabled"
    assert summary["chatgpt_password"] == "password"
    assert summary["totp_secret"] == "JBSWY3DPEHPK3PXP"

    detail = client.get("/api/results/secure@example.com").json()
    assert detail["totp_secret"] == "JBSWY3DPEHPK3PXP"
