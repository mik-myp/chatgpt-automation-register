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
_RUNTIME_EVENT_BATCH_SIZE = 25
EventValue = tuple[str, str, str, dict[str, Any] | None]


def emit_event(
    session_factory: SessionFactory,
    job_id: str,
    event_type: str,
    message: str,
    *,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    emit_events(
        session_factory,
        job_id,
        [(event_type, message, level, data)],
    )


def emit_events(
    session_factory: SessionFactory,
    job_id: str,
    values: list[EventValue],
) -> int:
    if not values:
        return 0
    with _EVENT_LOCK:
        return _write_events(
            session_factory,
            job_id,
            values,
        )


def _write_events(
    session_factory: SessionFactory,
    job_id: str,
    values: list[EventValue],
) -> int:
    for _ in range(5):
        with session_factory() as session:
            runtime_values = sum(value[0] == "runtime_log" for value in values)
            rejected = 0
            filtered = values
            if runtime_values:
                limit = SettingsService(session).maintenance_internal().max_runtime_log_lines
                existing = (
                    session.scalar(
                        select(func.count())
                        .select_from(JobEvent)
                        .where(
                            JobEvent.job_id == job_id,
                            JobEvent.event_type == "runtime_log",
                        )
                    )
                    or 0
                )
                available = max(0, limit - existing)
                accepted_runtime = 0
                filtered = []
                for value in values:
                    if value[0] != "runtime_log":
                        filtered.append(value)
                    elif accepted_runtime < available:
                        filtered.append(value)
                        accepted_runtime += 1
                    else:
                        rejected += 1
                if not filtered:
                    return rejected
            sequence = (
                session.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id))
                or 0
            ) + 1
            session.add_all(
                JobEvent(
                    job_id=job_id,
                    sequence=sequence + index,
                    level=level,
                    event_type=event_type,
                    message=message[:4000],
                    data=data or {},
                )
                for index, (event_type, message, level, data) in enumerate(filtered)
            )
            try:
                session.commit()
                return rejected
            except IntegrityError:
                session.rollback()
    return len(values)


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

    buffered: list[EventValue] = []
    stored_lines = 0
    if job_id:
        with session_factory() as session:
            stored_lines = (
                session.scalar(
                    select(func.count())
                    .select_from(JobEvent)
                    .where(
                        JobEvent.job_id == job_id,
                        JobEvent.event_type == "runtime_log",
                    )
                )
                or 0
            )
    skipped_lines = 0

    def flush() -> None:
        nonlocal skipped_lines
        if job_id and buffered:
            skipped_lines += emit_events(session_factory, job_id, [*buffered])
            buffered.clear()

    def sink(line: str) -> None:
        nonlocal skipped_lines, stored_lines
        if stored_lines >= max_lines:
            skipped_lines += 1
            return
        buffered.append(("runtime_log", line, "debug", None))
        stored_lines += 1
        if len(buffered) >= _RUNTIME_EVENT_BATCH_SIZE:
            flush()

    try:
        return runtime_call(
            payload,
            timeout,
            log_sink=sink if job_id else None,
            max_lines=max_lines,
            cancel_check=cancel_check,
        )
    finally:
        flush()
        if job_id and skipped_lines:
            emit_event(
                session_factory,
                job_id,
                "runtime_log_truncated",
                f"运行日志达到 {max_lines} 行上限，已忽略后续 {skipped_lines} 行",
                level="warning",
                data={"limit": max_lines, "skipped": skipped_lines},
            )
