from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import (
    AccountStatus,
    Credential,
    OutlookAccount,
    RegistrationRun,
    RunStatus,
)
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineRunKind,
    PipelineStatus,
)
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.executor_support import (
    account_payload as _account_payload,
)
from gpt_auto_register.worker.executor_support import (
    classify_error as _classify_error,
)
from gpt_auto_register.worker.executor_support import (
    emit as _emit,
)
from gpt_auto_register.worker.executor_support import (
    legacy_call as _legacy_call,
)
from gpt_auto_register.worker.pipeline_kakao_executor import (
    KakaoPipelineExecutorMixin,
    pair_kakao_proxy_assignments,
)
from gpt_auto_register.worker.proxy_service import (
    ProxyAllocator,
    ProxyApiError,
    emit_proxy_attempt,
)
from gpt_auto_register.worker.runtime_gateway import RuntimeCanceledError


class PipelineExecutor(KakaoPipelineExecutorMixin):
    NETWORK_CIRCUIT_BREAKER_THRESHOLD = 5

    def __init__(
        self,
        job_id: str,
        run_id: str,
        item_ids: list[str] | None = None,
        cancel_event: threading.Event | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.job_id = job_id
        self.run_id = run_id
        self.item_ids = item_ids
        self._failure_lock = threading.Lock()
        self._consecutive_network_failures = 0
        self._cancel_event = cancel_event or threading.Event()
        self._session_factory = session_factory or SessionLocal

    def execute(self) -> dict[str, Any]:
        with self._session_factory() as session:
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
            proxy_settings = settings_service.proxy_internal()
            item_query = select(PipelineItem.id).where(PipelineItem.pipeline_run_id == self.run_id)
            if self.item_ids is not None:
                item_query = item_query.where(PipelineItem.id.in_(self.item_ids))
            item_ids = list(session.scalars(item_query.order_by(PipelineItem.position)))
            session.commit()

        if run.kind == PipelineRunKind.KAKAO:
            return self._execute_kakao_pipeline(item_ids)

        _emit(self.job_id, "pipeline_started", "流水线开始执行")
        kakao_enabled = run.kakao_enabled
        try:
            proxy_batch = ProxyAllocator(
                proxy_settings,
                self._session_factory,
                self.job_id,
                "registration",
            ).allocate(item_ids)
        except ProxyApiError:
            proxy_batch = None
        proxy_assignments = proxy_batch.assignments if proxy_batch is not None else {}
        kakao_proxy_assignments: dict[str, list[tuple[str, str]]] = {}
        kakao_proxy_failures: dict[str, str] = {}
        if kakao_enabled:
            try:
                kakao_allocator = ProxyAllocator(
                    proxy_settings,
                    self._session_factory,
                    self.job_id,
                    "kakao",
                )
                kr_batch = kakao_allocator.allocate(item_ids, region="KR")
                vn_batch = kakao_allocator.allocate(item_ids, region="VN")
                kakao_proxy_assignments, kakao_proxy_failures = pair_kakao_proxy_assignments(
                    item_ids,
                    kr_batch.assignments,
                    vn_batch.assignments,
                )
            except ProxyApiError:
                pass
        runnable_item_ids = [item_id for item_id in item_ids if item_id in proxy_assignments]
        for item_id in item_ids:
            if item_id not in proxy_assignments:
                self._save_proxy_shortage(item_id, "注册步骤代理数量不足，账号未开始执行")
            elif kakao_enabled and item_id not in kakao_proxy_assignments:
                _emit(
                    self.job_id,
                    "kakao_proxy_allocation_failed",
                    kakao_proxy_failures.get(item_id, "Kakao KR/VN 代理对数量不足"),
                    level="error",
                    data={"item_id": item_id, "step": "kakao"},
                )
        concurrency = max(1, min(50, int(registration.get("concurrency") or 10)))
        success = failed = 0
        failed += len(item_ids) - len(runnable_item_ids)
        with ThreadPoolExecutor(
            max_workers=min(concurrency, len(runnable_item_ids) or 1)
        ) as executor:
            futures = {
                executor.submit(
                    self._execute_item,
                    item_id,
                    registration,
                    sms,
                    mail,
                    export,
                    kakao_enabled,
                    proxy_assignments[item_id],
                    kakao_proxy_assignments.get(item_id, []),
                ): item_id
                for item_id in runnable_item_ids
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

        with self._session_factory() as session:
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
            final_status = run.status.value
            session.commit()
        _emit(
            self.job_id,
            "pipeline_finished",
            f"流水线执行完成：成功 {success}，失败 {failed}",
            data={"registered": success, "failed": failed},
        )
        return {"status": final_status, "registered": success, "failed": failed}

    def _wait_until_runnable(self) -> bool:
        while True:
            if self._cancel_event.is_set():
                return False
            with self._session_factory() as session:
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
        kakao_enabled: bool,
        proxies: list[str],
        kakao_proxies: list[tuple[str, str]],
    ) -> bool:
        if not self._wait_until_runnable():
            return False
        resumed = self._resume_saved_registration(item_id, export, kakao_enabled, kakao_proxies)
        if resumed is not None:
            return resumed
        with self._session_factory() as session:
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
            item_config = {**registration, "proxy": proxies[0]}
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
            last_error = "注册失败"
            for attempt, proxy in enumerate(proxies, start=1):
                started_at = utc_now()
                item_config = {**registration, "proxy": proxy}
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
                        cancel_check=self._cancel_event.is_set,
                    )
                    last_error = str(result.get("error") or "注册失败")
                    succeeded = bool(result.get("ok"))
                except RuntimeCanceledError:
                    raise
                except Exception as error:
                    last_error = str(error)
                    result = {}
                    succeeded = False
                emit_proxy_attempt(
                    self._session_factory,
                    self.job_id,
                    email=str(account_data["email"]),
                    item_id=item_id,
                    step="registration",
                    attempt=attempt,
                    proxy=proxy,
                    started_at=started_at,
                    succeeded=succeeded,
                    error="" if succeeded else last_error,
                )
                if succeeded:
                    break
                if attempt < len(proxies):
                    _emit(
                        self.job_id,
                        "registration_retry",
                        f"注册失败，切换到第 {attempt + 1} 个预分配代理",
                        level="warning",
                        data={"item_id": item_id, "email": account_data["email"]},
                    )
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
                raise RuntimeError(last_error)
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
        except RuntimeCanceledError:
            self._save_registration_canceled(
                item_id,
                registration_run.id,
                account_data["email"],
            )
            return False
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
            kakao_enabled,
            account_data["email"],
            kakao_proxies,
        )

    def _resume_saved_registration(
        self,
        item_id: str,
        export: dict[str, Any],
        kakao_enabled: bool,
        kakao_proxies: list[tuple[str, str]],
    ) -> bool | None:
        with self._session_factory() as session:
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
            kakao_enabled,
            item.account_email,
            kakao_proxies,
        )

    def _complete_post_registration(
        self,
        item_id: str,
        credential: dict[str, Any],
        export: dict[str, Any],
        kakao_enabled: bool,
        email: str,
        kakao_proxies: list[tuple[str, str]],
    ) -> bool:
        if not self._wait_until_runnable():
            return True
        try:
            self._run_export(credential, export)
            if kakao_enabled:
                if not kakao_proxies:
                    raise RuntimeError("Kakao 步骤代理数量不足，账号未开始执行")
                if not self._wait_until_runnable():
                    return True
                last_error: Exception | None = None
                for attempt, (kr_proxy, vn_proxy) in enumerate(kakao_proxies, start=1):
                    started_at = utc_now()
                    proxy_label = f"KR={kr_proxy} | VN={vn_proxy}"
                    try:
                        self._run_kakao(
                            item_id,
                            credential,
                            kr_proxy=kr_proxy,
                            vn_proxy=vn_proxy,
                        )
                        emit_proxy_attempt(
                            self._session_factory,
                            self.job_id,
                            email=email,
                            item_id=item_id,
                            step="kakao",
                            attempt=attempt,
                            proxy=proxy_label,
                            started_at=started_at,
                            succeeded=True,
                        )
                        last_error = None
                        break
                    except Exception as error:
                        last_error = error
                        emit_proxy_attempt(
                            self._session_factory,
                            self.job_id,
                            email=email,
                            item_id=item_id,
                            step="kakao",
                            attempt=attempt,
                            proxy=proxy_label,
                            started_at=started_at,
                            succeeded=False,
                            error=str(error),
                        )
                if last_error is not None:
                    raise last_error
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

    def _save_proxy_shortage(self, item_id: str, reason: str) -> None:
        with self._session_factory() as session:
            item = session.get(PipelineItem, item_id)
            if item is None:
                return
            item.status = PipelineItemStatus.FAILED
            item.error = reason
            session.commit()
        _emit(
            self.job_id,
            "item_proxy_insufficient",
            reason,
            level="error",
            data={"item_id": item_id, "step": "registration"},
        )

    def _record_network_failure(self) -> None:
        with self._failure_lock:
            self._consecutive_network_failures += 1
            failures = self._consecutive_network_failures
        if failures < self.NETWORK_CIRCUIT_BREAKER_THRESHOLD:
            return
        with self._session_factory() as session:
            run = session.get(PipelineRun, self.run_id)
            if run is not None and run.status == PipelineStatus.RUNNING:
                run.status = PipelineStatus.PAUSED
                session.commit()
                _emit(
                    self.job_id,
                    "circuit_breaker_opened",
                    f"连续 {self.NETWORK_CIRCUIT_BREAKER_THRESHOLD} 次网络错误，流水线已自动暂停",
                    level="warning",
                    data={"consecutive_network_failures": failures},
                )

    def _mark_item_completed(self, item_id: str) -> None:
        with self._session_factory() as session:
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
        with self._session_factory() as session:
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
        with self._session_factory() as session:
            item = session.get(PipelineItem, item_id)
            registration_run = session.get(RegistrationRun, registration_run_id)
            run = session.get(PipelineRun, self.run_id)
            if (
                item is None
                or registration_run is None
                or run is None
                or run.status == PipelineStatus.CANCELED
                or self._cancel_event.is_set()
            ):
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

    def _save_registration_canceled(
        self,
        item_id: str,
        registration_run_id: str,
        email: str,
    ) -> None:
        with self._session_factory() as session:
            item = session.get(PipelineItem, item_id)
            registration_run = session.get(RegistrationRun, registration_run_id)
            account = session.get(OutlookAccount, email)
            if item is not None:
                item.status = PipelineItemStatus.SKIPPED
                item.error = "流水线已取消"
            if registration_run is not None:
                registration_run.status = RunStatus.CANCELED
                registration_run.error = "流水线已取消"
                registration_run.finished_at = utc_now()
            if account is not None and account.status == AccountStatus.IN_USE:
                account.status = AccountStatus.AVAILABLE
                account.claimed_at = None
            session.commit()

    def _save_registration_failure(
        self,
        item_id: str,
        registration_run_id: str,
        email: str,
        message: str,
    ) -> None:
        if self._cancel_event.is_set():
            self._save_registration_canceled(item_id, registration_run_id, email)
            return
        category = _classify_error(message)
        with self._session_factory() as session:
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
            cancel_check=self._cancel_event.is_set,
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
