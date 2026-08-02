from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.worker import manager


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
