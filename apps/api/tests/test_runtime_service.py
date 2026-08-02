from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.jobs import Job, JobEvent
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.worker import runtime_service


def test_runtime_logs_are_batched_and_capped(
    db_session: Session,
    monkeypatch,
) -> None:
    job = Job(kind="pipeline.run", payload={})
    db_session.add_all(
        [
            job,
            AppSetting(
                key="maintenance",
                value={"job_log_retention_days": 14, "max_runtime_log_lines": 100},
            ),
        ]
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    def fake_runtime(
        _payload: dict[str, object],
        _timeout: int,
        *,
        log_sink: Callable[[str], None] | None,
        max_lines: int,
        cancel_check: Callable[[], bool] | None,
    ) -> dict[str, object]:
        assert max_lines == 100
        assert cancel_check is None
        assert log_sink is not None
        for index in range(120):
            log_sink(f"line {index}")
        return {"ok": True}

    monkeypatch.setattr(runtime_service, "runtime_call", fake_runtime)

    result = runtime_service.call_legacy_runtime(
        factory,
        {"action": "test"},
        job_id=job.id,
    )

    with factory() as session:
        runtime_lines = session.scalar(
            select(func.count())
            .select_from(JobEvent)
            .where(JobEvent.job_id == job.id, JobEvent.event_type == "runtime_log")
        )
        truncated = session.scalar(
            select(JobEvent).where(
                JobEvent.job_id == job.id,
                JobEvent.event_type == "runtime_log_truncated",
            )
        )
        assert result == {"ok": True}
        assert runtime_lines == 100
        assert truncated is not None
        assert truncated.data == {"limit": 100, "skipped": 20}
