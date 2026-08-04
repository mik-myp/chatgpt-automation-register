import pytest
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.accounts import (
    AccountStatus,
    Credential,
    OutlookAccount,
    RegistrationRun,
)
from gpt_auto_register.db.models.jobs import Job, JobEvent
from gpt_auto_register.db.models.kakao import (
    KakaoClaimState,
    KakaoEmailClaim,
    KakaoTask,
)
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineRunKind,
    PipelineStatus,
)
from gpt_auto_register.modules.kakao.local_service import (
    KakaoExtractionError,
    KakaoExtractionResult,
)
from gpt_auto_register.worker import executor_support, pipeline_executor, pipeline_kakao_executor
from gpt_auto_register.worker.proxy_service import ProxyAllocator, ProxyBatch


def configure_executor(monkeypatch: pytest.MonkeyPatch, factory: object) -> None:
    monkeypatch.setattr(pipeline_executor, "SessionLocal", factory)
    monkeypatch.setattr(executor_support, "SessionLocal", factory)


def configure_dynamic_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    def allocate(
        _self: ProxyAllocator,
        keys: list[str],
        *,
        region: str = "",
    ) -> ProxyBatch:
        prefix = {"KR": "10.1", "VN": "10.2"}.get(region, "10.0")
        assignments = {
            key: [f"http://{prefix}.{index + 1}.{attempt + 1}:7000" for attempt in range(3)]
            for index, key in enumerate(keys)
        }
        return ProxyBatch(assignments, len(keys) * 3, len(keys) * 3, 0, 0)

    monkeypatch.setattr(ProxyAllocator, "allocate", allocate)


def local_extraction_result() -> KakaoExtractionResult:
    return KakaoExtractionResult(
        payment_url="https://web.nicepay.co.kr/payment/local",
        checkout_session_id="checkout-local",
        payment_method_id="pm-local",
        stripe_redirect_url="https://checkout.stripe.com/local",
    )


