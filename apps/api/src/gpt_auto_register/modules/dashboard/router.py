from fastapi import APIRouter
from sqlalchemy import func, select

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.db.models.pipeline import PipelineRun, PipelineStatus
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.accounts.schemas import AccountStats
from gpt_auto_register.modules.accounts.service import account_stats
from gpt_auto_register.modules.cards.repository import CardRepository
from gpt_auto_register.modules.cards.schemas import CardInventoryStats
from gpt_auto_register.modules.dashboard.schemas import (
    DashboardJobStats,
    DashboardPipelineStats,
    DashboardResponse,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(db: DatabaseSession) -> DashboardResponse:
    card_total, card_active, batches = CardRepository(db).stats()
    pipeline_counts = {
        pipeline_status: count
        for pipeline_status, count in db.execute(
            select(PipelineRun.status, func.count()).group_by(PipelineRun.status)
        )
    }
    job_counts = {
        job_status: count
        for job_status, count in db.execute(select(Job.status, func.count()).group_by(Job.status))
    }
    return DashboardResponse(
        accounts=AccountStats(**account_stats(AccountRepository(db))),
        cards=CardInventoryStats(
            total=card_total,
            active=card_active,
            inactive=card_total - card_active,
            batches=batches,
        ),
        pipelines=DashboardPipelineStats(
            total=sum(pipeline_counts.values()),
            active=sum(
                pipeline_counts.get(value, 0)
                for value in (PipelineStatus.QUEUED, PipelineStatus.RUNNING, PipelineStatus.PAUSED)
            ),
            completed=pipeline_counts.get(PipelineStatus.COMPLETED, 0),
            failed=pipeline_counts.get(PipelineStatus.FAILED, 0),
        ),
        jobs=DashboardJobStats(
            queued=job_counts.get(JobStatus.QUEUED, 0),
            running=job_counts.get(JobStatus.RUNNING, 0),
            failed=job_counts.get(JobStatus.FAILED, 0),
        ),
        registration_results=db.scalar(select(func.count()).select_from(Credential)) or 0,
    )
