from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.kakao import (
    KakaoClaimState,
    KakaoEmailClaim,
    KakaoTask,
    KakaoTaskStatus,
)
from gpt_auto_register.db.models.pipeline import PipelineItem, PipelineRun
from gpt_auto_register.modules.kakao.state import claim_extraction


@pytest.fixture
def kakao_task(db_session: Session) -> Generator[KakaoTask, None, None]:
    task = KakaoTask(
        upstream_job_id="upstream-1",
        email="alpha@example.com",
        status=KakaoTaskStatus.QUEUED,
        upstream_payload={"engine": "local-upi-1", "stage": "queued"},
    )
    db_session.add(task)
    db_session.commit()
    yield task


def test_kakao_task_details_returns_local_engine_state(
    client: TestClient,
    kakao_task: KakaoTask,
) -> None:
    response = client.get(f"/api/kakao/tasks/{kakao_task.id}/details")

    assert response.status_code == 200
    payload = response.json()
    assert payload["local"]["id"] == kakao_task.id
    assert payload["task"] == {"engine": "local-upi-1", "stage": "queued"}
    assert payload["kakao_status"]["payment_status"] is None


def test_kakao_sync_marks_email_when_payment_link_is_generated(
    client: TestClient,
    db_session: Session,
    kakao_task: KakaoTask,
) -> None:
    kakao_task.status = KakaoTaskStatus.DONE
    kakao_task.payment_url = "https://pay.example.com/generated"
    db_session.commit()

    response = client.post("/api/kakao/tasks/sync", json={"task_ids": [kakao_task.id]})

    assert response.status_code == 200
    db_session.expire_all()
    saved_task = db_session.get(KakaoTask, kakao_task.id)
    claim = db_session.get(KakaoEmailClaim, kakao_task.email)
    assert saved_task is not None
    assert saved_task.payment_url == "https://pay.example.com/generated"
    assert claim is not None
    assert claim.state == KakaoClaimState.COMPLETED


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
