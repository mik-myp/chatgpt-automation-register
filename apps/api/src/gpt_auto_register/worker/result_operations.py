from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.db.models.pipeline import PipelineItem
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.modules.results.plus_checker import check_plus
from gpt_auto_register.modules.results.schemas import RegistrationResultDetail
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.runtime_gateway import RuntimeCanceledError
from gpt_auto_register.worker.runtime_service import call_legacy_runtime


def _credential_payload(credential: Credential) -> dict[str, Any]:
    return {
        "email": credential.email,
        "password": credential.password or "",
        "access_token": credential.access_token or "",
        "session_token": credential.session_token or "",
        "refresh_token": credential.refresh_token or "",
        "id_token": credential.id_token or "",
        "device_id": credential.device_id or "",
        "cookie_header": credential.cookie_header or "",
        "totp_secret": credential.totp_secret or "",
    }


def _account_payload(account: OutlookAccount) -> dict[str, Any]:
    return {
        "email": account.email,
        "password": account.password or "",
        "client_id": account.client_id or "",
        "refresh_token": account.refresh_token or "",
        "mail_type": account.mail_type.value,
        "mail_url": account.mail_url or "",
    }


class ResultOperationExecutor:
    def __init__(
        self,
        job_id: str,
        payload: dict[str, Any],
        cancel_event: threading.Event,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.job_id = job_id
        self.payload = payload
        self.cancel_event = cancel_event
        self._session_factory = session_factory or SessionLocal

    def execute(self) -> dict[str, Any]:
        emails = self._resolve_emails()
        if self.payload.get("operation") == "plus_check":
            return self._check_plus(emails)
        if self.payload.get("operation") == "publish":
            return self._publish(emails)
        raise RuntimeError("不支持的注册结果后台任务")

    def _resolve_emails(self) -> list[str]:
        requested = [
            str(email).strip().lower()
            for email in self.payload.get("emails", [])
            if str(email).strip()
        ]
        with self._session_factory() as session:
            query = select(Credential.email).distinct().order_by(Credential.created_at.desc())
            pipeline_run_id = str(self.payload.get("pipeline_run_id") or "")
            if pipeline_run_id:
                query = query.join(
                    PipelineItem,
                    PipelineItem.account_email == Credential.email,
                ).where(PipelineItem.pipeline_run_id == pipeline_run_id)
            elif not self.payload.get("all"):
                query = query.where(Credential.email.in_(requested))
            emails = list(session.scalars(query))
            job = session.get(Job, self.job_id)
            if job is not None:
                job.payload = {**job.payload, "resolved_emails": emails}
                job.result = self._progress(total=len(emails))
                session.commit()
        return emails

    def _check_plus(self, emails: list[str]) -> dict[str, Any]:
        proxy = str(self.payload.get("proxy") or "")
        results: list[tuple[str, dict[str, object]]] = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(emails)))) as executor:
            futures = {executor.submit(self._check_one, email, proxy): email for email in emails}
            for future in as_completed(futures):
                if self.cancel_event.is_set():
                    raise RuntimeCanceledError("Plus 检查已取消")
                email = futures[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = {
                        "state": "error",
                        "label": "检查失败",
                        "is_plus": None,
                        "error": str(error),
                    }
                self._save_plus_result(email, result)
                results.append((email, result))
                self._save_progress_results(emails, results)
        return self._plus_result(emails, results)

    def _check_one(self, email: str, proxy: str) -> dict[str, object]:
        with self._session_factory() as session:
            credential = session.get(Credential, email)
            if credential is None:
                return {
                    "state": "no_credential",
                    "label": "凭据不存在",
                    "is_plus": None,
                    "error": "ChatGPT 凭据不存在，无法恢复授权",
                }
            access_token = credential.access_token or ""

        result: dict[str, object] = (
            check_plus(access_token, proxy)
            if access_token
            else {
                "state": "no_access_token",
                "label": "无 Access Token",
                "is_plus": None,
                "error": "缺少 Access Token，正在尝试恢复授权",
            }
        )
        if result.get("state") not in {"invalid_token", "no_access_token"}:
            return result
        if self.cancel_event.is_set():
            raise RuntimeCanceledError("Plus 检查已取消")

        recovery_errors: list[str] = []
        for mode in ("session", "login"):
            if self.cancel_event.is_set():
                raise RuntimeCanceledError("Plus 检查已取消")
            try:
                refreshed = self._refresh_authorization(email, proxy, mode)
            except RuntimeCanceledError:
                raise
            except Exception as error:
                recovery_errors.append(f"{mode}: {error}")
                continue
            result = check_plus(refreshed, proxy)
            if result.get("state") != "invalid_token":
                return {**result, "authorization_recovered": True, "recovery_mode": mode}
            recovery_errors.append(f"{mode}: 新授权仍返回 HTTP 401")
        return {
            **result,
            "error": "授权已失效，自动恢复失败"
            + (f"：{'；'.join(recovery_errors)}" if recovery_errors else ""),
        }

    def _refresh_authorization(self, email: str, proxy: str, mode: str) -> str:
        if self.cancel_event.is_set():
            raise RuntimeCanceledError("Plus 检查已取消")
        with self._session_factory() as session:
            credential = session.get(Credential, email)
            account = session.get(OutlookAccount, email)
            if credential is None:
                raise RuntimeError("凭据不存在")
            if mode == "session" and not (credential.session_token or credential.cookie_header):
                raise RuntimeError("没有可用于刷新的 Session")
            if mode == "login" and account is None:
                raise RuntimeError("邮箱账号不存在，无法重新登录")
            settings = SettingsService(session)
            registration = settings.registration_internal().model_dump()
            registration["proxy"] = proxy or str(registration.get("proxy") or "")
            payload = {
                "action": "refresh_authorization",
                "mode": mode,
                "account": _account_payload(account) if account is not None else {"email": email},
                "credential": _credential_payload(credential),
                "registration": registration,
                "mail": settings.mail_internal(),
            }
        response = call_legacy_runtime(
            self._session_factory,
            payload,
            timeout=600 if mode == "login" else 120,
            job_id=self.job_id,
            cancel_check=self.cancel_event.is_set,
        )
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error") or "授权恢复失败"))
        value = dict(response.get("credential") or {})
        with self._session_factory() as session:
            credential = session.get(Credential, email)
            if credential is None:
                raise RuntimeError("凭据不存在")
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
            session.commit()
            if not credential.access_token:
                raise RuntimeError("授权恢复后仍没有 Access Token")
            return credential.access_token

    def _save_plus_result(self, email: str, result: dict[str, object]) -> None:
        with self._session_factory() as session:
            credential = session.get(Credential, email)
            if credential is None:
                return
            credential.metadata_json = {
                **(credential.metadata_json or {}),
                "plus_check": {**result, "checked_at": utc_now().isoformat()},
            }
            session.commit()

    def _publish(self, emails: list[str]) -> dict[str, Any]:
        targets = [str(value) for value in self.payload.get("targets", [])]
        with self._session_factory() as session:
            export = SettingsService(session).export_internal()
        for name in ("cpa", "sub2api"):
            export[name]["enabled"] = name in targets
        results: list[tuple[str, dict[str, Any]]] = []
        for email in emails:
            if self.cancel_event.is_set():
                raise RuntimeCanceledError("发布任务已取消")
            with self._session_factory() as session:
                credential = session.get(Credential, email)
                if credential is None:
                    continue
                detail = RegistrationResultDetail.model_validate(credential).model_dump(
                    mode="json", exclude={"totp_secret"}
                )
            try:
                response = call_legacy_runtime(
                    self._session_factory,
                    {"action": "export", "credential": detail, "export": export},
                    timeout=300,
                    job_id=self.job_id,
                    cancel_check=self.cancel_event.is_set,
                )
            except RuntimeCanceledError:
                raise
            except Exception as error:
                response = {"ok": False, "error": str(error), "results": {}}
            target_results = dict(response.get("results") or {})
            failures = [
                f"{email} / {target}: {target_results.get(target, {}).get('error', '导出失败')}"
                for target in targets
                if not target_results.get(target, {}).get("ok")
            ]
            ok = bool(response.get("ok")) and not failures
            results.append(
                (
                    email,
                    {
                        "ok": ok,
                        "errors": failures
                        or ([] if ok else [str(response.get("error") or "导出失败")]),
                    },
                )
            )
            self._save_publish_progress(emails, results)
        return self._publish_result(emails, results)

    def _save_progress_results(
        self,
        emails: list[str],
        results: list[tuple[str, dict[str, object]]],
    ) -> None:
        self._save_job_result(self._plus_result(emails, results))

    def _save_publish_progress(
        self,
        emails: list[str],
        results: list[tuple[str, dict[str, Any]]],
    ) -> None:
        self._save_job_result(self._publish_result(emails, results))

    def _save_job_result(self, result: dict[str, Any]) -> None:
        with self._session_factory() as session:
            job = session.get(Job, self.job_id)
            if job is not None and job.status == JobStatus.RUNNING:
                job.result = result
                session.commit()

    @staticmethod
    def _progress(*, total: int) -> dict[str, Any]:
        return {
            "total": total,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "plus": 0,
            "unknown": 0,
            "errors": [],
            "processed_emails": [],
            "failed_emails": [],
        }

    @classmethod
    def _plus_result(
        cls,
        emails: list[str],
        results: list[tuple[str, dict[str, object]]],
    ) -> dict[str, Any]:
        succeeded = [item for item in results if item[1].get("is_plus") is not None]
        failed = [item for item in results if item[1].get("is_plus") is None]
        return {
            "total": len(emails),
            "processed": len(results),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "plus": sum(item[1].get("is_plus") is True for item in results),
            "unknown": len(failed),
            "errors": [
                f"{email}: {result.get('error')}" for email, result in failed if result.get("error")
            ][:20],
            "processed_emails": [email for email, _ in results],
            "failed_emails": [email for email, _ in failed],
        }

    @staticmethod
    def _publish_result(
        emails: list[str],
        results: list[tuple[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        failed = [item for item in results if not item[1].get("ok")]
        return {
            "total": len(emails),
            "processed": len(results),
            "succeeded": len(results) - len(failed),
            "failed": len(failed),
            "plus": 0,
            "unknown": 0,
            "errors": [
                f"{email}: {error}"
                for email, result in failed
                for error in result.get("errors", [])
            ][:20],
            "processed_emails": [email for email, _ in results],
            "failed_emails": [email for email, _ in failed],
        }
