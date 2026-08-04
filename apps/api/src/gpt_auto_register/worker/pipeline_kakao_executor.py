from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.kakao import KakaoTask, KakaoTaskStatus
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineStatus,
)
from gpt_auto_register.modules.kakao.local_service import (
    KakaoExtractionError,
    extract_payment_link,
)
from gpt_auto_register.modules.kakao.state import (
    KakaoClaimConflictError,
    completed_extraction_emails,
    mark_extraction_completed,
    release_extraction_claim,
    require_extraction_claim,
)
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.executor_support import emit as _emit
from gpt_auto_register.worker.proxy_service import ProxyAllocator, ProxyApiError, emit_proxy_attempt

ProxyPair = tuple[str, str]


def pair_kakao_proxy_assignments(
    item_ids: list[str],
    kr_assignments: dict[str, list[str]],
    vn_assignments: dict[str, list[str]],
) -> tuple[dict[str, list[ProxyPair]], dict[str, str]]:
    assignments: dict[str, list[ProxyPair]] = {}
    failures: dict[str, str] = {}
    reserved: set[str] = set()
    for item_id in item_ids:
        kr_values = kr_assignments.get(item_id, [])
        vn_values = vn_assignments.get(item_id, [])
        values = [*kr_values, *vn_values]
        if not kr_values or len(kr_values) != len(vn_values):
            failures[item_id] = "Kakao KR/VN 代理对数量不足"
            reserved.update(values)
            continue
        if len(set(values)) != len(values):
            failures[item_id] = "Kakao 账号预分配的 KR/VN 代理存在重复"
            reserved.update(values)
            continue
        if reserved.intersection(values):
            failures[item_id] = "Kakao 账号预分配代理已被前序账号占用"
            reserved.update(values)
            continue
        reserved.update(values)
        assignments[item_id] = list(zip(kr_values, vn_values, strict=True))
    return assignments, failures