def test_first_registration_result_initializes_credential_metadata(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = PipelineRun(target_count=1, kakao_enabled=False, config_snapshot={})
    account = OutlookAccount(email="new@example.com", status=AccountStatus.IN_USE)
    db_session.add_all([run, account])
    db_session.flush()
    registration = RegistrationRun(email=account.email, config_snapshot={})
    item = PipelineItem(
        pipeline_run_id=run.id,
        position=0,
        account_email=account.email,
    )
    db_session.add_all([registration, item])
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    pipeline_executor.PipelineExecutor("unused", run.id)._save_registration_success(
        item.id,
        registration.id,
        {
            "email": account.email,
            "password": "known-password",
            "security": {
                "password": {"status": "set"},
                "mfa": {"status": "not_requested"},
            },
        },
    )

    with factory() as session:
        credential = session.get(Credential, account.email)
        assert credential is not None
        assert credential.password == "known-password"
        assert credential.metadata_json["account_security"]["password"]["status"] == "set"


def test_canceled_pipeline_does_not_persist_registration_result(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "canceled@example.com"
    run = PipelineRun(
        status=PipelineStatus.CANCELED,
        target_count=1,
        kakao_enabled=False,
        config_snapshot={},
    )
    account = OutlookAccount(email=email, status=AccountStatus.IN_USE)
    db_session.add_all([run, account])
    db_session.flush()
    registration = RegistrationRun(email=email, config_snapshot={})
    item = PipelineItem(
        pipeline_run_id=run.id,
        position=0,
        account_email=email,
    )
    db_session.add_all([registration, item])
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    pipeline_executor.PipelineExecutor("unused", run.id)._save_registration_success(
        item.id,
        registration.id,
        {"email": email, "password": "must-not-be-saved"},
    )

    with factory() as session:
        assert session.get(Credential, email) is None


def test_pipeline_reports_canceled_when_canceled_during_execution(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = PipelineRun(
        target_count=1,
        kakao_enabled=False,
        config_snapshot={"registration": {"concurrency": 1}},
    )
    job = Job(id="cancel-during-execution", kind="pipeline.run", payload={})
    db_session.add_all([run, job])
    db_session.flush()
    item = PipelineItem(pipeline_run_id=run.id, position=0)
    db_session.add(item)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    configure_dynamic_proxies(monkeypatch)

    def cancel_item(*_args: object, **_kwargs: object) -> bool:
        with factory() as session:
            saved_run = session.get(PipelineRun, run.id)
            assert saved_run is not None
            saved_run.status = PipelineStatus.CANCELED
            session.commit()
        return False

    monkeypatch.setattr(pipeline_executor.PipelineExecutor, "_execute_item", cancel_item)

    result = pipeline_executor.PipelineExecutor(job.id, run.id).execute()

    assert result["status"] == "canceled"


def test_kakao_submission_persists_local_payment_link(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "registered@example.com"
    run = PipelineRun(target_count=1, kakao_enabled=True, config_snapshot={})
    credential = Credential(email=email, access_token="access-token", metadata_json={})
    job = Job(id="kakao-job", kind="pipeline.run", payload={})
    db_session.add_all(
        [
            run,
            credential,
            job,
        ]
    )
    db_session.flush()
    item = PipelineItem(pipeline_run_id=run.id, position=0, account_email=email)
    db_session.add(item)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    monkeypatch.setattr(
        pipeline_kakao_executor,
        "extract_payment_link",
        lambda **_kwargs: local_extraction_result(),
    )

    pipeline_executor.PipelineExecutor(job.id, run.id)._run_kakao(
        item.id,
        {"email": email, "access_token": "access-token"},
        kr_proxy="http://10.1.1.1:7000",
        vn_proxy="http://10.2.1.1:7000",
    )

    with factory() as session:
        saved_run = session.get(PipelineRun, run.id)
        saved_credential = session.get(Credential, email)
        tasks = session.query(KakaoTask).all()
        assert saved_run is not None
        assert saved_credential is not None
        assert saved_run.kakao_task_count == 1
        assert len(tasks) == 1
        assert tasks[0].payment_url == "https://web.nicepay.co.kr/payment/local"
        assert tasks[0].upstream_payload["engine"] == "local-upi-1"
        assert (
            saved_credential.metadata_json["kakao_pipeline"]["payment_url"]
            == tasks[0].payment_url
        )


def test_kakao_submission_skips_email_with_completed_claim(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "already-extracted@example.com"
    run = PipelineRun(
        kind=PipelineRunKind.KAKAO,
        target_count=1,
        kakao_enabled=True,
        config_snapshot={},
    )
    db_session.add(run)
    db_session.flush()
    item = PipelineItem(pipeline_run_id=run.id, position=0, account_email=email)
    job = Job(id="skip-kakao-job", kind="pipeline.run", payload={})
    credential = Credential(email=email, access_token="access-token", metadata_json={})
    completed_claim = KakaoEmailClaim(
        email=email,
        state=KakaoClaimState.COMPLETED,
    )
    db_session.add_all([item, job, credential, completed_claim])
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)

    pipeline_executor.PipelineExecutor(job.id, run.id)._run_kakao(
        item.id,
        {"email": email, "access_token": "access-token"},
        kr_proxy="http://10.1.1.1:7000",
        vn_proxy="http://10.2.1.1:7000",
    )

    with factory() as session:
        saved_item = session.get(PipelineItem, item.id)
        assert saved_item is not None
        assert saved_item.status == PipelineItemStatus.COMPLETED
        assert saved_item.eligibility_state == "already_extracted"


def test_kakao_pipeline_executes_existing_credentials(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "pipeline-kakao@example.com"
    run = PipelineRun(
        kind=PipelineRunKind.KAKAO,
        target_count=1,
        kakao_enabled=True,
        config_snapshot={},
        scheduled_count=1,
    )
    credential = Credential(email=email, access_token="access-token", metadata_json={})
    job = Job(id="kakao-pipeline-job", kind="pipeline.run", payload={})
    db_session.add_all(
        [
            run,
            credential,
            job,
        ]
    )
    db_session.flush()
    item = PipelineItem(
        pipeline_run_id=run.id,
        position=0,
        account_email=email,
    )
    db_session.add(item)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    configure_dynamic_proxies(monkeypatch)
    attempted_pairs: list[tuple[str, str]] = []

    def extract(**kwargs: object) -> KakaoExtractionResult:
        attempted_pairs.append((str(kwargs["kr_proxy"]), str(kwargs["vn_proxy"])))
        if len(attempted_pairs) == 1:
            raise KakaoExtractionError("temporary proxy failure", category="proxy", retryable=True)
        return local_extraction_result()

    monkeypatch.setattr(pipeline_kakao_executor, "extract_payment_link", extract)

    result = pipeline_executor.PipelineExecutor(job.id, run.id).execute()

    with factory() as session:
        saved_run = session.get(PipelineRun, run.id)
        saved_item = session.get(PipelineItem, item.id)
        task = session.query(KakaoTask).one()
        assert result["completed"] == 1
        assert saved_run is not None
        assert saved_run.status == PipelineStatus.COMPLETED
        assert saved_run.registered_count == 1
        assert saved_run.kakao_task_count == 1
        assert saved_item is not None
        assert saved_item.status == PipelineItemStatus.COMPLETED
        assert task.pipeline_run_id == run.id
        assert task.pipeline_item_id == item.id
        assert task.payment_url == "https://web.nicepay.co.kr/payment/local"
        assert attempted_pairs == [
            ("http://10.1.1.1:7000", "http://10.2.1.1:7000"),
            ("http://10.1.1.2:7000", "http://10.2.1.2:7000"),
        ]
        attempts = list(
            session.query(JobEvent)
            .filter(JobEvent.job_id == job.id, JobEvent.event_type.like("proxy_attempt_%"))
            .order_by(JobEvent.sequence)
        )
        assert [event.data["result"] for event in attempts] == ["failed", "succeeded"]


def test_invalid_state_retries_with_a_fresh_registration_process(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "retry@example.com"
    run = PipelineRun(
        target_count=1,
        kakao_enabled=False,
        config_snapshot={"registration": {"concurrency": 1}},
    )
    account = OutlookAccount(email=email, status=AccountStatus.AVAILABLE)
    job = Job(id="retry-job", kind="pipeline.run", payload={})
    db_session.add_all([run, account, job])
    db_session.flush()
    db_session.add(PipelineItem(pipeline_run_id=run.id, position=0))
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    configure_dynamic_proxies(monkeypatch)
    monkeypatch.setattr(pipeline_executor.time, "sleep", lambda _seconds: None)
    attempts = 0

    def register(_payload: dict[str, object], **_kwargs: object) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return {"ok": False, "error": "invalid_state"}
        return {"ok": True, "credential": {"email": email, "access_token": "token"}}

    monkeypatch.setattr(pipeline_executor, "_legacy_call", register)

    result = pipeline_executor.PipelineExecutor(job.id, run.id).execute()

    with factory() as session:
        saved_run = session.get(PipelineRun, run.id)
        assert saved_run is not None
        assert attempts == 3
        assert result["registered"] == 1
        assert saved_run.status == PipelineStatus.COMPLETED


def test_pipeline_is_failed_when_every_registration_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "failed@example.com"
    run = PipelineRun(
        target_count=1,
        kakao_enabled=False,
        config_snapshot={"registration": {"concurrency": 1}},
    )
    account = OutlookAccount(email=email, status=AccountStatus.AVAILABLE)
    job = Job(id="failed-job", kind="pipeline.run", payload={})
    db_session.add_all([run, account, job])
    db_session.flush()
    db_session.add(PipelineItem(pipeline_run_id=run.id, position=0))
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    configure_dynamic_proxies(monkeypatch)
    monkeypatch.setattr(
        pipeline_executor,
        "_legacy_call",
        lambda _payload, **_kwargs: {"ok": False, "error": "registration rejected"},
    )

    pipeline_executor.PipelineExecutor(job.id, run.id).execute()

    with factory() as session:
        saved_run = session.get(PipelineRun, run.id)
        assert saved_run is not None
        assert saved_run.status == PipelineStatus.FAILED
        assert saved_run.failed_count == 1
