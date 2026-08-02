from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.worker import account_security_executor, manager


def test_account_security_failure_marks_job_failed(
    db_session: Session,
    monkeypatch,
) -> None:
    worker = manager.WorkerManager()
    job = Job(
        id="account-security-job",
        kind="account.security",
        status=JobStatus.RUNNING,
        payload={"action": "enable_mfa", "emails": ["user@example.com"]},
        attempts=1,
        max_attempts=1,
        lease_owner=worker.worker_id,
    )
    db_session.add(job)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(manager, "SessionLocal", factory)

    worker._finish(
        job.id,
        result={"succeeded": 0, "failed": 1, "total": 1},
        error="1 个账号安全操作失败",
    )

    with factory() as session:
        saved = session.get(Job, job.id)
        assert saved is not None
        assert saved.status == JobStatus.FAILED
        assert saved.error == "1 个账号安全操作失败"
        assert saved.result == {"succeeded": 0, "failed": 1, "total": 1}


def test_failed_security_action_persists_refreshed_session(
    db_session: Session,
    monkeypatch,
) -> None:
    email = "user@example.com"
    db_session.add(Credential(email=email, cookie_header="old-cookie", metadata_json={}))
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(account_security_executor, "SessionLocal", factory)

    account_security_executor.AccountSecurityExecutor._persist_session(
        email,
        {
            "access_token": "refreshed-access-token",
            "session_token": "refreshed-session-token",
            "cookie_header": "refreshed-cookie",
        },
    )

    with factory() as session:
        saved = session.get(Credential, email)
        assert saved is not None
        assert saved.access_token == "refreshed-access-token"
        assert saved.session_token == "refreshed-session-token"
        assert saved.cookie_header == "refreshed-cookie"