class KakaoPipelineExecutorMixin:
    job_id: str
    run_id: str
    _session_factory: Callable[[], Session]

    def _wait_until_runnable(self) -> bool:
        raise NotImplementedError

    def _execute_kakao_pipeline(self, item_ids: list[str]) -> dict[str, Any]:
        _emit(self.job_id, "pipeline_started", "Kakao 本地提取任务开始执行")
        with self._session_factory() as session:
            settings = SettingsService(session)
            proxy_settings = settings.proxy_internal()
            concurrency = settings.pipeline_internal().kakao_email_concurrency

        allocator = ProxyAllocator(
            proxy_settings,
            self._session_factory,
            self.job_id,
            "kakao",
        )
        try:
            kr_batch = allocator.allocate(item_ids, region="KR")
            vn_batch = allocator.allocate(item_ids, region="VN")
        except ProxyApiError:
            kr_batch = vn_batch = None

        assignments: dict[str, list[ProxyPair]] = {}
        assignment_failures: dict[str, str] = {}
        if kr_batch is not None and vn_batch is not None:
            assignments, assignment_failures = pair_kakao_proxy_assignments(
                item_ids,
                kr_batch.assignments,
                vn_batch.assignments,
            )

        runnable = [item_id for item_id in item_ids if item_id in assignments]
        for item_id in item_ids:
            if item_id not in assignments:
                self._save_kakao_proxy_shortage(
                    item_id,
                    assignment_failures.get(item_id, "Kakao KR/VN 代理对数量不足"),
                )

        with ThreadPoolExecutor(max_workers=min(concurrency, len(runnable) or 1)) as executor:
            futures = {
                executor.submit(self._execute_kakao_item, item_id, assignments[item_id]): item_id
                for item_id in runnable
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

        with self._session_factory() as session:
            run = session.get(PipelineRun, self.run_id)
            if run is None:
                raise RuntimeError("流水线轮次已被删除")
            statuses = list(
                session.scalars(
                    select(PipelineItem.status).where(PipelineItem.pipeline_run_id == self.run_id)
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
            final_status = run.status.value
            created = run.kakao_task_count
            session.commit()
        _emit(
            self.job_id,
            "pipeline_finished",
            f"Kakao 本地提取完成：成功 {completed}，跳过 {skipped}，失败 {failed}",
            data={"completed": completed, "skipped": skipped, "failed": failed, "tasks": created},
        )
        return {
            "status": final_status,
            "completed": completed,
            "skipped": skipped,
            "failed": failed,
            "tasks": created,
        }

    def _execute_kakao_item(self, item_id: str, proxy_pairs: list[ProxyPair]) -> None:
        if not self._wait_until_runnable():
            return
        with self._session_factory() as session:
            item = session.get(PipelineItem, item_id)
            if item is None or not item.account_email:
                return
            if item.status == PipelineItemStatus.COMPLETED:
                return
            credential = session.get(Credential, item.account_email)
            if credential is None or not credential.access_token:
                reason = "前置条件不满足：账号缺少 Access Token"
                item.status = PipelineItemStatus.FAILED
                item.error = reason
                session.commit()
                self._emit_prerequisite_failure(item_id, item.account_email, reason)
                return
            email = item.account_email
            access_token = str(credential.access_token)
            item.status = PipelineItemStatus.SUBMITTING
            item.error = None
            session.commit()

        last_error: Exception | None = None
        for attempt, (kr_proxy, vn_proxy) in enumerate(proxy_pairs, start=1):
            started_at = utc_now()
            proxy_label = f"KR={kr_proxy} | VN={vn_proxy}"
            try:
                self._run_kakao(
                    item_id,
                    {"email": email, "access_token": access_token},
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
                return
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
                if isinstance(error, KakaoExtractionError) and not error.retryable:
                    break
                if attempt < len(proxy_pairs):
                    _emit(
                        self.job_id,
                        "kakao_retry",
                        f"Kakao 提取失败，切换到第 {attempt + 1} 个预分配 KR/VN 代理对",
                        level="warning",
                        data={"item_id": item_id, "email": email},
                    )
        if last_error is not None:
            self._save_kakao_failure(item_id, str(last_error))
            _emit(
                self.job_id,
                "kakao_item_failed",
                f"Kakao 支付链接提取失败 {email}: {last_error}",
                level="error",
                data={"item_id": item_id, "email": email},
            )

    def _run_kakao(
        self,
        item_id: str,
        credential: dict[str, Any],
        *,
        kr_proxy: str,
        vn_proxy: str,
    ) -> None:
        access_token = str(credential.get("access_token") or "")
        email = str(credential.get("email") or "").strip().lower()
        with self._session_factory() as session:
            item = session.get(PipelineItem, item_id)
            if item is None:
                raise RuntimeError("Kakao 流水线账号不存在")
            if email in completed_extraction_emails(session, [email]):
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
            try:
                require_extraction_claim(session, email, self.run_id, item_id)
            except KakaoClaimConflictError:
                item.status = PipelineItemStatus.SKIPPED
                item.eligibility_state = "already_active"
                item.error = "邮箱已有活动的 Kakao 提取任务"
                session.commit()
                _emit(
                    self.job_id,
                    "kakao_skipped",
                    f"Kakao 提取已跳过，邮箱已有活动任务：{email}",
                    data={"item_id": item_id, "email": email, "reason": "already_active"},
                )
                return
            settings = SettingsService(session).kakao_internal()
            task = session.scalar(select(KakaoTask).where(KakaoTask.pipeline_item_id == item_id))
            if task is None:
                task = KakaoTask(
                    upstream_job_id=f"local:{uuid4()}",
                    pipeline_run_id=self.run_id,
                    pipeline_item_id=item_id,
                    email=email,
                    status=KakaoTaskStatus.EXTRACTING,
                    payment_status="extracting",
                    upstream_payload={"engine": "local-upi-1"},
                )
                session.add(task)
                run = session.get(PipelineRun, self.run_id)
                if run is not None:
                    run.kakao_task_count = (run.kakao_task_count or 0) + 1
            else:
                task.status = KakaoTaskStatus.EXTRACTING
                task.payment_status = "extracting"
                task.error = None
            session.commit()

        def extraction_log(message: str, level: str) -> None:
            _emit(
                self.job_id,
                "kakao_step_log",
                message,
                level=level,
                data={"item_id": item_id, "email": email},
            )

        result = extract_payment_link(
            access_token=access_token,
            email=email,
            kr_proxy=kr_proxy,
            vn_proxy=vn_proxy,
            request_timeout=settings.timeout,
            poll_timeout=settings.poll_timeout,
            promo_id=settings.promo_code,
            stop_event=getattr(self, "_cancel_event", None),
            log=extraction_log,
            verify_proxy_countries=settings.verify_proxy_countries,
        )

        with self._session_factory() as session:
            item = session.get(PipelineItem, item_id)
            task = session.scalar(select(KakaoTask).where(KakaoTask.pipeline_item_id == item_id))
            run = session.get(PipelineRun, self.run_id)
            if item is None or task is None or run is None or run.status == PipelineStatus.CANCELED:
                return
            task.status = KakaoTaskStatus.DONE
            task.payment_status = "ready"
            task.payment_url = result.payment_url
            task.error = None
            task.upstream_payload = {"engine": "local-upi-1", **result.as_payload()}
            mark_extraction_completed(session, task)
            item.status = PipelineItemStatus.COMPLETED
            item.eligibility_state = "eligible"
            item.error = None
            credential_row = session.get(Credential, email)
            if credential_row is not None:
                credential_row.metadata_json = {
                    **(credential_row.metadata_json or {}),
                    "kakao_pipeline": {
                        "status": "completed",
                        "eligible": True,
                        "state": "eligible",
                        "error": "",
                        "checked_at": utc_now().isoformat(),
                        "job_ids": [task.upstream_job_id],
                        "payment_url": result.payment_url,
                        "engine": "local-upi-1",
                    },
                }
            session.commit()
        _emit(
            self.job_id,
            "kakao_payment_link_extracted",
            f"Kakao 支付链接提取成功 {email}",
            data={"item_id": item_id, "email": email, "payment_url": result.payment_url},
        )

    def _save_kakao_failure(self, item_id: str, reason: str) -> None:
        with self._session_factory() as session:
            item = session.get(PipelineItem, item_id)
            task = session.scalar(select(KakaoTask).where(KakaoTask.pipeline_item_id == item_id))
            if item is not None:
                item.status = PipelineItemStatus.FAILED
                item.error = reason
            if task is not None:
                task.status = KakaoTaskStatus.FAILED
                task.payment_status = "failed"
                task.error = reason
                task.upstream_payload = {
                    **(task.upstream_payload or {}),
                    "failure_reason": reason,
                }
                release_extraction_claim(session, task)
            session.commit()

    def _emit_prerequisite_failure(self, item_id: str, email: str, reason: str) -> None:
        _emit(
            self.job_id,
            "kakao_prerequisite_failed",
            reason,
            level="error",
            data={"item_id": item_id, "email": email, "step": "kakao"},
        )

    def _save_kakao_proxy_shortage(self, item_id: str, detail: str) -> None:
        reason = f"{detail}，账号未开始执行"
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
            data={"item_id": item_id, "step": "kakao"},
        )
