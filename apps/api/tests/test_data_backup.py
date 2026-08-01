from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import AccountStatus, Credential, OutlookAccount


def test_backup_export_preview_and_merge(client: TestClient, db_session: Session) -> None:
    db_session.add(OutlookAccount(email="local@example.com", status=AccountStatus.AVAILABLE))
    db_session.add(Credential(email="local@example.com", password="old"))
    db_session.commit()

    bundle = client.get("/api/settings/data/export").json()
    assert bundle["format"] == "gpt-auto-register-backup"
    assert bundle["version"] == 1
    credential = bundle["sections"]["credentials"][0]
    credential["password"] = "new"
    preview_request = {
        "bundle": bundle,
        "sections": ["credentials"],
        "mode": "merge",
    }
    preview = client.post("/api/settings/data/preview", json=preview_request)
    assert preview.status_code == 200
    assert preview.json()["sections"]["credentials"]["updated"] == 1

    imported = client.post(
        "/api/settings/data/import",
        json={**preview_request, "conflict_policy": "incoming"},
    )
    assert imported.status_code == 200
    assert imported.json()["updated"] == 1
    assert db_session.get(Credential, "local@example.com").password == "new"


def test_backup_overwrite_protects_in_use_account(
    client: TestClient, db_session: Session
) -> None:
    db_session.add(OutlookAccount(email="busy@example.com", status=AccountStatus.IN_USE))
    db_session.commit()
    bundle = client.get("/api/settings/data/export").json()
    bundle["sections"]["accounts"] = []
    request = {"bundle": bundle, "sections": ["accounts"], "mode": "overwrite"}

    preview = client.post("/api/settings/data/preview", json=request).json()
    assert preview["sections"]["accounts"]["protected"] == 1
    imported = client.post(
        "/api/settings/data/import",
        json={**request, "conflict_policy": "incoming"},
    ).json()
    assert imported["protected"] == 1
    assert db_session.get(OutlookAccount, "busy@example.com") is not None
