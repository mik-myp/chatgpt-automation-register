from __future__ import annotations

import os
import threading
import time
from contextlib import suppress
from datetime import timedelta
from typing import Any, TextIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from sqlalchemy import Connection, Engine, or_, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.core.config import get_settings
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.auth import SetupState
from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.db.models.kakao import (
    KakaoTask,
    KakaoTaskStatus,
)
from gpt_auto_register.db.models.pipeline import (
    PipelineRun,
    PipelineStatus,
)
from gpt_auto_register.db.result import affected_rows
from gpt_auto_register.db.session import SessionLocal, engine
from gpt_auto_register.modules.kakao.client import KakaoClient, payload_tasks
from gpt_auto_register.modules.kakao.state import (
    apply_upstream,
    synchronized_kakao_state,
)
from gpt_auto_register.modules.settings.maintenance import cleanup_storage
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.account_security_executor import AccountSecurityExecutor
from gpt_auto_register.worker.cancellation import (
    monitor_job_cancellation,
    monitor_run_cancellation,
)
from gpt_auto_register.worker.executor_support import emit as _emit
from gpt_auto_register.worker.pipeline_executor import PipelineExecutor
from gpt_auto_register.worker.result_operations import ResultOperationExecutor
from gpt_auto_register.worker.runtime_gateway import RuntimeCanceledError


class WorkerManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        database_engine: Engine | None = None,
    ) -> None:
        self._session_factory_override = session_factory
        self._database_engine = database_engine or engine
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_cancel_event: threading.Event | None = None
        self.worker_id = f"local-{os.getpid()}"
        self._next_kakao_sync = 0.0
        self._next_maintenance = 0.0
        self._lock_file: TextIO | None = None
        self._lock_connection: Connection | None = None

    @property
    def _session_factory(self) -> sessionmaker[Session]:
        return self._session_factory_override or SessionLocal

    def _acquire_singleton_lock(self) -> bool:
        settings = get_settings()
        settings.ensure_runtime_directories()
        if getattr(settings, "database_dialect", "sqlite") == "postgresql":
            connection = self._database_engine.connect()
            acquired = bool(
                connection.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": 7_043_821_991},
                )
            )
            if not acquired:
                connection.close()
                return False
            self._lock_connection = connection
            return True
        lock_path = settings.runtime_data_path.parent / "worker.lock"
        lock_file = lock_path.open("a+", encoding="utf-8")
        lock_path.chmod(0o600)
        try:
            if os.name == "nt":
                lock_file.seek(0)
                if not lock_file.read(1):
                    lock_file.seek(0)
                    lock_file.write("\0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_file.close()
            return False
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        self._lock_file = lock_file
        return True

    def _release_singleton_lock(self) -> None:
        if self._lock_connection is not None:
            with suppress(Exception):
                self._lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": 7_043_821_991},
                )
            self._lock_connection.close()
            self._lock_connection = None
            return
        if self._lock_file is None:
            return
        with suppress(OSError):
            if os.name == "nt":
                self._lock_file.seek(0)
                unlock_mode = msvcrt.LK_UNLCK  # type: ignore[attr-defined]
                msvcrt.locking(  # type: ignore[attr-defined]
                    self._lock_file.fileno(), unlock_mode, 1
                )
            else:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        self._lock_file.close()
        self._lock_file = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self._acquire_singleton_lock():
            raise RuntimeError("已有 Worker 正在运行，首版部署只允许一个 Worker")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="pipeline-job-worker",
        )
        try:
            self._thread.start()
        except Exception:
            self._thread = None
            self._release_singleton_lock()
            raise

    def stop(self) -> None:
        self._stop.set()
        if self._active_cancel_event is not None:
            self._active_cancel_event.set()
        if self._thread:
            self._thread.join()
            self._thread = None
        self._release_singleton_lock()

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _claim(self) -> Job | None:
        now = utc_now()
        with self._session_factory() as session:
            candidate = (
                select(Job.id)
                .where(
                    Job.kind.in_(
                        [
                            "pipeline.run",
                            "account.security",
                            "results.plus_check",
                            "results.publish",
                        ]
                    ),
                    or_(
                        Job.status == JobStatus.QUEUED,
                        (Job.status == JobStatus.RUNNING)
                        & (Job.lease_expires_at.is_(None) | (Job.lease_expires_at < now)),
                    ),
                    Job.available_at <= now,
                )
                .order_by(Job.priority.desc(), Job.created_at, Job.id)
                .limit(1)
                .scalar_subquery()
            )
            statement = (
                update(Job)
                .where(Job.id == candidate)
                .values(
                    status=JobStatus.RUNNING,
                    attempts=Job.attempts + 1,
                    lease_owner=self.worker_id,
                    lease_expires_at=now + timedelta(hours=2),
                    error=None,
                )
                .returning(Job)
            )
            job = session.scalars(statement).one_or_none()
            session.commit()
            return job

    def _finish(
        self,
        job_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> JobStatus:
        with self._session_factory() as session:
            ownership = (
                Job.id == job_id,
                Job.status == JobStatus.RUNNING,
                Job.lease_owner == self.worker_id,
            )
            if error:
                job = session.get(Job, job_id)
                attempts = job.attempts if job is not None else 0
                delay = min(300, 5 * (2 ** max(0, attempts - 1)))
                requeued = affected_rows(
                    session.execute(
                        update(Job)
                        .where(*ownership, Job.attempts < Job.max_attempts)
                        .values(
                            status=JobStatus.QUEUED,
                            available_at=utc_now() + timedelta(seconds=delay),
                            error=error,
                            finished_at=None,
                            lease_owner=None,
                            lease_expires_at=None,
                        )
                    )
                )
                if requeued:
                    if job is not None and job.pipeline_run_id:
                        run = session.get(PipelineRun, job.pipeline_run_id)
                        if run is not None and run.status != PipelineStatus.CANCELED:
                            run.status = PipelineStatus.QUEUED
                            run.finished_at = None
                    session.commit()
                    return JobStatus.QUEUED
            final_status = JobStatus.FAILED if error else JobStatus.SUCCEEDED
            session.execute(
                update(Job)
                .where(*ownership)
                .values(
                    status=final_status,
                    error=error,
                    result=result or {},
                    finished_at=utc_now(),
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            session.commit()
            return final_status

    def _interrupt(self, job_id: str) -> None:
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status != JobStatus.RUNNING or job.lease_owner != self.worker_id:
                return
            job.status = JobStatus.QUEUED
            job.attempts = max(0, job.attempts - 1)
            job.available_at = utc_now()
            job.lease_owner = None
            job.lease_expires_at = None
            if job.pipeline_run_id:
                run = session.get(PipelineRun, job.pipeline_run_id)
                if run is not None and run.status != PipelineStatus.CANCELED:
                    run.status = PipelineStatus.QUEUED
                    run.finished_at = None
            session.commit()

    def _heartbeat(self, job_id: str, stopped: threading.Event) -> None:
        while not stopped.wait(30):
            with self._session_factory() as session:
                job = session.get(Job, job_id)
                if (
                    job is None
                    or job.status != JobStatus.RUNNING
                    or job.lease_owner != self.worker_id
                ):
                    return
                job.lease_expires_at = utc_now() + timedelta(minutes=2)
                session.commit()

    @synchronized_kakao_state
    def _sync_kakao_tasks(self) -> None:
        with self._session_factory() as session:
            settings = SettingsService(session).kakao_internal()
            if not settings.base_url:
                return
            tasks = list(
                session.scalars(
                    select(KakaoTask)
                    .where(
                        KakaoTask.status.in_([KakaoTaskStatus.QUEUED, KakaoTaskStatus.EXTRACTING])
                    )
                    .order_by(KakaoTask.updated_at)
                    .limit(200)
                )
            )
            if not tasks:
                return
            client = KakaoClient(settings.base_url, settings.timeout)
            for start in range(0, len(tasks), 50):
                group = tasks[start : start + 50]
                try:
                    values = payload_tasks(
                        client.task_statuses([task.upstream_job_id for task in group])
                    )
                except Exception:
                    continue
                by_id = {
                    str(value.get("job_id") or value.get("id") or ""): value for value in values
                }
                for task in group:
                    value = by_id.get(task.upstream_job_id)
                    if value is None:
                        continue
                    apply_upstream(task, value, session)
            session.commit()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if get_settings().authentication_enabled:
                with self._session_factory() as session:
                    setup = session.get(SetupState, 1)
                    if setup is None or not setup.initialized:
                        self._stop.wait(1)
                        continue
            now = time.monotonic()
            if now >= self._next_kakao_sync:
                self._next_kakao_sync = now + 5
                with suppress(Exception):
                    self._sync_kakao_tasks()
            if now >= self._next_maintenance:
                self._next_maintenance = now + 3600
                with suppress(Exception), self._session_factory() as session:
                    settings = get_settings()
                    maintenance = SettingsService(session).maintenance_internal()
                    cleanup_storage(
                        session,
                        retention_days=maintenance.job_log_retention_days,
                        backup_directory=settings.backup_path,
                    )
            job = self._claim()
            if job is None:
                self._stop.wait(0.5)
                continue
            heartbeat_stop = threading.Event()
            heartbeat = threading.Thread(
                target=self._heartbeat,
                args=(job.id, heartbeat_stop),
                daemon=True,
                name=f"job-heartbeat-{job.id[:8]}",
            )
            heartbeat.start()
            try:
                run_id = str(job.pipeline_run_id or job.payload.get("pipeline_run_id") or "")
                cancellation_monitor = (
                    monitor_run_cancellation(run_id, self._session_factory)
                    if run_id
                    else monitor_job_cancellation(job.id, self._session_factory)
                )
                with cancellation_monitor as cancel_event:
                    self._active_cancel_event = cancel_event
                    if job.kind in {"results.plus_check", "results.publish"}:
                        result = ResultOperationExecutor(
                            job.id,
                            job.payload,
                            cancel_event,
                            self._session_factory,
                        ).execute()
                        self._finish(job.id, result=result)
                        continue
                    if job.kind == "account.security":
                        result = AccountSecurityExecutor(
                            job.id,
                            job.payload,
                            cancel_event,
                            self._session_factory,
                        ).execute()
                        failed = int(result.get("failed") or 0)
                        self._finish(
                            job.id,
                            result=result,
                            error=f"{failed} 个账号安全操作失败" if failed else None,
                        )
                        continue
                    retry_item_ids = job.payload.get("retry_item_ids")
                    item_ids = (
                        [str(value) for value in retry_item_ids]
                        if isinstance(retry_item_ids, list)
                        else None
                    )
                    result = PipelineExecutor(
                        job.id,
                        run_id,
                        item_ids,
                        cancel_event,
                        self._session_factory,
                    ).execute()
                    self._finish(job.id, result=result)
            except RuntimeCanceledError:
                if self._stop.is_set():
                    self._interrupt(job.id)
            except Exception as error:
                _emit(job.id, "job_failed", str(error), level="error")
                final_status = self._finish(job.id, error=str(error))
                if final_status == JobStatus.FAILED:
                    with self._session_factory() as session:
                        run_id = str(
                            job.pipeline_run_id or job.payload.get("pipeline_run_id") or ""
                        )
                        run = session.get(PipelineRun, run_id)
                        if run is not None and run.status != PipelineStatus.CANCELED:
                            run.status = PipelineStatus.FAILED
                            run.finished_at = utc_now()
                        session.commit()
            finally:
                self._active_cancel_event = None
                heartbeat_stop.set()
                heartbeat.join(timeout=1)
