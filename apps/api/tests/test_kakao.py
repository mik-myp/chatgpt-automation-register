from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoCardBatch,
    KakaoTask,
    KakaoTaskStatus,
)
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.modules.kakao.client import KakaoClient


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
