from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import (
    AccountStatus,
    OutlookAccount,
    RegistrationRun,
    RunStatus,
)
from gpt_auto_register.db.models.jobs import Job, JobEvent, JobStatus
from gpt_auto_register.db.models.kakao import KakaoCard, PipelineCardAllocation
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineStatus,
)
from gpt_auto_register.db.result import affected_rows


class PipelineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: str) -> PipelineRun | None:
        return self.session.get(PipelineRun, run_id)

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
        self.session.add_all(
            PipelineItem(
                pipeline_run_id=run.id,
                position=position,
                account_email=email if position == 0 else None,
            )
            for position in range(target_count)
        )
        self.session.add(
            Job(
                kind="pipeline.run",
                payload={"pipeline_run_id": run.id},
                max_attempts=3,
            )
        )
        self.session.flush()
        return run

    def list_page(
        self,
        *,
        status: PipelineStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PipelineRun], int]:
        filters = [PipelineRun.status == status] if status is not None else []
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

    def card_allocations(self, run_id: str) -> list[tuple[PipelineCardAllocation, str]]:
        rows = self.session.execute(
            select(PipelineCardAllocation, KakaoCard.code)
            .join(KakaoCard, KakaoCard.id == PipelineCardAllocation.card_id)
            .where(PipelineCardAllocation.pipeline_run_id == run_id)
            .order_by(KakaoCard.position, KakaoCard.id)
        )
        return [(allocation, code) for allocation, code in rows]

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
        jobs = self.session.scalars(
            select(Job).where(
                Job.kind == "pipeline.run",
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        run_id_set = set(run_ids)
        for job in jobs:
            if job.payload.get("pipeline_run_id") not in run_id_set:
                continue
            job.status = JobStatus.CANCELED
            job.finished_at = now
        return affected_rows(result)

    def pause_runs(self, run_ids: list[str]) -> int:
        result = self.session.execute(
            update(PipelineRun)
            .where(
                PipelineRun.id.in_(run_ids),
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
                PipelineRun.status == PipelineStatus.PAUSED,
            )
            .values(status=PipelineStatus.RUNNING)
        )
        return affected_rows(result)

    def events(self, run_id: str, after: int, limit: int) -> list[JobEvent]:
        jobs = self.session.scalars(
            select(Job).where(Job.kind == "pipeline.run").order_by(Job.created_at.desc())
        )
        job = next(
            (value for value in jobs if value.payload.get("pipeline_run_id") == run_id),
            None,
        )
        if job is None:
            return []
        query = select(JobEvent).where(
            JobEvent.job_id == job.id,
            JobEvent.sequence > after,
        )
        if after == 0:
            return list(
                reversed(
                    list(
                        self.session.scalars(query.order_by(JobEvent.sequence.desc()).limit(limit))
                    )
                )
            )
        return list(self.session.scalars(query.order_by(JobEvent.sequence).limit(limit)))

    def retry_items(self, run_id: str, item_ids: list[str]) -> int:
        items = list(
            self.session.scalars(
                select(PipelineItem).where(
                    PipelineItem.pipeline_run_id == run_id,
                    PipelineItem.id.in_(item_ids),
                    PipelineItem.status.in_(
                        [PipelineItemStatus.FAILED, PipelineItemStatus.SKIPPED]
                    ),
                )
            )
        )
        if not items:
            return 0
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
            item.status = PipelineItemStatus.SCHEDULED
            item.error = None
            item.eligibility_state = None
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
                payload={
                    "pipeline_run_id": run_id,
                    "retry_item_ids": [item.id for item in items],
                },
                max_attempts=3,
            )
        )
        return len(items)
