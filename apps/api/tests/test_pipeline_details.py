from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.pipeline import PipelineItem, PipelineRun, PipelineStatus


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
    db_session.add(PipelineItem(pipeline_run_id=run.id, position=0))
    db_session.commit()

    response = client.get(f"/api/pipelines/runs/{run.id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["config_snapshot"] == {"registration": {"concurrency": 1}}
    assert len(detail["items"]) == 1


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
