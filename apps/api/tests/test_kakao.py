from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoCardBatch,
    KakaoEmailClaim,
    KakaoTask,
    KakaoTaskStatus,
)
from gpt_auto_register.db.models.pipeline import PipelineItem, PipelineRun
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.modules.kakao.client import KakaoClient
from gpt_auto_register.modules.kakao.state import claim_extraction


@pytest.fixture
def kakao_task(db_session: Session) -> Generator[KakaoTask, None, None]:
    db_session.add(
        AppSetting(
            key="kakao",
            value={"base_url": "https://kakao.example.com", "timeout": 30},
        )
    )
    batch = KakaoCardBatch(name="test batch")
    db_session.add(batch)
    db_session.flush()
    card = KakaoCard(batch_id=batch.id, code="KA-TEST", position=0, active=True)
    db_session.add(card)
    db_session.flush()
    db_session.add(Credential(email="alpha@example.com", access_token="token", metadata_json={}))
    task = KakaoTask(
        upstream_job_id="upstream-1",
        card_id=card.id,
        email="alpha@example.com",
        status=KakaoTaskStatus.QUEUED,
    )
    db_session.add(task)
    db_session.commit()
    yield task


def test_kakao_task_details_returns_local_and_upstream_state(
    client: TestClient,
    kakao_task: KakaoTask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        KakaoClient,
        "task_detail",
        lambda _self, job_id: {"job_id": job_id, "status": "queued"},
    )
    monkeypatch.setattr(
        KakaoClient,
        "kakao_status",
        lambda _self, job_id: {"job_id": job_id, "payment_status": "waiting"},
    )

    response = client.get(f"/api/kakao/tasks/{kakao_task.id}/details")

    assert response.status_code == 200
    payload = response.json()
    assert payload["local"]["id"] == kakao_task.id
    assert payload["task"]["job_id"] == "upstream-1"
    assert payload["kakao_status"]["payment_status"] == "waiting"


def test_kakao_sync_marks_email_when_payment_link_is_generated(
    client: TestClient,
    db_session: Session,
    kakao_task: KakaoTask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        KakaoClient,
        "task_statuses",
        lambda _self, _job_ids: {
            "items": [
                {
                    "job_id": kakao_task.upstream_job_id,
                    "status": "done",
                    "nicepay_checkout_url": "https://pay.example.com/generated",
                }
            ]
        },
    )

    response = client.post("/api/kakao/tasks/sync", json={"task_ids": [kakao_task.id]})

    assert response.status_code == 200
    db_session.expire_all()
    credential = db_session.get(Credential, kakao_task.email)
    saved_task = db_session.get(KakaoTask, kakao_task.id)
    assert credential is not None
    assert saved_task is not None
    assert saved_task.payment_url == "https://pay.example.com/generated"
    extraction = credential.metadata_json["kakao_extraction"]
    assert extraction["completed"] is True
    assert extraction["completed_at"]
    assert extraction["task_id"] == kakao_task.id
    assert extraction["upstream_job_id"] == kakao_task.upstream_job_id
    assert extraction["payment_url"] == "https://pay.example.com/generated"


def test_kakao_email_claim_allows_only_one_pipeline_item(db_session: Session) -> None:
    first_run = PipelineRun(target_count=1, config_snapshot={})
    second_run = PipelineRun(target_count=1, config_snapshot={})
    db_session.add_all([first_run, second_run])
    db_session.flush()
    first_item = PipelineItem(pipeline_run_id=first_run.id, position=0)
    second_item = PipelineItem(pipeline_run_id=second_run.id, position=0)
    db_session.add_all([first_item, second_item])
    db_session.flush()

    first = claim_extraction(db_session, "User@Example.com", first_run.id, first_item.id)
    duplicate = claim_extraction(db_session, "user@example.com", second_run.id, second_item.id)
    db_session.commit()

    assert first is True
    assert duplicate is False
    claim = db_session.get(KakaoEmailClaim, "user@example.com")
    assert claim is not None
    assert claim.pipeline_item_id == first_item.id
