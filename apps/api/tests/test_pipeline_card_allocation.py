import pytest
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.accounts import (
    AccountStatus,
    Credential,
    OutlookAccount,
    RegistrationRun,
)
from gpt_auto_register.db.models.jobs import Job
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoCardBatch,
    KakaoClaimState,
    KakaoEmailClaim,
    KakaoTask,
    PipelineCardAllocation,
)
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineRunKind,
    PipelineStatus,
)
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.modules.cards.allocator import CardAllocator
from gpt_auto_register.modules.kakao.client import KakaoClient
from gpt_auto_register.worker import executor_support, pipeline_executor


def configure_executor(monkeypatch: pytest.MonkeyPatch, factory: object) -> None:
    monkeypatch.setattr(pipeline_executor, "SessionLocal", factory)
    monkeypatch.setattr(executor_support, "SessionLocal", factory)


def test_first_card_allocation_initializes_counters(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = PipelineRun(target_count=1, kakao_enabled=True, config_snapshot={})
    batch = KakaoCardBatch(name="test")
    db_session.add_all([run, batch])
    db_session.flush()
    item = PipelineItem(pipeline_run_id=run.id, position=0)
    card = KakaoCard(batch_id=batch.id, code="test-card", position=0)
    job = Job(id="allocation-job", kind="pipeline.run", payload={})
    db_session.add_all([item, card, job])
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    monkeypatch.setattr(
        CardAllocator,
        "select",
        lambda _self, _count: (["test-card"], []),
    )

    mapping = pipeline_executor.PipelineExecutor("allocation-job", run.id)._allocate_cards(
        [item.id]
    )

    with factory() as session:
        allocation = session.get(PipelineCardAllocation, (run.id, card.id))
        assert mapping == {item.id: "test-card"}
        assert allocation is not None
        assert allocation.allocated_count == 1
        assert allocation.created_count == 0


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


def test_kakao_submission_counts_created_and_duplicate_tasks_separately(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "registered@example.com"
    run = PipelineRun(target_count=1, kakao_enabled=True, config_snapshot={})
    batch = KakaoCardBatch(name="test")
    credential = Credential(email=email, access_token="access-token", metadata_json={})
    job = Job(id="kakao-job", kind="pipeline.run", payload={})
    db_session.add_all(
        [
            run,
            batch,
            credential,
            job,
            AppSetting(
                key="kakao",
                value={"base_url": "https://kakao.example.com", "timeout": 30},
            ),
        ]
    )
    db_session.flush()
    item = PipelineItem(pipeline_run_id=run.id, position=0, account_email=email)
    card = KakaoCard(batch_id=batch.id, code="test-card", position=0)
    db_session.add_all([item, card])
    db_session.flush()
    allocation = PipelineCardAllocation(
        pipeline_run_id=run.id,
        card_id=card.id,
        allocated_count=1,
    )
    db_session.add(allocation)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    monkeypatch.setattr(
        KakaoClient,
        "check_eligibility",
        lambda _self, _tokens: {"items": [{"index": 0, "eligible": True, "state": "eligible"}]},
    )
    monkeypatch.setattr(
        KakaoClient,
        "create_tasks",
        lambda _self, **_kwargs: {
            "tasks": [{"job_id": "created-job", "status": "queued"}],
            "active_duplicates": [{"job_id": "duplicate-job", "status": "queued"}],
        },
    )

    pipeline_executor.PipelineExecutor(job.id, run.id)._run_kakao(
        item.id,
        {"email": email, "access_token": "access-token"},
        card.code,
    )

    with factory() as session:
        saved_run = session.get(PipelineRun, run.id)
        saved_allocation = session.get(PipelineCardAllocation, (run.id, card.id))
        saved_credential = session.get(Credential, email)
        tasks = session.query(KakaoTask).all()
        assert saved_run is not None
        assert saved_allocation is not None
        assert saved_credential is not None
        assert saved_run.kakao_task_count == 1
        assert saved_allocation.created_count == 1
        assert saved_allocation.duplicate_count == 1
        assert {task.upstream_job_id for task in tasks} == {"created-job", "duplicate-job"}
        assert saved_credential.metadata_json["kakao_pipeline"]["job_ids"] == ["created-job"]
        assert saved_credential.metadata_json["kakao_pipeline"]["active_duplicate_job_ids"] == [
            "duplicate-job"
        ]


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

    def unexpected_call(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("已完成 Kakao 提取的邮箱不应再次调用上游")

    monkeypatch.setattr(KakaoClient, "check_eligibility", unexpected_call)
    monkeypatch.setattr(KakaoClient, "create_tasks", unexpected_call)

    pipeline_executor.PipelineExecutor(job.id, run.id)._run_kakao(
        item.id,
        {"email": email, "access_token": "access-token"},
        "unused-card",
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
    batch = KakaoCardBatch(name="kakao executor")
    credential = Credential(email=email, access_token="access-token", metadata_json={})
    job = Job(id="kakao-pipeline-job", kind="pipeline.run", payload={})
    db_session.add_all(
        [
            run,
            batch,
            credential,
            job,
            AppSetting(
                key="kakao",
                value={"base_url": "https://kakao.example.com", "timeout": 30},
            ),
        ]
    )
    db_session.flush()
    card = KakaoCard(batch_id=batch.id, code="pipeline-card", position=0)
    item = PipelineItem(
        pipeline_run_id=run.id,
        position=0,
        account_email=email,
        card_code_snapshot=card.code,
    )
    db_session.add_all([card, item])
    db_session.flush()
    db_session.add(
        PipelineCardAllocation(
            pipeline_run_id=run.id,
            card_id=card.id,
            allocated_count=1,
        )
    )
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    configure_executor(monkeypatch, factory)
    monkeypatch.setattr(
        KakaoClient,
        "check_eligibility",
        lambda _self, _tokens: {"items": [{"index": 0, "eligible": True, "state": "eligible"}]},
    )
    monkeypatch.setattr(
        KakaoClient,
        "create_tasks",
        lambda _self, **_kwargs: {
            "tasks": [{"job_id": "pipeline-created-job", "status": "queued"}]
        },
    )

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
