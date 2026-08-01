from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select, update

from gpt_auto_register.core.config import get_settings
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import (
    AccountStatus,
    Credential,
    OutlookAccount,
    RegistrationRun,
    RunStatus,
)
from gpt_auto_register.db.models.jobs import Job, JobEvent, JobStatus
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoTask,
    KakaoTaskStatus,
    PipelineCardAllocation,
)
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineStatus,
)
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.cards.allocator import CardAllocator
from gpt_auto_register.modules.kakao.client import KakaoClient, payload_tasks
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.legacy_runner import RESULT_PREFIX

_EVENT_LOCK = threading.Lock()


def _classify_error(message: str) -> str:
    value = message.lower()
    account_patterns = (
        "wrong_email_otp_code",
        "invalid_grant",
        "imap xoauth2",
        "outlook otp timeout",
        "registration_disallowed",
        "已有账号",
        "refresh_token 失效",
    )
    network_patterns = (
        "tls",
        "ssl",
        "connection",
        "timeout",
        "proxy",
        "socks",
        "dns",
        "cloudflare",
        "403 forbidden",
        "connection reset",
    )
    if any(pattern in value for pattern in account_patterns):
        return "account"
    if any(pattern in value for pattern in network_patterns):
        return "network"
    return "unknown"


def _emit(
    job_id: str,
    event_type: str,
    message: str,
    *,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    with _EVENT_LOCK, SessionLocal() as session:
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
                message=message,
                data=data or {},
            )
        )
        session.commit()


