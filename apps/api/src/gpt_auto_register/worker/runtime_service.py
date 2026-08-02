import threading
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.jobs import JobEvent
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.runtime_gateway import runtime_call

SessionFactory = Callable[[], Session]
_EVENT_LOCK = threading.Lock()


def emit_event(
    session_factory: SessionFactory,
    job_id: str,
    event_type: str,
    message: str,
    *,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    with _EVENT_LOCK:
        _write_event(
            session_factory,
            job_id,
            event_type,
            message,
            level=level,
            data=data,
        )


def _write_event(
    session_factory: SessionFactory,
    job_id: str,
    event_type: str,
    message: str,
    *,
    level: str,
    data: dict[str, Any] | None,
) -> None:
    for _ in range(5):
        with session_factory() as session:
            sequence = (
                session.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id))
                or 0
            ) + 1
            session.add(
                JobEvent(
                    job_id=job_id,
                    sequence=sequence,
                    level=level,
                    event_type=event_type,
                    message=message[:4000],
                    data=data or {},
                )
            )
            try:
                session.commit()
                return
            except IntegrityError:
                session.rollback()


def call_legacy_runtime(
    session_factory: SessionFactory,
    payload: dict[str, Any],
    timeout: int = 1800,
    *,
    job_id: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    max_lines = 2000
    with session_factory() as session, suppress(Exception):
        max_lines = SettingsService(session).maintenance_internal().max_runtime_log_lines

    def sink(line: str) -> None:
        if job_id:
            emit_event(
                session_factory,
                job_id,
                "runtime_log",
                line,
                level="debug",
            )

    return runtime_call(
        payload,
        timeout,
        log_sink=sink if job_id else None,
        max_lines=max_lines,
        cancel_check=cancel_check,
    )
