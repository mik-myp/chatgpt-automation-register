from collections import Counter

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import (
    AccountStatus,
    OutlookAccount,
    RegistrationRun,
    RunStatus,
)
from gpt_auto_register.db.models.jobs import Job, JobEvent, JobStatus
from gpt_auto_register.db.models.kakao import KakaoCard, KakaoTask, PipelineCardAllocation
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineItemStatus,
    PipelineRun,
    PipelineRunKind,
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
        card_slots: list[str] | None = None,
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
                card_code_snapshot=(card_slots or [])[position] if card_slots else None,
            )
            for position in range(target_count)
        ]
        self.session.add_all(items)
        if card_slots:
            counts = Counter(card_slots)
            cards = {
                card.code: card
                for card in self.session.scalars(
                    select(KakaoCard).where(KakaoCard.code.in_(counts))
                )
            }
            self.session.add_all(
                PipelineCardAllocation(
                    pipeline_run_id=run.id,
                    card_id=cards[code].id,
                    allocated_count=count,
                )
                for code, count in counts.items()
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

    def create_security(
        self,
        *,
        source_run_id: str | None,
        emails: list[str],
    ) -> PipelineRun:
        run = PipelineRun(
            kind=PipelineRunKind.ACCOUNT_SECURITY,
            source_pipeline_run_id=source_run_id,
            mode="security",
            target_count=len(emails),
            kakao_enabled=False,
            config_snapshot={"action": "set_password_and_mfa"},
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
        self.session.add(
            Job(
                kind="account.security",
                payload={
                    "action": "set_password_and_mfa",
                    "emails": emails,
                    "pipeline_run_id": run.id,
                    "source_pipeline_run_id": source_run_id or "",
                },
                max_attempts=1,
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

    def card_assignments(self, run_id: str) -> list[KakaoTask]:
        return list(
            self.session.scalars(
                select(KakaoTask)
                .where(KakaoTask.pipeline_run_id == run_id)
                .order_by(KakaoTask.created_at, KakaoTask.id)
            )
        )

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
                Job.kind.in_(["pipeline.run", "account.security"]),
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

    def delete_runs(self, run_ids: list[str]) -> int:
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

    def events(self, run_id: str, after: int, limit: int) -> list[JobEvent]:
        jobs = self.session.scalars(select(Job).order_by(Job.created_at.desc()))
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
        active_jobs = self.session.scalars(
            select(Job).where(
                Job.kind == "account.security",
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        if any(job.payload.get("pipeline_run_id") == run_id for job in active_jobs):
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
