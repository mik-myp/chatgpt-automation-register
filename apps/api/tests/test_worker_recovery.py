from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.worker import manager


def test_only_one_worker_can_hold_the_local_database_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_path = tmp_path / "data" / "runtime"

    def ensure_directories() -> None:
        runtime_path.mkdir(parents=True, exist_ok=True)

    settings = SimpleNamespace(
        runtime_data_path=runtime_path,
        ensure_runtime_directories=ensure_directories,
    )
    monkeypatch.setattr(manager, "get_settings", lambda: settings)
    first = manager.WorkerManager()
    second = manager.WorkerManager()
    try:
        assert first._acquire_singleton_lock() is True
        assert second._acquire_singleton_lock() is False
    finally:
        first._release_singleton_lock()
        second._release_singleton_lock()


def test_worker_reclaims_running_job_without_lease(
    db_session: Session,
    monkeypatch,
) -> None:
    job = Job(
        kind="account.security",
        status=JobStatus.RUNNING,
        payload={"action": "set_password", "emails": ["user@example.com"]},
        lease_owner=None,
        lease_expires_at=None,
    )
    db_session.add(job)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(manager, "SessionLocal", factory)

    claimed = manager.WorkerManager()._claim()

    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.lease_owner is not None
    assert claimed.attempts == 1
