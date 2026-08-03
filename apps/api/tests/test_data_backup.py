import hashlib
import io
import json
import zipfile
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import AccountStatus, Credential, OutlookAccount
from gpt_auto_register.db.models.jobs import Job, JobEvent


def _resign(bundle: dict[str, object]) -> None:
    value = {key: item for key, item in bundle.items() if key != "checksum"}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    bundle["checksum"] = "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def test_backup_export_preview_and_merge(client: TestClient, db_session: Session) -> None:
    db_session.add(OutlookAccount(email="local@example.com", status=AccountStatus.AVAILABLE))
    db_session.add(Credential(email="local@example.com", password="old"))
    db_session.commit()

    bundle = client.get("/api/settings/data/export").json()
    assert bundle["format"] == "gpt-auto-register-backup"
    assert bundle["version"] == 3
    assert "job_events" in bundle["scope"]["excluded"]
    credential = bundle["sections"]["credentials"][0]
    credential["password"] = "new"
    _resign(bundle)
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


def test_backup_rejects_tampered_bundle(client: TestClient, db_session: Session) -> None:
    db_session.add(Credential(email="secure@example.com", password="old"))
    db_session.commit()
    bundle = client.get("/api/settings/data/export").json()
    bundle["sections"]["credentials"][0]["password"] = "tampered"
    response = client.post(
        "/api/settings/data/preview",
        json={"bundle": bundle, "sections": ["credentials"], "mode": "merge"},
    )
    assert response.status_code == 422
    assert "完整性校验失败" in response.json()["detail"]


def test_backup_rejects_previous_format_version(client: TestClient) -> None:
    bundle = client.get("/api/settings/data/export").json()
    bundle["version"] = 2
    _resign(bundle)

    response = client.post(
        "/api/settings/data/preview",
        json={"bundle": bundle, "sections": ["settings"], "mode": "merge"},
    )

    assert response.status_code == 422


def test_backup_overwrite_protects_in_use_account(client: TestClient, db_session: Session) -> None:
    db_session.add(OutlookAccount(email="busy@example.com", status=AccountStatus.IN_USE))
    db_session.commit()
    bundle = client.get("/api/settings/data/export").json()
    bundle["sections"]["accounts"] = []
    _resign(bundle)
    request = {"bundle": bundle, "sections": ["accounts"], "mode": "overwrite"}

    preview = client.post("/api/settings/data/preview", json=request).json()
    assert preview["sections"]["accounts"]["protected"] == 1
    imported = client.post(
        "/api/settings/data/import",
        json={**request, "conflict_policy": "incoming"},
    ).json()
    assert imported["protected"] == 1
    assert db_session.get(OutlookAccount, "busy@example.com") is not None


def test_storage_cleanup_removes_only_expired_events(
    client: TestClient, db_session: Session
) -> None:
    job = Job(kind="pipeline.run", status="succeeded", payload={})
    db_session.add(job)
    db_session.flush()
    db_session.add_all(
        [
            JobEvent(
                job_id=job.id,
                sequence=1,
                event_type="old",
                created_at=utc_now() - timedelta(days=15),
            ),
            JobEvent(job_id=job.id, sequence=2, event_type="current"),
        ]
    )
    db_session.commit()

    stats = client.get("/api/settings/data/storage").json()
    assert stats["job_events"] == 2
    assert stats["expired_job_events"] == 1
    cleaned = client.post("/api/settings/data/cleanup").json()
    assert cleaned["removed_job_events"] == 1
    assert db_session.query(JobEvent).count() == 1


def test_diagnostic_export_preserves_raw_runtime_context(
    client: TestClient, db_session: Session
) -> None:
    job = Job(
        kind="pipeline.run",
        status="failed",
        payload={"access_token": "payload-secret"},
        error="alice@example.com password=hunter2",
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        JobEvent(
            job_id=job.id,
            sequence=1,
            event_type="runtime_log",
            level="error",
            message=("alice@example.com phone=13800138000 验证码: 123456 Bearer header-secret"),
            data={
                "access_token": "event-secret",
                "nested": {"email": "alice@example.com", "reason": "network timeout"},
            },
        )
    )
    db_session.commit()

    response = client.get("/api/settings/data/diagnostics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "gpt-auto-register-diagnostics-" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "manifest.json",
            "jobs.jsonl",
            "job-events.jsonl",
            "pipelines.jsonl",
        }
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        exported = b"\n".join(archive.read(name) for name in archive.namelist())

    assert manifest["format"] == "gpt-auto-register-diagnostics"
    assert manifest["scope"]["exported_jobs"] == 1
    assert manifest["scope"]["exported_job_events"] == 1
    for raw_value in (
        b"alice@example.com",
        b"hunter2",
        b"13800138000",
        b"123456",
        b"header-secret",
        b"event-secret",
    ):
        assert raw_value in exported
    assert b"payload-secret" not in exported
    assert manifest["security"]["encrypted"] is False
    assert manifest["security"]["redacted"] is False
