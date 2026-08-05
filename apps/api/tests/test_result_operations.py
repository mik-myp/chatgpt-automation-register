import threading

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.db.models.pipeline import PipelineItem
from gpt_auto_register.worker import result_operations


def _plus_result() -> dict[str, object]:
    return {
        "state": "plus",
        "label": "Plus 已生效",
        "is_plus": True,
        "error": "",
    }


def test_plus_check_recovers_missing_access_token_from_session(
    db_session: Session,
    monkeypatch,
) -> None:
    email = "session@example.com"
    db_session.add(Credential(email=email, session_token="session-token", metadata_json={}))
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(result_operations, "SessionLocal", factory)

    checked_tokens: list[str] = []
    monkeypatch.setattr(
        result_operations,
        "check_plus",
        lambda token, _proxy: checked_tokens.append(token) or _plus_result(),
    )
    monkeypatch.setattr(
        result_operations,
        "call_legacy_runtime",
        lambda *_args, **_kwargs: {
            "ok": True,
            "credential": {"access_token": "session-access-token"},
        },
    )

    result = result_operations.ResultOperationExecutor("job-id", {}, threading.Event())._check_one(
        email, ""
    )

    assert result["is_plus"] is True
    assert result["recovery_mode"] == "session"
    assert checked_tokens == ["session-access-token"]
    with factory() as session:
        credential = session.get(Credential, email)
        assert credential is not None
        assert credential.access_token == "session-access-token"


def test_plus_check_falls_back_to_login_after_session_token_stays_unauthorized(
    db_session: Session,
    monkeypatch,
) -> None:
    email = "login@example.com"
    db_session.add_all(
        [
            OutlookAccount(email=email, password="mail-password"),
            Credential(
                email=email,
                password="chatgpt-password",
                access_token="expired-access-token",
                session_token="session-token",
                metadata_json={},
            ),
        ]
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(result_operations, "SessionLocal", factory)

    checked_tokens: list[str] = []

    def fake_check(token: str, _proxy: str) -> dict[str, object]:
        checked_tokens.append(token)
        if token == "login-access-token":
            return _plus_result()
        return {
            "state": "invalid_token",
            "label": "令牌已失效",
            "is_plus": None,
            "error": "HTTP 401",
        }

    recovery_modes: list[str] = []

    def fake_runtime(
        _factory: object,
        payload: dict[str, object],
        **_kwargs: object,
    ) -> dict[str, object]:
        mode = str(payload["mode"])
        recovery_modes.append(mode)
        return {
            "ok": True,
            "credential": {
                "access_token": f"{mode}-access-token",
                "session_token": f"{mode}-session-token",
            },
        }

    monkeypatch.setattr(result_operations, "check_plus", fake_check)
    monkeypatch.setattr(result_operations, "call_legacy_runtime", fake_runtime)

    result = result_operations.ResultOperationExecutor("job-id", {}, threading.Event())._check_one(
        email, ""
    )

    assert result["is_plus"] is True
    assert result["recovery_mode"] == "login"
    assert recovery_modes == ["session", "login"]
    assert checked_tokens == [
        "expired-access-token",
        "session-access-token",
        "login-access-token",
    ]
    with factory() as session:
        credential = session.get(Credential, email)
        assert credential is not None
        assert credential.access_token == "login-access-token"
        assert credential.session_token == "login-session-token"


def test_result_operation_cancel_and_retry_only_requeues_failed_or_remaining_accounts(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/results/check-plus",
        json={"emails": ["done@example.com", "failed@example.com", "remaining@example.com"]},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    canceled = client.post(f"/api/result-operations/{job_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"

    job = db_session.get(Job, job_id)
    assert job is not None
    job.payload = {
        **job.payload,
        "resolved_emails": [
            "done@example.com",
            "failed@example.com",
            "remaining@example.com",
        ],
    }
    job.result = {
        "total": 3,
        "processed": 2,
        "succeeded": 1,
        "failed": 1,
        "processed_emails": ["done@example.com", "failed@example.com"],
        "failed_emails": ["failed@example.com"],
    }
    db_session.commit()

    retried = client.post(f"/api/result-operations/{job_id}/retry")

    assert retried.status_code == 202
    retry_job = db_session.get(Job, retried.json()["id"])
    assert retry_job is not None
    assert retry_job.status == JobStatus.QUEUED
    assert retry_job.payload["emails"] == ["failed@example.com", "remaining@example.com"]
    assert retry_job.payload["all"] is False
    assert retry_job.payload["retry_of"] == job_id


def test_plus_check_accepts_pipeline_run_scope_without_explicit_emails(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/results/check-plus",
        json={"emails": [], "all": False, "pipeline_run_id": "security-run-id"},
    )

    assert response.status_code == 202
    job = db_session.get(Job, response.json()["id"])
    assert job is not None
    assert job.payload["pipeline_run_id"] == "security-run-id"
    assert job.payload["emails"] == []
    assert job.payload["all"] is False


def test_result_operation_email_query_is_postgresql_compatible_and_deduplicated(
    db_session: Session,
) -> None:
    email = "duplicate@example.com"
    db_session.add(Credential(email=email, metadata_json={}))
    db_session.add_all(
        [
            PipelineItem(pipeline_run_id="run-id", position=0, account_email=email),
            PipelineItem(pipeline_run_id="run-id", position=1, account_email=email),
        ]
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", capture_statement)
    try:
        emails = result_operations.ResultOperationExecutor(
            "missing-job",
            {"pipeline_run_id": "run-id"},
            threading.Event(),
            factory,
        )._resolve_emails()
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", capture_statement)

    assert emails == [email]
    credential_query = next(
        statement for statement in statements if "SELECT DISTINCT credentials.email" in statement
    )
    assert "credentials.created_at" in credential_query.split("FROM credentials", maxsplit=1)[0]
