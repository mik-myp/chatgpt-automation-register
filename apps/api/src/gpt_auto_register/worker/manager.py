from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.redaction import redact_text, redact_value
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
    PipelineRunKind,
    PipelineStatus,
)
from gpt_auto_register.db.result import affected_rows
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.cards.allocator import CardAllocator, card_allocation_guard
from gpt_auto_register.modules.kakao.client import KakaoClient, payload_tasks
from gpt_auto_register.modules.kakao.state import (
    apply_upstream,
    completed_extraction_emails,
    synchronized_kakao_state,
)
from gpt_auto_register.modules.settings.maintenance import cleanup_storage
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.runtime_gateway import runtime_call

_EVENT_LOCK = threading.Lock()


def _classify_error(message: str) -> str:
    value = message.lower()
    account_patterns = (
        "wrong_email_otp_code",
        "invalid_grant",
        "imap xoauth2",
        "outlook otp timeout",
        "outlook imap account unusable",
        "user is authenticated but not connected",
        "outlook refresh failed",
        "authentication failed",
        "authenticate failed",
        "registration_disallowed",
        "邮件链接 otp timeout",
        "已有账号",
        "账号被",
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
        "connection aborted",
        "remote disconnected",
        "max retries exceeded",
        "csrf token 获取失败",
        "csrf token 失败",
        "/sentinel/req",
        "sentinel /req",
        "sentinel quickjs",
        "check_proxy 失败",
        "网络预检查",
        "curl: (35)",
        "curl: (28)",
        "curl: (6)",
        "curl: (7)",
        "invalid_state",
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
    with _EVENT_LOCK:
        for _ in range(5):
            with SessionLocal() as session:
                sequence = (
                    session.scalar(
                        select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id)
                    )
                    or 0
                ) + 1
                session.add(
                    JobEvent(
                        job_id=job_id,
                        sequence=sequence,
                        level=level,
                        event_type=event_type,
                        message=redact_text(message, limit=4000),
                        data=redact_value(data or {}),
                    )
                )
                try:
                    session.commit()
                    return
                except IntegrityError:
                    session.rollback()