def _legacy_call(
    payload: dict[str, Any],
    timeout: int = 1800,
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    environment = os.environ.copy()
    environment["GPT_AUTO_LEGACY_RUNTIME_PATH"] = str(settings.legacy_runtime_path)
    environment["GPT_AUTO_RUNTIME_DATA_PATH"] = str(settings.runtime_data_path)
    process = subprocess.Popen(
        [sys.executable, "-m", "gpt_auto_register.worker.legacy_runner"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise RuntimeError("无法连接旧项目协议运行时")
    timed_out = threading.Event()

    def terminate_on_timeout() -> None:
        timed_out.set()
        process.kill()

    timer = threading.Timer(timeout, terminate_on_timeout)
    timer.daemon = True
    timer.start()
    lines: list[str] = []
    try:
        process.stdin.write(json.dumps(payload, ensure_ascii=False))
        process.stdin.close()
        for raw_line in process.stdout:
            line = raw_line.rstrip("\r\n")
            lines.append(line)
            if line and not line.startswith(RESULT_PREFIX) and job_id:
                _emit(job_id, "runtime_log", line[-4000:], level="debug")
        process.wait()
    finally:
        timer.cancel()
    if timed_out.is_set():
        raise RuntimeError(f"旧项目协议运行超时（{timeout} 秒）")
    for line in reversed(lines):
        if line.startswith(RESULT_PREFIX):
            value = json.loads(line.removeprefix(RESULT_PREFIX))
            if isinstance(value, dict):
                return value
    raise RuntimeError(lines[-1] if lines else "旧项目协议运行时未返回结果")


def _account_payload(account: OutlookAccount) -> dict[str, Any]:
    return {
        "email": account.email,
        "password": account.password or "",
        "client_id": account.client_id or "",
        "refresh_token": account.refresh_token or "",
        "mail_type": account.mail_type.value,
        "mail_url": account.mail_url or "",
    }


class PipelineExecutor:
    def __init__(self, job_id: str, run_id: str, item_ids: list[str] | None = None) -> None:
        self.job_id = job_id
        self.run_id = run_id
        self.item_ids = item_ids
        self._failure_lock = threading.Lock()
        self._consecutive_network_failures = 0

    def execute(self) -> dict[str, Any]:
        with SessionLocal() as session:
            run = session.get(PipelineRun, self.run_id)
            if run is None:
                raise RuntimeError("流水线轮次不存在")
            if run.status == PipelineStatus.CANCELED:
                return {"status": "canceled"}
            if run.status == PipelineStatus.QUEUED:
                run.status = PipelineStatus.RUNNING
            run.started_at = run.started_at or utc_now()
            settings_service = SettingsService(session)
            registration = dict(run.config_snapshot.get("registration") or {})
            sms = settings_service.sms_internal()
            mail = settings_service.mail_internal()
            export = settings_service.export_internal()
            item_query = select(PipelineItem.id).where(PipelineItem.pipeline_run_id == self.run_id)
            if self.item_ids is not None:
                item_query = item_query.where(PipelineItem.id.in_(self.item_ids))
            item_ids = list(session.scalars(item_query.order_by(PipelineItem.position)))
            session.commit()

        _emit(self.job_id, "pipeline_started", "流水线开始执行")
        card_codes = self._allocate_cards(item_ids) if run.kakao_enabled else {}
        concurrency = max(1, min(50, int(registration.get("concurrency") or 10)))
        success = failed = 0
        with ThreadPoolExecutor(max_workers=min(concurrency, len(item_ids) or 1)) as executor:
            futures = {
                executor.submit(
                    self._execute_item,
                    item_id,
                    registration,
                    sms,
                    mail,
                    export,
                    card_codes.get(item_id),
                ): item_id
                for item_id in item_ids
            }
            for future in as_completed(futures):
                try:
                    if future.result():
                        success += 1
                    else:
                        failed += 1
                except Exception as error:
                    failed += 1
                    _emit(
                        self.job_id,
                        "item_failed",
                        str(error),
                        level="error",
                        data={"item_id": futures[future]},
                    )

        with SessionLocal() as session:
            run = session.get(PipelineRun, self.run_id)
            if run is None:
                raise RuntimeError("流水线轮次已被删除")
            total_registered = (
                session.scalar(
                    select(func.count())
                    .select_from(PipelineItem)
                    .join(
                        RegistrationRun,
                        RegistrationRun.id == PipelineItem.registration_run_id,
                    )
                    .where(
                        PipelineItem.pipeline_run_id == self.run_id,
                        RegistrationRun.status == RunStatus.SUCCEEDED,
                    )
                )
                or 0
            )
            total_failed = max(0, run.target_count - total_registered)
            run.registered_count = total_registered
            run.failed_count = total_failed
            if run.status != PipelineStatus.CANCELED:
                run.status = PipelineStatus.COMPLETED
                run.finished_at = utc_now()
            session.commit()
        _emit(
            self.job_id,
            "pipeline_finished",
            f"流水线执行完成：成功 {success}，失败 {failed}",
            data={"registered": success, "failed": failed},
        )
        return {"status": "completed", "registered": success, "failed": failed}

    def _allocate_cards(self, item_ids: list[str]) -> dict[str, str]:
        with SessionLocal() as session:
            slots, _ = CardAllocator(session).select(len(item_ids))
            cards = {
                card.code: card
                for card in session.scalars(select(KakaoCard).where(KakaoCard.code.in_(set(slots))))
            }
            counts: dict[str, int] = {}
            mapping: dict[str, str] = {}
            for item_id, code in zip(item_ids, slots, strict=True):
                mapping[item_id] = code
                counts[code] = counts.get(code, 0) + 1
                item = session.get(PipelineItem, item_id)
                if item is not None:
                    item.card_code_snapshot = code
            for code, count in counts.items():
                card = cards[code]
                allocation = session.get(
                    PipelineCardAllocation,
                    (self.run_id, card.id),
                )
                if allocation is None:
                    allocation = PipelineCardAllocation(
                        pipeline_run_id=self.run_id,
                        card_id=card.id,
                    )
                    session.add(allocation)
                allocation.allocated_count += count
            session.commit()
        _emit(
            self.job_id,
            "cards_allocated",
            f"已实时分配 {len(item_ids)} 个卡密名额",
        )
        return mapping

    def _wait_until_runnable(self) -> bool:
        while True:
            with SessionLocal() as session:
                run = session.get(PipelineRun, self.run_id)
                if run is None or run.status == PipelineStatus.CANCELED:
                    return False
                if run.status != PipelineStatus.PAUSED:
                    return True
            time.sleep(0.5)

    def _execute_item(
        self,
        item_id: str,
        registration: dict[str, Any],
        sms: dict[str, Any],
        mail: dict[str, Any],
        export: dict[str, Any],
        card_code: str | None,
    ) -> bool:
        if not self._wait_until_runnable():
            return False
        resumed = self._resume_saved_registration(item_id, export, card_code)
        if resumed is not None:
            return resumed
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            run = session.get(PipelineRun, self.run_id)
            if item is None or run is None:
                return False
            if item.status in {
                PipelineItemStatus.COMPLETED,
                PipelineItemStatus.REGISTERED,
                PipelineItemStatus.SKIPPED,
            }:
                return True
            uses_cf_mail = mail.get("source") == "cf_temp"
            account = None if uses_cf_mail else AccountRepository(session).claim(item.account_email)
            if account is None and not uses_cf_mail:
                item.status = PipelineItemStatus.FAILED
                item.error = "没有可领取的号池账号"
                session.commit()
                return False
            if account is not None:
                item.account_email = account.email
            item.status = PipelineItemStatus.REGISTERING
            proxy = str(registration.get("proxy") or "").strip()
            if not proxy:
                pool = [
                    line.strip()
                    for line in str(registration.get("proxy_pool") or "").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
                if pool:
                    proxy = secrets.choice(pool)
            item_config = {**registration, "proxy": proxy}
            registration_run = RegistrationRun(
                email=account.email if account is not None else f"cf-pending-{item.id}",
                status=RunStatus.RUNNING,
                config_snapshot=item_config,
                started_at=utc_now(),
            )
            session.add(registration_run)
            session.flush()
            item.registration_run_id = registration_run.id
            account_data = (
                _account_payload(account)
                if account is not None
                else {
                    "email": "",
                    "password": "",
                    "client_id": "",
                    "refresh_token": "",
                    "mail_type": "cf_temp",
                    "mail_url": "",
                }
            )
            session.commit()

        _emit(
            self.job_id,
            "registration_started",
            f"开始注册 {account_data['email']}",
            data={"item_id": item_id, "email": account_data["email"]},
        )
        try:
            result = _legacy_call(
                {
                    "action": "register",
                    "account": account_data,
                    "registration": item_config,
                    "sms": sms,
                    "mail": mail,
                },
                job_id=self.job_id,
            )
            if not result.get("ok"):
                raise RuntimeError(str(result.get("error") or "注册失败"))
            credential = dict(result.get("credential") or {})
            self._save_registration_success(item_id, registration_run.id, credential)
            with self._failure_lock:
                self._consecutive_network_failures = 0
            _emit(
                self.job_id,
                "registration_succeeded",
                f"注册成功 {account_data['email']}",
                data={"item_id": item_id, "email": account_data["email"]},
            )
        except Exception as error:
            category = _classify_error(str(error))
            self._save_registration_failure(
                item_id,
                registration_run.id,
                account_data["email"],
                str(error),
            )
            _emit(
                self.job_id,
                "registration_failed",
                f"注册失败 {account_data['email']}: {error}",
                level="error",
                data={"item_id": item_id, "email": account_data["email"]},
            )
            if category == "network":
                self._record_network_failure()
            return False

        return self._complete_post_registration(
            item_id,
            credential,
            export,
            card_code,
            account_data["email"],
        )

    def _resume_saved_registration(
        self,
        item_id: str,
        export: dict[str, Any],
        card_code: str | None,
    ) -> bool | None:
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            if item is None:
                return False
            if item.status == PipelineItemStatus.COMPLETED:
                return True
            if not item.registration_run_id or not item.account_email:
                return None
            registration_run = session.get(RegistrationRun, item.registration_run_id)
            credential = session.get(Credential, item.account_email)
            if (
                registration_run is None
                or registration_run.status != RunStatus.SUCCEEDED
                or credential is None
            ):
                return None
            value = {
                field: getattr(credential, field)
                for field in (
                    "email",
                    "password",
                    "access_token",
                    "session_token",
                    "refresh_token",
                    "id_token",
                    "device_id",
                    "cookie_header",
                    "totp_secret",
                )
            }
            item.status = PipelineItemStatus.REGISTERED
            item.error = None
            session.commit()
        _emit(
            self.job_id,
            "post_registration_resumed",
            f"继续执行注册后任务 {item.account_email}",
            data={"item_id": item_id, "email": item.account_email},
        )
        return self._complete_post_registration(
            item_id,
            value,
            export,
            card_code,
            item.account_email,
        )

    def _complete_post_registration(
        self,
        item_id: str,
        credential: dict[str, Any],
        export: dict[str, Any],
        card_code: str | None,
        email: str,
    ) -> bool:
        try:
            self._run_export(credential, export)
            if card_code:
                self._run_kakao(item_id, credential, card_code)
            else:
                self._mark_item_completed(item_id)
        except Exception as error:
            self._save_post_registration_failure(item_id, str(error))
            _emit(
                self.job_id,
                "post_registration_failed",
                f"注册已成功，后置任务失败 {email}: {error}",
                level="error",
                data={"item_id": item_id, "email": email},
            )
        return True

    def _record_network_failure(self) -> None:
        with self._failure_lock:
            self._consecutive_network_failures += 1
            failures = self._consecutive_network_failures
        if failures < 5:
            return
        with SessionLocal() as session:
            run = session.get(PipelineRun, self.run_id)
            if run is not None and run.status == PipelineStatus.RUNNING:
                run.status = PipelineStatus.PAUSED
                session.commit()
                _emit(
                    self.job_id,
                    "circuit_breaker_opened",
                    "连续 5 次网络错误，流水线已自动暂停",
                    level="warning",
                    data={"consecutive_network_failures": failures},
                )

    def _mark_item_completed(self, item_id: str) -> None:
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            if item is not None:
                item.status = PipelineItemStatus.COMPLETED
                item.error = None
            session.commit()

    def _save_post_registration_failure(self, item_id: str, message: str) -> None:
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            if item is not None:
                item.status = PipelineItemStatus.FAILED
                item.error = f"注册成功，后置任务失败：{message}"
            session.commit()

    def _save_registration_success(
        self,
        item_id: str,
        registration_run_id: str,
        value: dict[str, Any],
    ) -> None:
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            registration_run = session.get(RegistrationRun, registration_run_id)
            if item is None or registration_run is None:
                return
            email = str(value.get("email") or item.account_email or "").lower()
            credential = session.get(Credential, email)
            if credential is None:
                credential = Credential(email=email)
                session.add(credential)
            for field in (
                "password",
                "access_token",
                "session_token",
                "refresh_token",
                "id_token",
                "device_id",
                "cookie_header",
                "totp_secret",
            ):
                setattr(credential, field, value.get(field) or None)
            security = value.get("security")
            if isinstance(security, dict):
                credential.metadata_json = {
                    **credential.metadata_json,
                    "account_security": security,
                }
            registration_run.status = RunStatus.SUCCEEDED
            registration_run.email = email
            registration_run.finished_at = utc_now()
            item.status = PipelineItemStatus.REGISTERED
            item.account_email = email
            account = session.get(OutlookAccount, item.account_email)
            if account is not None:
                account.status = AccountStatus.DONE
                account.finished_at = utc_now()
                account.failure_reason = None
            session.commit()

    def _save_registration_failure(
        self,
        item_id: str,
        registration_run_id: str,
        email: str,
        message: str,
    ) -> None:
        category = _classify_error(message)
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            registration_run = session.get(RegistrationRun, registration_run_id)
            account = session.get(OutlookAccount, email)
            if item is not None:
                item.status = PipelineItemStatus.FAILED
                item.error = message
            if registration_run is not None:
                registration_run.status = RunStatus.FAILED
                registration_run.error_category = category
                registration_run.error = message
                registration_run.finished_at = utc_now()
            if account is not None:
                account.status = (
                    AccountStatus.AVAILABLE if category == "network" else AccountStatus.FAILED
                )
                account.claimed_at = None if category == "network" else account.claimed_at
                account.failure_reason = None if category == "network" else message
                account.finished_at = None if category == "network" else utc_now()
            session.commit()

    def _run_export(
        self,
        credential: dict[str, Any],
        export: dict[str, Any],
    ) -> None:
        if not any(export.get(name, {}).get("enabled") for name in ("cpa", "sub2api")):
            return
        result = _legacy_call(
            {"action": "export", "credential": credential, "export": export},
            timeout=300,
            job_id=self.job_id,
        )
        target_results = dict(result.get("results") or {})
        failed = any(
            export.get(name, {}).get("enabled") and not target_results.get(name, {}).get("ok")
            for name in ("cpa", "sub2api")
        )
        level = "error" if failed or not result.get("ok") else "info"
        _emit(
            self.job_id,
            "export_finished",
            "自动导出存在失败" if failed else "自动导出完成",
            level=level,
            data=target_results,
        )

    def _run_kakao(
        self,
        item_id: str,
        credential: dict[str, Any],
        card_code: str,
    ) -> None:
        access_token = str(credential.get("access_token") or "")
        if not access_token:
            raise RuntimeError("注册结果缺少 Access Token")
        with SessionLocal() as session:
            settings = SettingsService(session).kakao_internal()
            card = session.scalar(select(KakaoCard).where(KakaoCard.code == card_code))
            if card is None:
                raise RuntimeError("已分配卡密不存在")
        client = KakaoClient(settings.base_url, settings.timeout)
        eligibility = payload_tasks(client.check_eligibility([access_token]))
        eligible = next((item for item in eligibility if item.get("index") in (0, "0")), None)
        if eligible is None and eligibility:
            eligible = eligibility[0]
        if not eligible or eligible.get("eligible") is not True:
            with SessionLocal() as session:
                item = session.get(PipelineItem, item_id)
                if item is not None:
                    item.status = PipelineItemStatus.SKIPPED
                    item.eligibility_state = str((eligible or {}).get("state") or "unknown")
                    item.error = str((eligible or {}).get("error") or "") or None
                session.commit()
            return
        payload = client.create_tasks(
            card=card_code,
            access_tokens=[access_token],
            plan_type=settings.plan_type,
            promo_code=settings.promo_code,
        )
        tasks = payload_tasks(payload)
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            run = session.get(PipelineRun, self.run_id)
            card = session.scalar(select(KakaoCard).where(KakaoCard.code == card_code))
            if item is None or run is None or card is None:
                return
            created = 0
            for task in tasks:
                upstream_id = str(task.get("job_id") or task.get("id") or "")
                if not upstream_id:
                    continue
                status_value = str(task.get("status") or "queued").lower()
                try:
                    task_status = KakaoTaskStatus(status_value)
                except ValueError:
                    task_status = KakaoTaskStatus.QUEUED
                existing = session.scalar(
                    select(KakaoTask).where(KakaoTask.upstream_job_id == upstream_id)
                )
                if existing is None:
                    session.add(
                        KakaoTask(
                            upstream_job_id=upstream_id,
                            pipeline_run_id=self.run_id,
                            pipeline_item_id=item_id,
                            card_id=card.id,
                            email=item.account_email or "",
                            status=task_status,
                            payment_status=task.get("payment_status"),
                            card_charged=task.get("card_charged"),
                            payment_url=task.get("payment_url"),
                            error=task.get("error"),
                            upstream_payload=task,
                        )
                    )
                    created += 1
            allocation = session.get(
                PipelineCardAllocation,
                (self.run_id, card.id),
            )
            if allocation is not None:
                allocation.created_count += created
            run.kakao_task_count += created
            item.status = PipelineItemStatus.COMPLETED
            session.commit()
        _emit(
            self.job_id,
            "kakao_submitted",
            f"Kakao 任务已提交：{len(tasks)}",
            data={"item_id": item_id},
        )


class WorkerManager:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.worker_id = f"local-{os.getpid()}"
        self._next_kakao_sync = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="pipeline-job-worker",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _claim(self) -> Job | None:
        now = utc_now()
        with SessionLocal() as session:
            candidate = (
                select(Job.id)
                .where(
                    Job.kind == "pipeline.run",
                    or_(
                        Job.status == JobStatus.QUEUED,
                        (Job.status == JobStatus.RUNNING) & (Job.lease_expires_at < now),
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
    ) -> None:
        with SessionLocal() as session:
            job = session.get(Job, job_id)
            if job is None or job.status == JobStatus.CANCELED:
                return
            if error and job.attempts < job.max_attempts:
                job.status = JobStatus.QUEUED
                delay = min(300, 5 * (2 ** max(0, job.attempts - 1)))
                job.available_at = utc_now() + timedelta(seconds=delay)
                job.error = error
            else:
                job.status = JobStatus.FAILED if error else JobStatus.SUCCEEDED
                job.error = error
                job.result = result or {}
                job.finished_at = utc_now()
            job.lease_owner = None
            job.lease_expires_at = None
            session.commit()

    def _heartbeat(self, job_id: str, stopped: threading.Event) -> None:
        while not stopped.wait(30):
            with SessionLocal() as session:
                job = session.get(Job, job_id)
                if (
                    job is None
                    or job.status != JobStatus.RUNNING
                    or job.lease_owner != self.worker_id
                ):
                    return
                job.lease_expires_at = utc_now() + timedelta(minutes=2)
                session.commit()

    def _sync_kakao_tasks(self) -> None:
        with SessionLocal() as session:
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
                    status_value = str(value.get("status") or "queued").lower()
                    try:
                        task.status = KakaoTaskStatus(status_value)
                    except ValueError:
                        task.status = KakaoTaskStatus.QUEUED
                    task.payment_status = str(value.get("payment_status") or "") or None
                    charged = value.get("card_charged")
                    task.card_charged = charged if isinstance(charged, bool) else None
                    task.payment_url = str(value.get("payment_url") or "") or None
                    task.error = str(value.get("error") or "") or None
                    task.upstream_payload = value
            session.commit()

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= self._next_kakao_sync:
                self._next_kakao_sync = now + 15
                with suppress(Exception):
                    self._sync_kakao_tasks()
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
                run_id = str(job.payload.get("pipeline_run_id") or "")
                retry_item_ids = job.payload.get("retry_item_ids")
                item_ids = (
                    [str(value) for value in retry_item_ids]
                    if isinstance(retry_item_ids, list)
                    else None
                )
                result = PipelineExecutor(job.id, run_id, item_ids).execute()
                self._finish(job.id, result=result)
            except Exception as error:
                _emit(job.id, "pipeline_failed", str(error), level="error")
                with SessionLocal() as session:
                    run_id = str(job.payload.get("pipeline_run_id") or "")
                    run = session.get(PipelineRun, run_id)
                    if run is not None and run.status != PipelineStatus.CANCELED:
                        run.status = PipelineStatus.FAILED
                        run.finished_at = utc_now()
                    session.commit()
                self._finish(job.id, error=str(error))
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=1)
