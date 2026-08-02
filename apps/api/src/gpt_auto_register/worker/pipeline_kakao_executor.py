from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.kakao import KakaoCard, KakaoTask, PipelineCardAllocation
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineStatus,
)
from gpt_auto_register.db.result import affected_rows
from gpt_auto_register.modules.kakao.client import KakaoClient, payload_tasks
from gpt_auto_register.modules.kakao.state import (
    KakaoClaimConflictError,
    apply_upstream,
    completed_extraction_emails,
    require_extraction_claim,
)
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.executor_support import emit as _emit


class KakaoPipelineExecutorMixin:
    job_id: str
    run_id: str
    _session_factory: Callable[[], Session]

    def _allocate_cards(self, item_ids: list[str]) -> dict[str, str]:
        raise NotImplementedError

    def _wait_until_runnable(self) -> bool:
        raise NotImplementedError

    def _record_kakao_failure(self, card_code: str) -> None:
        raise NotImplementedError

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
            f"Kakao 流水线执行完成：完成 {completed}，跳过 {skipped}，失败 {failed}",
            data={
                "completed": completed,
                "skipped": skipped,
                "failed": failed,
                "tasks": created,
            },
        )
        return {
            "status": final_status,
            "completed": completed,
            "skipped": skipped,
            "failed": failed,
            "tasks": created,
        }

    def _execute_kakao_item(self, item_id: str, card_code: str) -> None:
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

    def _run_kakao(
        self,
        item_id: str,
        credential: dict[str, Any],
        card_code: str,
    ) -> None:
        access_token = str(credential.get("access_token") or "")
        if not access_token:
            raise RuntimeError("注册结果缺少 Access Token")
        with self._session_factory() as session:
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
            try:
                require_extraction_claim(session, email or "", self.run_id, item_id)
            except KakaoClaimConflictError:
                if item is not None:
                    item.status = PipelineItemStatus.COMPLETED
                    item.eligibility_state = "already_active"
                    item.error = None
                session.commit()
                _emit(
                    self.job_id,
                    "kakao_skipped",
                    f"Kakao 提取已跳过，邮箱已有活动任务：{email}",
                    data={"item_id": item_id, "email": email, "reason": "already_active"},
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
            with self._session_factory() as session:
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
        if not task_ids and not duplicate_ids:
            raise RuntimeError("Kakao 创建接口未返回任务 ID，未将该账号标记为完成")
        with self._session_factory() as session:
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
