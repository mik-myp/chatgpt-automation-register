import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.jobs import Job
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoCardBatch,
    KakaoTask,
    KakaoTaskStatus,
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
from gpt_auto_register.modules.cards.allocator import CardAllocationError
from gpt_auto_register.modules.settings.schemas import DeliveryCopySettings


def test_pipeline_detail_includes_snapshot_and_items(
    client: TestClient, db_session: Session
) -> None:
    run = PipelineRun(
        status=PipelineStatus.FAILED,
        mode="single",
        target_count=1,
        kakao_enabled=False,
        config_snapshot={"registration": {"concurrency": 1}},
        scheduled_count=1,
    )
    db_session.add(run)
    db_session.flush()
    batch = KakaoCardBatch(name="test")
    db_session.add(batch)
    db_session.flush()
    card = KakaoCard(batch_id=batch.id, code="FULL-CARD-CODE", position=0)
    db_session.add(card)
    db_session.flush()
    db_session.add_all(
        [
            PipelineItem(pipeline_run_id=run.id, position=0),
            PipelineCardAllocation(
                pipeline_run_id=run.id,
                card_id=card.id,
                allocated_count=1,
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/pipelines/runs/{run.id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["config_snapshot"] == {"registration": {"concurrency": 1}}
    assert len(detail["items"]) == 1
    assert detail["cards"][0]["card_code"] == "FULL-CARD-CODE"


def test_single_pipeline_preserves_requested_email(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/pipelines/runs",
        json={
            "mode": "single",
            "email": "  Selected@Example.COM  ",
            "target_count": 1,
            "kakao_enabled": False,
        },
    )

    assert response.status_code == 201
    detail_response = client.get(f"/api/pipelines/runs/{response.json()['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["items"][0]["account_email"] == "selected@example.com"


def test_kakao_pipeline_creation_rejects_insufficient_capacity(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_capacity(_allocator: object, target_count: int) -> object:
        raise CardAllocationError(f"卡密实时剩余次数只有 1，无法分配 {target_count} 个任务")

    monkeypatch.setattr(
        "gpt_auto_register.modules.pipelines.router.CardAllocator.select",
        reject_capacity,
    )

    response = client.post(
        "/api/pipelines/runs",
        json={"mode": "batch", "target_count": 3, "kakao_enabled": True},
    )

    assert response.status_code == 409
    assert "无法分配 3 个任务" in response.json()["detail"]


def test_non_kakao_pipeline_does_not_check_card_capacity(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(_allocator: object, _target_count: int) -> object:
        raise AssertionError("Kakao disabled pipeline must not query card capacity")

    monkeypatch.setattr(
        "gpt_auto_register.modules.pipelines.router.CardAllocator.select",
        unexpected_call,
    )

    response = client.post(
        "/api/pipelines/runs",
        json={"mode": "batch", "target_count": 2, "kakao_enabled": False},
    )

    assert response.status_code == 201


def test_pipeline_detail_includes_plus_state_and_card_assignments(
    client: TestClient,
    db_session: Session,
) -> None:
    run = PipelineRun(
        status=PipelineStatus.COMPLETED,
        mode="single",
        target_count=1,
        kakao_enabled=True,
        scheduled_count=1,
    )
    batch = KakaoCardBatch(name="assignments")
    db_session.add_all([run, batch])
    db_session.flush()
    item = PipelineItem(
        pipeline_run_id=run.id,
        position=0,
        account_email="plus@example.com",
        status=PipelineItemStatus.COMPLETED,
    )
    card = KakaoCard(batch_id=batch.id, code="ASSIGNMENT-CARD", position=0)
    credential = Credential(
        email="plus@example.com",
        metadata_json={
            "plus_check": {
                "state": "plus",
                "label": "Plus 已生效",
                "is_plus": True,
                "checked_at": "2026-08-02T10:00:00+00:00",
            }
        },
    )
    db_session.add_all([item, card, credential])
    db_session.flush()
    db_session.add_all(
        [
            PipelineCardAllocation(
                pipeline_run_id=run.id,
                card_id=card.id,
                allocated_count=1,
                created_count=1,
            ),
            KakaoTask(
                upstream_job_id="assignment-job",
                pipeline_run_id=run.id,
                pipeline_item_id=item.id,
                card_id=card.id,
                card_code_snapshot=card.code,
                email="plus@example.com",
                status=KakaoTaskStatus.DONE,
                payment_status="ready",
                card_charged=True,
                payment_url="https://pay.example.com/assignment",
            ),
        ]
    )
    db_session.commit()

    detail = client.get(f"/api/pipelines/runs/{run.id}").json()
    deliveries = client.get(f"/api/pipelines/runs/{run.id}/deliveries").json()

    assert detail["items"][0]["plus_state"] == "plus"
    assert detail["cards"][0]["assignments"] == [
        {
            "task_id": detail["cards"][0]["assignments"][0]["task_id"],
            "email": "plus@example.com",
            "status": "done",
            "payment_status": "ready",
            "card_charged": True,
        }
    ]
    assert deliveries["items"][0]["plus_is_active"] is True


def test_security_copy_obeys_plus_only_setting(
    client: TestClient,
    db_session: Session,
) -> None:
    run = PipelineRun(
        kind=PipelineRunKind.ACCOUNT_SECURITY,
        status=PipelineStatus.COMPLETED,
        mode="security",
        target_count=2,
        kakao_enabled=False,
        scheduled_count=2,
        registered_count=2,
    )
    db_session.add(run)
    db_session.flush()
    for position, email, plus_state, is_plus in [
        (0, "plus@example.com", "plus", True),
        (1, "free@example.com", "free", False),
    ]:
        db_session.add_all(
            [
                PipelineItem(
                    pipeline_run_id=run.id,
                    position=position,
                    account_email=email,
                    status=PipelineItemStatus.COMPLETED,
                ),
                Credential(
                    email=email,
                    password="known-password",
                    totp_secret="JBSWY3DPEHPK3PXP",
                    metadata_json={
                        "account_security": {
                            "password": {"status": "set"},
                            "mfa": {"status": "enabled"},
                        },
                        "plus_check": {
                            "state": plus_state,
                            "label": plus_state,
                            "is_plus": is_plus,
                        },
                    },
                ),
            ]
        )
    db_session.add(
        AppSetting(
            key="delivery_copy",
            value=DeliveryCopySettings(only_copy_plus=True).model_dump(),
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/pipelines/runs/{run.id}/security-credentials/copy",
        json={"all_completed": True},
    )

    assert response.status_code == 200
    assert response.json()["copied"] == 1
    assert response.json()["plus_restricted"] == 1
    assert "plus@example.com" in response.json()["text"]
    assert "free@example.com" not in response.json()["text"]


def test_global_security_candidates_only_include_available_incomplete_accounts(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            OutlookAccount(email="candidate@example.com"),
            OutlookAccount(email="complete@example.com"),
            OutlookAccount(email="busy@example.com"),
            OutlookAccount(email="missing-credential@example.com"),
            Credential(email="candidate@example.com", metadata_json={}),
            Credential(
                email="complete@example.com",
                password="chatgpt-password",
                totp_secret="JBSWY3DPEHPK3PXP",
                metadata_json={
                    "account_security": {
                        "password": {"status": "set"},
                        "mfa": {"status": "enabled"},
                    }
                },
            ),
            Credential(email="busy@example.com", metadata_json={}),
            Job(
                kind="account.security",
                payload={
                    "action": "set_password_and_mfa",
                    "emails": ["busy@example.com"],
                },
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/pipelines/runs/security-candidates",
        params={"search": "candidate", "limit": 25, "offset": 0},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "email": "candidate@example.com",
                "password_status": "not_set",
                "mfa_status": "not_enabled",
                "security_error": None,
                "needs_password": True,
                "needs_mfa": True,
            }
        ],
        "total": 1,
        "limit": 25,
        "offset": 0,
    }


def test_create_global_security_pipeline_without_source_run(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            OutlookAccount(email="selected@example.com"),
            Credential(email="selected@example.com", metadata_json={}),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/pipelines/runs/security-runs",
        json={"emails": [" Selected@Example.com "]},
    )

    assert response.status_code == 201
    run = response.json()
    assert run["kind"] == "account_security"
    assert run["source_pipeline_run_id"] is None
    assert run["target_count"] == 1
    detail = client.get(f"/api/pipelines/runs/{run['id']}").json()
    assert detail["items"][0]["account_email"] == "selected@example.com"
    assert detail["items"][0]["password_status"] == "not_set"
    assert detail["items"][0]["mfa_status"] == "not_enabled"
