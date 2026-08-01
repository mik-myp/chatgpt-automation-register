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
    KakaoTask,
    PipelineCardAllocation,
)
from gpt_auto_register.db.models.pipeline import PipelineItem, PipelineRun
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.modules.cards.allocator import CardAllocator
from gpt_auto_register.modules.kakao.client import KakaoClient
from gpt_auto_register.worker import manager


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
    monkeypatch.setattr(manager, "SessionLocal", factory)
    monkeypatch.setattr(
        CardAllocator,
        "select",
        lambda _self, _count: (["test-card"], []),
    )

    mapping = manager.PipelineExecutor("allocation-job", run.id)._allocate_cards([item.id])

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
    monkeypatch.setattr(manager, "SessionLocal", factory)
    manager.PipelineExecutor("unused", run.id)._save_registration_success(
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
    monkeypatch.setattr(manager, "SessionLocal", factory)
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

    manager.PipelineExecutor(job.id, run.id)._run_kakao(
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
