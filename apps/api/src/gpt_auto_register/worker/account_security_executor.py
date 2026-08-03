from __future__ import annotations

import hashlib
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import (
    Credential,
    OutlookAccount,
)
from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineStatus,
)
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.executor_support import (
    account_payload as _account_payload,
)
from gpt_auto_register.worker.executor_support import (
    emit as _emit,
)
from gpt_auto_register.worker.executor_support import (
    legacy_call as _legacy_call,
)
from gpt_auto_register.worker.runtime_gateway import RuntimeCanceledError


class AccountSecurityExecutor:
    def __init__(
        self,
        job_id: str,
        payload: dict[str, Any],
        cancel_event: threading.Event | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.job_id = job_id
        self.action = str(payload.get("action") or "")
        self.emails = [str(value).strip().lower() for value in payload.get("emails", [])]
        self.pipeline_run_id = str(payload.get("pipeline_run_id") or "")
        self._cancel_event = cancel_event or threading.Event()
        self._session_factory = session_factory or SessionLocal

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
            except RuntimeCanceledError:
                break
            except Exception as error:
                if self._cancel_event.is_set():
                    break
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
        with self._session_factory() as session:
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
        if self._cancel_event.is_set():
            return False
        with self._session_factory() as session:
            job = session.get(Job, self.job_id)
            return job is not None and job.status == JobStatus.RUNNING

    def _start_pipeline(self) -> None:
        if not self.pipeline_run_id:
            return
        with self._session_factory() as session:
            run = session.get(PipelineRun, self.pipeline_run_id)
            if run is None or run.status == PipelineStatus.CANCELED:
                return
            run.status = PipelineStatus.RUNNING
            run.started_at = run.started_at or utc_now()
            session.commit()

    def _mark_item_running(self, email: str) -> None:
        if not self.pipeline_run_id:
            return
        with self._session_factory() as session:
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
        with self._session_factory() as session:
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
        with self._session_factory() as session:
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

        with self._session_factory() as session:
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
        except RuntimeCanceledError:
            raise
        except Exception as error:
            self._record(email, action, "failed", str(error))
            raise

    def _run_action(self, email: str, action: str) -> None:
        with self._session_factory() as session:
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
                cancel_check=self._cancel_event.is_set,
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
            cancel_check=self._cancel_event.is_set,
        )
        if self._cancel_event.is_set():
            raise RuntimeCanceledError("协议运行已取消")
        value = dict(result.get("credential") or {})
        self._persist_session(email, value, self._session_factory)
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
        with self._session_factory() as session:
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
        with self._session_factory() as session:
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
    def _persist_session(
        email: str,
        value: dict[str, Any],
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        factory = session_factory or SessionLocal
        with factory() as session:
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
