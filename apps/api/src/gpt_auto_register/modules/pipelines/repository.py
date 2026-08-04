from collections import Counter

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from gpt_auto_register.core.encryption import secret_fingerprint
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import (
    AccountStatus,
    OutlookAccount,
    RegistrationRun,
    RunStatus,
)
from gpt_auto_register.db.models.jobs import Job, JobEvent, JobStatus
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoClaimState,
    KakaoEmailClaim,
    KakaoTask,
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
from gpt_auto_register.modules.kakao.state import require_extraction_claim
from gpt_auto_register.modules.settings.service import SettingsService


class PipelineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: str) -> PipelineRun | None:
        return self.session.get(PipelineRun, run_id)

    def _queue_job(
        self,
        *,
        kind: str,
        run: PipelineRun,
        payload: dict[str, object],
        max_attempts: int,
    ) -> Job:
        order = SettingsService(self.session).pipeline_internal().step_order
        run_step = "kakao" if run.kind == PipelineRunKind.KAKAO else (
            "account_security" if run.kind == PipelineRunKind.ACCOUNT_SECURITY else "registration"
        )
        priorities: dict[str, int] = {
            step: 30 - index * 10 for index, step in enumerate(order)
        }
        job = Job(
            kind=kind,
            pipeline_run_id=run.id,
            payload=payload,
            max_attempts=max_attempts,
            priority=priorities[run_step],
        )
        self.session.add(job)
        self.session.flush()
        self.session.add(
            JobEvent(
                job_id=job.id,
                sequence=1,
                event_type="task_queued",
                message=f"任务已排队，步骤 {run_step}",
                data={"task_type": run_step, "step_order": order},
            )
        )
        return job

    def create(
        self,
        *,
        mode: str,
        target_count: int,
        email: str | None,
        kakao_enabled: bool,
        config_snapshot: dict[str, object],
    ) -> PipelineRun:
        run = PipelineRun(
            mode=mode,
            target_count=target_count,
            kakao_enabled=kakao_enabled,
            config_snapshot=config_snapshot,
            scheduled_count=target_count,
        )
        self.session.add(run)
        self.session.flush()
        items = [
            PipelineItem(
                pipeline_run_id=run.id,
                position=position,
                account_email=email if position == 0 else None,
            )
            for position in range(target_count)
        ]
        self.session.add_all(items)
        self._queue_job(
            kind="pipeline.run",
            run=run,
            payload={"pipeline_run_id": run.id},
            max_attempts=3,
        )
        self.session.flush()
        return run

    def create_kakao(
        self,
        *,
        source_run_id: str | None,
        emails: list[str],
    ) -> PipelineRun:
        settings = SettingsService(self.session)
        pipeline = settings.pipeline_internal()
        proxy = settings.proxy_internal()
        run = PipelineRun(
            kind=PipelineRunKind.KAKAO,
            source_pipeline_run_id=source_run_id,
            mode="kakao",
            target_count=len(emails),
            kakao_enabled=True,
            config_snapshot={
                "action": "create_kakao_tasks",
                "step_order": pipeline.step_order,
                "email_concurrency": pipeline.kakao_email_concurrency,
                "proxy_max_attempts": proxy.max_attempts_per_account,
            },
            scheduled_count=len(emails),
        )
        self.session.add(run)
        self.session.flush()
        items = [
            PipelineItem(
                pipeline_run_id=run.id,
                position=position,
                account_email=email,
            )
            for position, email in enumerate(emails)
        ]
        self.session.add_all(items)
        self.session.flush()
        for item in items:
            require_extraction_claim(
                self.session,
                item.account_email or "",
                run.id,
                item.id,
            )
        self._queue_job(
            kind="pipeline.run",
            run=run,
            payload={"pipeline_run_id": run.id},
            max_attempts=3,
        )
        self.session.flush()
        return run

    def _reserve_cards(self, run_id: str, card_slots: list[str]) -> None:
        counts = Counter(card_slots)
        cards = {
            card.code: card
            for card in self.session.scalars(
                select(KakaoCard).where(
                    KakaoCard.code_fingerprint.in_([secret_fingerprint(code) for code in counts])
                )
            )
        }
        self.session.add_all(
            PipelineCardAllocation(
                pipeline_run_id=run_id,
                card_id=cards[code].id,
                allocated_count=count,
            )
            for code, count in counts.items()
        )

    def create_security(
        self,
        *,
        source_run_id: str | None,
        emails: list[str],
    ) -> PipelineRun:
        settings = SettingsService(self.session)
        pipeline = settings.pipeline_internal()
        proxy = settings.proxy_internal()
        run = PipelineRun(
            kind=PipelineRunKind.ACCOUNT_SECURITY,
            source_pipeline_run_id=source_run_id,
            mode="security",
            target_count=len(emails),
            kakao_enabled=False,
            config_snapshot={
                "action": "set_password_and_mfa",
                "step_order": pipeline.step_order,
                "email_concurrency": pipeline.account_security_email_concurrency,
                "proxy_max_attempts": proxy.max_attempts_per_account,
            },
            scheduled_count=len(emails),
        )
        self.session.add(run)
        self.session.flush()
        self.session.add_all(
            PipelineItem(
                pipeline_run_id=run.id,
                position=position,
                account_email=email,
                password_status="pending",
                mfa_status="pending",
            )
            for position, email in enumerate(emails)
        )
        self._queue_job(
            kind="account.security",
            run=run,
            payload={
                "action": "set_password_and_mfa",
                "emails": emails,
                "pipeline_run_id": run.id,
                "source_pipeline_run_id": source_run_id or "",
            },
            max_attempts=1,
        )
        self.session.flush()
        return run

    def list_page(
        self,
        *,
        status: PipelineStatus | None,
        search: str = "",
        limit: int,
        offset: int,
    ) -> tuple[list[PipelineRun], int]:
        filters = [PipelineRun.status == status] if status is not None else []
        if search:
            needle = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(PipelineRun.id).like(needle),
                    func.lower(PipelineRun.mode).like(needle),
                    select(PipelineItem.id)
                    .where(
                        PipelineItem.pipeline_run_id == PipelineRun.id,
                        func.lower(PipelineItem.account_email).like(needle),
                    )
                    .exists(),
                )
            )
        total = (
            self.session.scalar(select(func.count()).select_from(PipelineRun).where(*filters)) or 0
        )
        items = list(
            self.session.scalars(
                select(PipelineRun)
                .where(*filters)
                .order_by(PipelineRun.created_at.desc(), PipelineRun.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def items(self, run_id: str) -> list[PipelineItem]:
        return list(
            self.session.scalars(
                select(PipelineItem)
                .where(PipelineItem.pipeline_run_id == run_id)
                .order_by(PipelineItem.position)
            )
        )

    def items_page(
        self,
        run_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[PipelineItem], int]:
        filters = [PipelineItem.pipeline_run_id == run_id]
        total = (
            self.session.scalar(select(func.count()).select_from(PipelineItem).where(*filters)) or 0
        )
        items = list(
            self.session.scalars(
                select(PipelineItem)
                .where(*filters)
                .order_by(PipelineItem.position)
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def card_allocations(self, run_id: str) -> list[tuple[PipelineCardAllocation, str]]:
        rows = self.session.execute(
            select(PipelineCardAllocation, KakaoCard.code)
            .join(KakaoCard, KakaoCard.id == PipelineCardAllocation.card_id)
            .where(PipelineCardAllocation.pipeline_run_id == run_id)
            .order_by(KakaoCard.position, KakaoCard.id)
        )
        return [(allocation, code) for allocation, code in rows]

    def card_allocations_page(
        self,
        run_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[PipelineCardAllocation, str]], int]:
        filters = [PipelineCardAllocation.pipeline_run_id == run_id]
        total = (
            self.session.scalar(
                select(func.count()).select_from(PipelineCardAllocation).where(*filters)
            )
            or 0
        )
        rows = self.session.execute(
            select(PipelineCardAllocation, KakaoCard.code)
            .join(KakaoCard, KakaoCard.id == PipelineCardAllocation.card_id)
            .where(*filters)
            .order_by(KakaoCard.position, KakaoCard.id)
            .limit(limit)
            .offset(offset)
        )
        return [(allocation, code) for allocation, code in rows], total

    def card_assignments(
        self,
        run_id: str,
        card_ids: list[str] | None = None,
    ) -> list[KakaoTask]:
        query = select(KakaoTask).where(KakaoTask.pipeline_run_id == run_id)
        if card_ids is not None:
            query = query.where(KakaoTask.card_id.in_(card_ids))
        return list(self.session.scalars(query.order_by(KakaoTask.created_at, KakaoTask.id)))

    def cancel_runs(self, run_ids: list[str]) -> int:
        now = utc_now()
        result = self.session.execute(
            update(PipelineRun)
            .where(
                PipelineRun.id.in_(run_ids),
                PipelineRun.status.in_(
                    [PipelineStatus.QUEUED, PipelineStatus.RUNNING, PipelineStatus.PAUSED]
                ),
            )
            .values(status=PipelineStatus.CANCELED, finished_at=now)
        )
        self.session.execute(
            update(Job)
            .where(
                Job.pipeline_run_id.in_(run_ids),
                Job.kind.in_(["pipeline.run", "account.security"]),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
            .values(status=JobStatus.CANCELED, finished_at=now)
        )
        return affected_rows(result)

    def delete_runs(self, run_ids: list[str]) -> int:
        self.session.execute(
            delete(KakaoEmailClaim).where(
                KakaoEmailClaim.pipeline_run_id.in_(run_ids),
                KakaoEmailClaim.state == KakaoClaimState.ACTIVE,
            )
        )
        result = self.session.execute(
            delete(PipelineRun).where(
                PipelineRun.id.in_(run_ids),
                PipelineRun.status.in_(
                    [
                        PipelineStatus.COMPLETED,
                        PipelineStatus.FAILED,
                        PipelineStatus.CANCELED,
                    ]
                ),
            )
        )
        return affected_rows(result)

    def pause_runs(self, run_ids: list[str]) -> int:
        result = self.session.execute(
            update(PipelineRun)
            .where(
                PipelineRun.id.in_(run_ids),
                PipelineRun.kind == PipelineRunKind.REGISTRATION,
                PipelineRun.status.in_([PipelineStatus.QUEUED, PipelineStatus.RUNNING]),
            )
            .values(status=PipelineStatus.PAUSED)
        )
        return affected_rows(result)

    def resume_runs(self, run_ids: list[str]) -> int:
        result = self.session.execute(
            update(PipelineRun)
            .where(
                PipelineRun.id.in_(run_ids),
                PipelineRun.kind == PipelineRunKind.REGISTRATION,
                PipelineRun.status == PipelineStatus.PAUSED,
            )
            .values(status=PipelineStatus.RUNNING)
        )
        return affected_rows(result)

    def events(self, run_id: str, after_cursor: int, limit: int) -> list[JobEvent]:
        query = (
            select(JobEvent)
            .join(Job, Job.id == JobEvent.job_id)
            .where(
                Job.pipeline_run_id == run_id,
                JobEvent.id > after_cursor,
            )
        )
        if after_cursor == 0:
            return list(
                reversed(
                    list(self.session.scalars(query.order_by(JobEvent.id.desc()).limit(limit)))
                )
            )
        return list(self.session.scalars(query.order_by(JobEvent.id).limit(limit)))

    def retry_items(self, run_id: str, item_ids: list[str]) -> int:
        claimed_ids = list(
            self.session.scalars(
                update(PipelineItem)
                .where(
                    PipelineItem.pipeline_run_id == run_id,
                    PipelineItem.id.in_(item_ids),
                    PipelineItem.status.in_(
                        [PipelineItemStatus.FAILED, PipelineItemStatus.SKIPPED]
                    ),
                )
                .values(
                    status=PipelineItemStatus.SCHEDULED,
                    error=None,
                    eligibility_state=None,
                )
                .returning(PipelineItem.id)
            )
        )
        if not claimed_ids:
            return 0
        items = list(
            self.session.scalars(select(PipelineItem).where(PipelineItem.id.in_(claimed_ids)))
        )
        for item in items:
            registration_run = (
                self.session.get(RegistrationRun, item.registration_run_id)
                if item.registration_run_id
                else None
            )
            if registration_run is None or registration_run.status != RunStatus.SUCCEEDED:
                if item.account_email:
                    account = self.session.get(OutlookAccount, item.account_email)
                    if account is not None and account.status == AccountStatus.FAILED:
                        account.status = AccountStatus.AVAILABLE
                        account.claimed_at = None
                        account.finished_at = None
                        account.failure_reason = None
                item.registration_run_id = None
        for allocation in self.session.scalars(
            select(PipelineCardAllocation).where(PipelineCardAllocation.pipeline_run_id == run_id)
        ):
            allocation.allocated_count = allocation.created_count
        run = self.get(run_id)
        if run is not None:
            run.status = PipelineStatus.QUEUED
            run.finished_at = None
        self.session.add(
            Job(
                kind="pipeline.run",
                pipeline_run_id=run_id,
                payload={
                    "pipeline_run_id": run_id,
                    "retry_item_ids": [item.id for item in items],
                },
                max_attempts=3,
            )
        )
        return len(claimed_ids)

    def retry_security_items(self, run_id: str, item_ids: list[str]) -> int:
        run = self.get(run_id)
        if run is None or run.kind != PipelineRunKind.ACCOUNT_SECURITY:
            return 0
        active_job = self.session.scalar(
            select(Job.id).where(
                Job.pipeline_run_id == run_id,
                Job.kind == "account.security",
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        if active_job is not None:
            return 0
        items = list(
            self.session.scalars(
                select(PipelineItem).where(
                    PipelineItem.pipeline_run_id == run_id,
                    PipelineItem.id.in_(item_ids),
                    PipelineItem.status == PipelineItemStatus.FAILED,
                )
            )
        )
        emails = [item.account_email for item in items if item.account_email]
        if not emails:
            return 0
        for item in items:
            item.status = PipelineItemStatus.SCHEDULED
            item.error = None
            item.security_error = None
        run.status = PipelineStatus.QUEUED
        run.finished_at = None
        self.session.add(
            Job(
                kind="account.security",
                pipeline_run_id=run.id,
                payload={
                    "action": "set_password_and_mfa",
                    "emails": emails,
                    "pipeline_run_id": run.id,
                    "source_pipeline_run_id": run.source_pipeline_run_id or "",
                },
                max_attempts=1,
            )
        )
        return len(emails)

    def retry_kakao_items(self, run_id: str, item_ids: list[str]) -> int:
        run = self.get(run_id)
        if run is None or run.kind != PipelineRunKind.KAKAO:
            return 0
        active_job = self.session.scalar(
            select(Job.id).where(
                Job.pipeline_run_id == run_id,
                Job.kind == "pipeline.run",
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        if active_job is not None:
            return 0
        claimed_ids = list(
            self.session.scalars(
                update(PipelineItem)
                .where(
                    PipelineItem.pipeline_run_id == run_id,
                    PipelineItem.id.in_(item_ids),
                    PipelineItem.status.in_(
                        [PipelineItemStatus.FAILED, PipelineItemStatus.SKIPPED]
                    ),
                )
                .values(
                    status=PipelineItemStatus.SCHEDULED,
                    error=None,
                    eligibility_state=None,
                )
                .returning(PipelineItem.id)
            )
        )
        if not claimed_ids:
            return 0
        run.status = PipelineStatus.QUEUED
        run.finished_at = None
        self.session.add(
            Job(
                kind="pipeline.run",
                pipeline_run_id=run_id,
                payload={
                    "pipeline_run_id": run_id,
                    "retry_item_ids": claimed_ids,
                },
                max_attempts=3,
            )
        )
        return len(claimed_ids)
