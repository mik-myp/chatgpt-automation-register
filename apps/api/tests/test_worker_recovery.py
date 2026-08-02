from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.db.models.pipeline import PipelineRun, PipelineStatus
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


def test_retryable_job_failure_requeues_pipeline_without_marking_it_failed(
    db_session: Session,
    monkeypatch,
) -> None:
    run = PipelineRun(
        status=PipelineStatus.RUNNING,
        target_count=1,
        config_snapshot={},
    )
    worker = manager.WorkerManager()
    db_session.add(run)
    db_session.flush()
    job = Job(
        kind="pipeline.run",
        pipeline_run_id=run.id,
        status=JobStatus.RUNNING,
        payload={"pipeline_run_id": run.id},
        attempts=1,
        max_attempts=3,
        lease_owner=worker.worker_id,
    )
    db_session.add(job)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(manager, "SessionLocal", factory)

    status = worker._finish(job.id, error="temporary failure")

    with factory() as session:
        saved_job = session.get(Job, job.id)
        saved_run = session.get(PipelineRun, run.id)
        assert status == JobStatus.QUEUED
        assert saved_job is not None and saved_job.status == JobStatus.QUEUED
        assert saved_run is not None and saved_run.status == PipelineStatus.QUEUED
        assert saved_run.finished_at is None