def _legacy_call(
    payload: dict[str, Any],
    timeout: int = 1800,
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    max_lines = 2000
    with SessionLocal() as session, suppress(Exception):
        max_lines = SettingsService(session).maintenance_internal().max_runtime_log_lines
    sink = (lambda line: _emit(job_id, "runtime_log", line, level="debug")) if job_id else None
    return runtime_call(payload, timeout, log_sink=sink, max_lines=max_lines)


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

        if run.kind == PipelineRunKind.KAKAO:
            return self._execute_kakao_pipeline(item_ids)

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
                run.status = (
                    PipelineStatus.FAILED
                    if total_registered == 0 and total_failed > 0
                    else PipelineStatus.COMPLETED
                )
                run.finished_at = utc_now()
            session.commit()
        _emit(
            self.job_id,
            "pipeline_finished",
            f"流水线执行完成：成功 {success}，失败 {failed}",
            data={"registered": success, "failed": failed},
        )
        return {"status": "completed", "registered": success, "failed": failed}

    def _execute_kakao_pipeline(self, item_ids: list[str]) -> dict[str, Any]:
        _emit(self.job_id, "pipeline_started", "Kakao 流水线开始执行")
        card_codes = self._allocate_cards(item_ids)
        with ThreadPoolExecutor(max_workers=min(10, len(item_ids) or 1)) as executor:
            futures = {
                executor.submit(
                    self._execute_kakao_item,
                    item_id,
                    card_codes[item_id],
                ): item_id
                for item_id in item_ids
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    _emit(
                        self.job_id,
                        "kakao_item_failed",
                        str(error),
                        level="error",
                        data={"item_id": futures[future]},
                    )

        with SessionLocal() as session:
            run = session.get(PipelineRun, self.run_id)
            if run is None:
                raise RuntimeError("流水线轮次已被删除")
            statuses = list(
                session.scalars(
                    select(PipelineItem.status).where(
                        PipelineItem.pipeline_run_id == self.run_id
                    )
                )
            )
            completed = sum(value == PipelineItemStatus.COMPLETED for value in statuses)
            skipped = sum(value == PipelineItemStatus.SKIPPED for value in statuses)
            failed = sum(value == PipelineItemStatus.FAILED for value in statuses)
            run.registered_count = completed
            run.failed_count = failed + skipped
            if run.status != PipelineStatus.CANCELED:
                run.status = (
                    PipelineStatus.FAILED
                    if completed == 0 and failed + skipped > 0
                    else PipelineStatus.COMPLETED
                )
                run.finished_at = utc_now()
            created = run.kakao_task_count
            session.commit()
        _emit(
            self.job_id,
            "pipeline_finished",
            f"Kakao 流水线执行完成：完成 {completed}，跳过 {skipped}，失败 {failed}",
            data={
                "completed": completed,
                "skipped": skipped,
                "failed": failed,
                "tasks": created,
            },
        )
        return {
            "status": "completed",
            "completed": completed,
            "skipped": skipped,
            "failed": failed,
            "tasks": created,
        }

    def _execute_kakao_item(self, item_id: str, card_code: str) -> None:
        if not self._wait_until_runnable():
            return
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            if item is None or not item.account_email:
                return
            if item.status == PipelineItemStatus.COMPLETED:
                return
            credential = session.get(Credential, item.account_email)
            if credential is None or not credential.access_token:
                item.status = PipelineItemStatus.FAILED
                item.error = "注册结果缺少 Access Token"
                session.commit()
                return
            email = item.account_email
            credential_value = {
                "email": credential.email,
                "access_token": credential.access_token,
            }
            item.status = PipelineItemStatus.SUBMITTING
            item.error = None
            session.commit()
        try:
            self._run_kakao(item_id, credential_value, card_code)
        except Exception as error:
            self._record_kakao_failure(card_code)
            with SessionLocal() as session:
                session.execute(
                    update(PipelineItem)
                    .where(
                        PipelineItem.id == item_id,
                        PipelineItem.pipeline_run_id.in_(
                            select(PipelineRun.id).where(
                                PipelineRun.id == self.run_id,
                                PipelineRun.status != PipelineStatus.CANCELED,
                            )
                        ),
                    )
                    .values(status=PipelineItemStatus.FAILED, error=str(error))
                )
                session.commit()
            _emit(
                self.job_id,
                "kakao_item_failed",
                f"Kakao 任务提交失败 {email}: {error}",
                level="error",
                data={"item_id": item_id, "email": email},
            )

    def _allocate_cards(self, item_ids: list[str]) -> dict[str, str]:
        with card_allocation_guard(), SessionLocal() as session:
            requested_items = list(
                session.scalars(select(PipelineItem).where(PipelineItem.id.in_(item_ids)))
            )
            run_items = list(
                session.scalars(
                    select(PipelineItem).where(PipelineItem.pipeline_run_id == self.run_id)
                )
            )
            reserved_counts = {
                card.code: allocation.allocated_count
                for allocation, card in session.execute(
                    select(PipelineCardAllocation, KakaoCard)
                    .join(KakaoCard, KakaoCard.id == PipelineCardAllocation.card_id)
                    .where(PipelineCardAllocation.pipeline_run_id == self.run_id)
                )
            }
            snapshot_counts: dict[str, int] = {}
            for item in run_items:
                if item.card_code_snapshot:
                    snapshot_counts[item.card_code_snapshot] = (
                        snapshot_counts.get(item.card_code_snapshot, 0) + 1
                    )
            if (
                len(requested_items) == len(item_ids)
                and all(item.card_code_snapshot for item in requested_items)
                and all(
                    reserved_counts.get(code, 0) >= count for code, count in snapshot_counts.items()
                )
            ):
                reserved_mapping = {
                    item.id: str(item.card_code_snapshot) for item in requested_items
                }
                session.close()
                _emit(
                    self.job_id,
                    "cards_allocated",
                    f"使用创建流水线时预留的 {len(reserved_mapping)} 个卡密名额",
                )
                return reserved_mapping
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
                allocated_item = session.get(PipelineItem, item_id)
                if allocated_item is not None:
                    allocated_item.card_code_snapshot = code
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
                        allocated_count=0,
                        created_count=0,
                        duplicate_count=0,
                        failed_count=0,
                    )
                    session.add(allocation)
                allocation.allocated_count = (allocation.allocated_count or 0) + count
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
                item.mail_url_snapshot = account.mail_url
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
            result: dict[str, Any] = {}
            for attempt in range(3):
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
                error_message = str(result.get("error") or "")
                if result.get("ok") or "invalid_state" not in error_message.lower():
                    break
                if attempt < 2:
                    _emit(
                        self.job_id,
                        "registration_retry",
                        f"注册会话失效，正在使用全新会话重试（{attempt + 1}/2）",
                        level="warning",
                        data={"item_id": item_id, "email": account_data["email"]},
                    )
                    time.sleep(attempt + 1)
            if not result.get("ok"):
                trace = str(result.get("traceback") or "").strip()
                if trace:
                    _emit(
                        self.job_id,
                        "runtime_traceback",
                        trace[-12000:],
                        level="error",
                        data={"item_id": item_id, "email": account_data["email"]},
                    )
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
            else:
                with self._failure_lock:
                    self._consecutive_network_failures = 0
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
        if not self._wait_until_runnable():
            return True
        try:
            self._run_export(credential, export)
            if card_code:
                if not self._wait_until_runnable():
                    return True
                try:
                    self._run_kakao(item_id, credential, card_code)
                except Exception:
                    self._record_kakao_failure(card_code)
                    raise
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

    def _record_kakao_failure(self, card_code: str) -> None:
        with SessionLocal() as session:
            card = session.scalar(select(KakaoCard).where(KakaoCard.code == card_code))
            if card is None:
                return
            allocation = session.get(PipelineCardAllocation, (self.run_id, card.id))
            if allocation is not None:
                allocation.failed_count = (allocation.failed_count or 0) + 1
            session.commit()

    def _record_network_failure(self) -> None:
        with self._failure_lock:
            self._consecutive_network_failures += 1
            failures = self._consecutive_network_failures
        if failures < 3:
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
            session.execute(
                update(PipelineItem)
                .where(
                    PipelineItem.id == item_id,
                    PipelineItem.pipeline_run_id.in_(
                        select(PipelineRun.id).where(
                            PipelineRun.id == self.run_id,
                            PipelineRun.status != PipelineStatus.CANCELED,
                        )
                    ),
                )
                .values(status=PipelineItemStatus.COMPLETED, error=None)
            )
            session.commit()

    def _save_post_registration_failure(self, item_id: str, message: str) -> None:
        with SessionLocal() as session:
            session.execute(
                update(PipelineItem)
                .where(
                    PipelineItem.id == item_id,
                    PipelineItem.pipeline_run_id.in_(
                        select(PipelineRun.id).where(
                            PipelineRun.id == self.run_id,
                            PipelineRun.status != PipelineStatus.CANCELED,
                        )
                    ),
                )
                .values(
                    status=PipelineItemStatus.FAILED,
                    error=f"注册成功，后置任务失败：{message}",
                )
            )
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
                credential = Credential(email=email, metadata_json={})
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
                    **(credential.metadata_json or {}),
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
            item = session.get(PipelineItem, item_id)
            email = item.account_email if item is not None else str(credential.get("email") or "")
            if email and email.strip().lower() in completed_extraction_emails(session, [email]):
                if item is not None:
                    item.status = PipelineItemStatus.COMPLETED
                    item.eligibility_state = "already_extracted"
                    item.error = None
                session.commit()
                _emit(
                    self.job_id,
                    "kakao_skipped",
                    f"Kakao 提取已跳过，邮箱已有支付链接：{email}",
                    data={"item_id": item_id, "email": email, "reason": "already_extracted"},
                )
                return
            settings = SettingsService(session).kakao_internal()
            card = session.scalar(select(KakaoCard).where(KakaoCard.code == card_code))
            if card is None:
                raise RuntimeError("已分配卡密不存在")
        client = KakaoClient(settings.base_url, settings.timeout)
        eligibility = payload_tasks(client.check_eligibility([access_token]))
        eligible = next((item for item in eligibility if item.get("index") in (0, "0")), None)
        if eligible is None and eligibility:
            eligible = eligibility[0]
        eligible_payload = eligible or {}
        eligibility_state = str(eligible_payload.get("state") or "unknown")
        eligibility_error = str(eligible_payload.get("error") or "")
        is_eligible = (
            bool(eligible_payload)
            and eligible_payload.get("eligible") is True
            and eligibility_state == "eligible"
            and not eligibility_error
        )
        if not self._wait_until_runnable():
            return
        if not is_eligible:
            with SessionLocal() as session:
                item = session.get(PipelineItem, item_id)
                if item is not None:
                    changed = affected_rows(
                        session.execute(
                            update(PipelineItem)
                            .where(
                                PipelineItem.id == item_id,
                                PipelineItem.pipeline_run_id.in_(
                                    select(PipelineRun.id).where(
                                        PipelineRun.id == self.run_id,
                                        PipelineRun.status != PipelineStatus.CANCELED,
                                    )
                                ),
                            )
                            .values(
                                status=PipelineItemStatus.SKIPPED,
                                eligibility_state=eligibility_state,
                                error=eligibility_error or None,
                            )
                        )
                    )
                    saved = session.get(Credential, item.account_email)
                    if changed and saved is not None:
                        saved.metadata_json = {
                            **(saved.metadata_json or {}),
                            "kakao_pipeline": {
                                "status": "skipped",
                                "eligible": False,
                                "state": eligibility_state,
                                "error": eligibility_error,
                                "checked_at": utc_now().isoformat(),
                                "job_ids": [],
                                "active_duplicate_job_ids": [],
                            },
                        }
                session.commit()
            return
        payload = client.create_tasks(
            card=card_code,
            access_tokens=[access_token],
            plan_type=settings.plan_type,
            promo_code=settings.promo_code,
        )
        if isinstance(payload, dict):
            raw_tasks: list[object] = (
                [payload] if payload.get("job_id") or payload.get("id") else []
            )
            if not raw_tasks:
                for key in ("tasks", "items", "results"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        raw_tasks = [*raw_tasks, *value]
            raw_duplicates = payload.get("active_duplicates")
            tasks = (
                [item for item in raw_tasks if isinstance(item, dict)]
                if isinstance(raw_tasks, list)
                else []
            )
            duplicates = (
                [item for item in raw_duplicates if isinstance(item, dict)]
                if isinstance(raw_duplicates, list)
                else []
            )
        else:
            tasks = payload_tasks(payload)
            duplicates = []
        task_ids = [str(task.get("job_id") or task.get("id") or "") for task in tasks]
        duplicate_ids = [str(task.get("job_id") or task.get("id") or "") for task in duplicates]
        task_ids = [value for value in task_ids if value]
        duplicate_ids = [value for value in duplicate_ids if value]
        with SessionLocal() as session:
            item = session.get(PipelineItem, item_id)
            run = session.get(PipelineRun, self.run_id)
            card = session.scalar(select(KakaoCard).where(KakaoCard.code == card_code))
            if item is None or run is None or card is None:
                return
            for task in [*tasks, *duplicates]:
                upstream_id = str(task.get("job_id") or task.get("id") or "")
                if not upstream_id:
                    continue
                existing = session.scalar(
                    select(KakaoTask).where(KakaoTask.upstream_job_id == upstream_id)
                )
                if existing is None:
                    saved_task = KakaoTask(
                        upstream_job_id=upstream_id,
                        pipeline_run_id=self.run_id,
                        pipeline_item_id=item_id,
                        card_id=card.id,
                        card_code_snapshot=card.code,
                        email=item.account_email or "",
                    )
                    session.add(saved_task)
                    apply_upstream(saved_task, task, session)
            allocation = session.get(
                PipelineCardAllocation,
                (self.run_id, card.id),
            )
            if allocation is not None:
                allocation.created_count = (allocation.created_count or 0) + len(task_ids)
                allocation.duplicate_count = (allocation.duplicate_count or 0) + len(duplicate_ids)
            run.kakao_task_count = (run.kakao_task_count or 0) + len(task_ids)
            session.execute(
                update(PipelineItem)
                .where(
                    PipelineItem.id == item_id,
                    PipelineItem.pipeline_run_id.in_(
                        select(PipelineRun.id).where(
                            PipelineRun.id == self.run_id,
                            PipelineRun.status != PipelineStatus.CANCELED,
                        )
                    ),
                )
                .values(status=PipelineItemStatus.COMPLETED, error=None)
            )
            item.eligibility_state = eligibility_state
            saved = session.get(Credential, item.account_email)
            if saved is not None:
                saved.metadata_json = {
                    **(saved.metadata_json or {}),
                    "kakao_pipeline": {
                        "status": (
                            "created" if task_ids else "duplicate" if duplicate_ids else "submitted"
                        ),
                        "eligible": True,
                        "state": eligibility_state,
                        "error": "",
                        "checked_at": utc_now().isoformat(),
                        "job_ids": task_ids,
                        "active_duplicate_job_ids": duplicate_ids,
                        "card_id": card.id,
                    },
                }
            session.commit()
        _emit(
            self.job_id,
            "kakao_submitted",
            f"Kakao 任务已提交：新建 {len(task_ids)}，执行中重复 {len(duplicate_ids)}",
            data={
                "item_id": item_id,
                "created": len(task_ids),
                "duplicates": len(duplicate_ids),
            },
        )


class AccountSecurityExecutor:
    def __init__(self, job_id: str, payload: dict[str, Any]) -> None:
        self.job_id = job_id
        self.action = str(payload.get("action") or "")
        self.emails = [str(value).strip().lower() for value in payload.get("emails", [])]
        self.pipeline_run_id = str(payload.get("pipeline_run_id") or "")

    def execute(self) -> dict[str, Any]:
        succeeded = failed = skipped = 0
        self._start_pipeline()
        self._save_progress(succeeded, failed, skipped)
        for email in self.emails:
            if not self._job_running():
                break
            self._mark_item_running(email)
            item_error = ""
            item_skipped = False
            try:
                if self._execute_one(email):
                    succeeded += 1
                else:
                    skipped += 1
                    item_skipped = True
            except Exception as error:
                failed += 1
                item_error = str(error)
                _emit(
                    self.job_id,
                    "account_security_failed",
                    f"账号安全操作失败 {email}: {error}",
                    level="error",
                    data={"email": email, "action": self.action},
                )
            self._save_item_progress(email, item_error, skipped=item_skipped)
            self._save_progress(succeeded, failed, skipped)
        self._finish_pipeline()
        return {
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "total": len(self.emails),
        }

    def _save_progress(self, succeeded: int, failed: int, skipped: int) -> None:
        with SessionLocal() as session:
            job = session.get(Job, self.job_id)
            if job is None or job.status != JobStatus.RUNNING:
                return
            job.result = {
                "succeeded": succeeded,
                "failed": failed,
                "skipped": skipped,
                "total": len(self.emails),
            }
            session.commit()

    def _job_running(self) -> bool:
        with SessionLocal() as session:
            job = session.get(Job, self.job_id)
            return job is not None and job.status == JobStatus.RUNNING

    def _start_pipeline(self) -> None:
        if not self.pipeline_run_id:
            return
        with SessionLocal() as session:
            run = session.get(PipelineRun, self.pipeline_run_id)
            if run is None or run.status == PipelineStatus.CANCELED:
                return
            run.status = PipelineStatus.RUNNING
            run.started_at = run.started_at or utc_now()
            session.commit()

    def _mark_item_running(self, email: str) -> None:
        if not self.pipeline_run_id:
            return
        with SessionLocal() as session:
            item = session.scalar(
                select(PipelineItem).where(
                    PipelineItem.pipeline_run_id == self.pipeline_run_id,
                    PipelineItem.account_email == email,
                )
            )
            if item is not None:
                item.status = PipelineItemStatus.REGISTERING
                item.error = None
                item.security_error = None
                session.commit()

    def _save_item_progress(self, email: str, error: str, *, skipped: bool) -> None:
        if not self.pipeline_run_id:
            return
        with SessionLocal() as session:
            item = session.scalar(
                select(PipelineItem).where(
                    PipelineItem.pipeline_run_id == self.pipeline_run_id,
                    PipelineItem.account_email == email,
                )
            )
            credential = session.get(Credential, email)
            if item is None:
                return
            metadata = credential.metadata_json if credential else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            security = metadata.get("account_security")
            security = security if isinstance(security, dict) else {}
            password = security.get("password")
            password = password if isinstance(password, dict) else {}
            mfa = security.get("mfa")
            mfa = mfa if isinstance(mfa, dict) else {}
            registration = SettingsService(session).registration_internal()
            password_status = str(
                password.get("status")
                or ("set" if credential and credential.password else "not_set")
            )
            mfa_status = str(
                mfa.get("status")
                or ("enabled" if credential and credential.totp_secret else "not_enabled")
            )
            password_complete = (
                bool(credential and credential.password)
                or (registration.password_mode == "fixed" and bool(registration.fixed_password))
            ) and password_status in {"set", "available"}
            mfa_complete = bool(credential and credential.totp_secret) and mfa_status == "enabled"
            item.password_status = password_status
            item.mfa_status = mfa_status
            item.security_error = error or None
            item.error = error or None
            item.status = (
                PipelineItemStatus.SKIPPED
                if skipped and password_complete and mfa_complete
                else PipelineItemStatus.COMPLETED
                if password_complete and mfa_complete
                else PipelineItemStatus.FAILED
            )
            self._update_pipeline_counts(session)
            session.commit()

    def _update_pipeline_counts(self, session: Any) -> None:
        run = session.get(PipelineRun, self.pipeline_run_id)
        if run is None:
            return
        statuses = list(
            session.scalars(
                select(PipelineItem.status).where(
                    PipelineItem.pipeline_run_id == self.pipeline_run_id
                )
            )
        )
        run.registered_count = sum(
            value in {PipelineItemStatus.COMPLETED, PipelineItemStatus.SKIPPED}
            for value in statuses
        )
        run.failed_count = sum(value == PipelineItemStatus.FAILED for value in statuses)

    def _finish_pipeline(self) -> None:
        if not self.pipeline_run_id:
            return
        with SessionLocal() as session:
            run = session.get(PipelineRun, self.pipeline_run_id)
            if run is None or run.status == PipelineStatus.CANCELED:
                return
            self._update_pipeline_counts(session)
            run.status = (
                PipelineStatus.FAILED
                if run.registered_count == 0 and run.failed_count > 0
                else PipelineStatus.COMPLETED
            )
            run.finished_at = utc_now()
            session.commit()

    def _execute_one(self, email: str) -> bool:
        if self.action != "set_password_and_mfa":
            self._execute_action(email, self.action)
            return True

        with SessionLocal() as session:
            credential = session.get(Credential, email)
            if credential is None:
                raise RuntimeError("ChatGPT 凭据不存在")
            metadata = credential.metadata_json or {}
            security = dict(metadata.get("account_security") or {})
            password = dict(security.get("password") or {})
            mfa = dict(security.get("mfa") or {})
            registration = SettingsService(session).registration_internal()
            password_value_available = bool(credential.password) or (
                registration.password_mode == "fixed" and bool(registration.fixed_password)
            )
            password_status = str(
                password.get("status") or ("set" if credential.password else "not_set")
            )
            mfa_status = str(
                mfa.get("status") or ("enabled" if credential.totp_secret else "not_enabled")
            )
            password_complete = password_value_available and password_status in {
                "set",
                "available",
            }
            mfa_complete = bool(credential.totp_secret) and mfa_status == "enabled"

        if password_complete and mfa_complete:
            _emit(
                self.job_id,
                "account_security_skipped",
                f"密码和 MFA 均已完成，跳过 {email}",
                data={"email": email, "action": self.action},
            )
            return False
        if password_complete:
            _emit(
                self.job_id,
                "account_security_step_skipped",
                f"密码已设置，跳过密码操作 {email}",
                data={"email": email, "action": "set_password"},
            )
        else:
            self._execute_action(email, "set_password")
        if mfa_complete:
            _emit(
                self.job_id,
                "account_security_step_skipped",
                f"MFA 已启用，跳过 MFA 操作 {email}",
                data={"email": email, "action": "enable_mfa"},
            )
        else:
            self._execute_action(email, "enable_mfa")
        return True

    def _execute_action(self, email: str, action: str) -> None:
        try:
            self._run_action(email, action)
        except Exception as error:
            self._record(email, action, "failed", str(error))
            raise

    def _run_action(self, email: str, action: str) -> None:
        with SessionLocal() as session:
            account = session.get(OutlookAccount, email)
            credential = session.get(Credential, email)
            if account is None or credential is None:
                raise RuntimeError("账号缺少邮箱或 ChatGPT 凭据")
            registration = SettingsService(session).registration_internal().model_dump()
            configured_password = (
                str(registration.get("fixed_password") or "")
                if registration.get("password_mode") == "fixed"
                else ""
            )
            proxy_pool = [
                value.strip()
                for value in str(registration.get("proxy_pool") or "").splitlines()
                if value.strip()
            ]
            if proxy_pool:
                digest = hashlib.sha256(email.encode("utf-8")).digest()
                registration["proxy"] = proxy_pool[
                    int.from_bytes(digest[:8], "big") % len(proxy_pool)
                ]
            if action == "enable_mfa":
                registration.update(password_mode="none", enable_authenticator_mfa=True)
            elif registration.get("password_mode") == "none":
                registration["password_mode"] = "random"
            mail = SettingsService(session).mail_internal()
            account_data = _account_payload(account)
            credential_data = {
                "password": credential.password or configured_password,
                "device_id": credential.device_id or "",
                "cookie_header": credential.cookie_header or "",
            }
            has_totp_secret = bool(credential.totp_secret)
        operation_label = "设置 ChatGPT 密码" if action == "set_password" else "启用或验证 MFA"
        _emit(
            self.job_id,
            "account_security_started",
            f"开始{operation_label} {email}",
            data={"email": email, "action": action},
        )
        if action == "enable_mfa" and has_totp_secret:
            result = _legacy_call(
                {
                    "action": "verify_mfa",
                    "credential": credential_data,
                    "proxy": registration.get("proxy", ""),
                },
                timeout=120,
                job_id=self.job_id,
            )
            if not result.get("verified"):
                raise RuntimeError(str(result.get("error") or "MFA 状态验证失败"))
            self._record(email, action, "enabled", "")
            _emit(
                self.job_id,
                "account_security_succeeded",
                f"MFA 服务端状态已验证 {email}",
                data={"email": email, "action": action},
            )
            return
        result = _legacy_call(
            {
                "action": action,
                "account": account_data,
                "credential": credential_data,
                "registration": registration,
                "mail": mail,
            },
            job_id=self.job_id,
        )
        value = dict(result.get("credential") or {})
        self._persist_session(email, value)
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or f"{operation_label}失败"))
        security = value.get("security") if isinstance(value.get("security"), dict) else {}
        security_key = "password" if action == "set_password" else "mfa"
        expected_status = "set" if action == "set_password" else "enabled"
        outcome = security.get(security_key) if isinstance(security, dict) else {}
        if not isinstance(outcome, dict) or outcome.get("status") != expected_status:
            raise RuntimeError(
                str((outcome or {}).get("error") or f"{operation_label}未由服务端确认")
            )
        with SessionLocal() as session:
            credential = session.get(Credential, email)
            if credential is None:
                raise RuntimeError("ChatGPT 凭据不存在")
            for field in (
                "access_token",
                "session_token",
                "refresh_token",
                "id_token",
                "device_id",
                "cookie_header",
            ):
                if value.get(field):
                    setattr(credential, field, value[field])
            if value.get("totp_secret"):
                credential.totp_secret = value["totp_secret"]
            if value.get("password"):
                credential.password = value["password"]
            credential.metadata_json = {
                **(credential.metadata_json or {}),
                "account_security": {
                    **dict((credential.metadata_json or {}).get("account_security") or {}),
                    security_key: outcome,
                },
            }
            session.commit()
        _emit(
            self.job_id,
            "account_security_succeeded",
            f"{operation_label}成功并验证 {email}",
            data={"email": email, "action": action},
        )

    def _record(
        self,
        email: str,
        action: str,
        status_value: str,
        error: str,
    ) -> None:
        with SessionLocal() as session:
            credential = session.get(Credential, email)
            if credential is None:
                return
            metadata = credential.metadata_json or {}
            security = dict(metadata.get("account_security") or {})
            key = "password" if action == "set_password" else "mfa"
            security[key] = {
                "requested": True,
                "status": status_value,
                "error": error,
            }
            credential.metadata_json = {**metadata, "account_security": security}
            session.commit()

    @staticmethod
    def _persist_session(email: str, value: dict[str, Any]) -> None:
        with SessionLocal() as session:
            credential = session.get(Credential, email)
            if credential is None:
                return
            changed = False
            for field in ("access_token", "session_token", "device_id", "cookie_header"):
                if value.get(field):
                    setattr(credential, field, value[field])
                    changed = True
            if changed:
                session.commit()


class WorkerManager:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.worker_id = f"local-{os.getpid()}"
        self._next_kakao_sync = 0.0
        self._next_maintenance = 0.0

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
                    Job.kind.in_(["pipeline.run", "account.security"]),
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
    ) -> None:
        with SessionLocal() as session:
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
                    session.commit()
                    return
            session.execute(
                update(Job)
                .where(*ownership)
                .values(
                    status=JobStatus.FAILED if error else JobStatus.SUCCEEDED,
                    error=error,
                    result=result or {},
                    finished_at=utc_now(),
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
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

    @synchronized_kakao_state
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
                    apply_upstream(task, value, session)
            session.commit()

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= self._next_kakao_sync:
                self._next_kakao_sync = now + 5
                with suppress(Exception):
                    self._sync_kakao_tasks()
            if now >= self._next_maintenance:
                self._next_maintenance = now + 3600
                with suppress(Exception), SessionLocal() as session:
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
                if job.kind == "account.security":
                    result = AccountSecurityExecutor(job.id, job.payload).execute()
                    failed = int(result.get("failed") or 0)
                    self._finish(
                        job.id,
                        result=result,
                        error=f"{failed} 个账号安全操作失败" if failed else None,
                    )
                    continue
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
