from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.jobs import Job, JobStatus
from gpt_auto_register.modules.results.schemas import (
    PlusCheckRequest,
    PublishResultsRequest,
    ResultOperationListResponse,
    ResultOperationSummary,
)

router = APIRouter(tags=["result-operations"])
_KINDS = ("results.plus_check", "results.publish")


def _summary(job: Job) -> ResultOperationSummary:
    result = job.result if isinstance(job.result, dict) else {}
    payload = job.payload if isinstance(job.payload, dict) else {}
    total = int(result.get("total") or len(payload.get("resolved_emails", [])))
    failed = int(result.get("failed") or 0)
    return ResultOperationSummary(
        id=job.id,
        kind=job.kind,
        status=job.status,
        total=total,
        processed=int(result.get("processed") or 0),
        succeeded=int(result.get("succeeded") or 0),
        failed=failed,
        plus=int(result.get("plus") or 0),
        unknown=int(result.get("unknown") or 0),
        errors=[str(value) for value in result.get("errors", [])][:20],
        cancelable=job.status in {JobStatus.QUEUED, JobStatus.RUNNING},
        retryable=job.status in {JobStatus.FAILED, JobStatus.CANCELED} or failed > 0,
        created_at=job.created_at,
        updated_at=job.updated_at,
        finished_at=job.finished_at,
    )


def _create_job(
    db: DatabaseSession,
    *,
    kind: str,
    operation: str,
    emails: list[str],
    all_results: bool,
    extra: dict[str, object] | None = None,
) -> ResultOperationSummary:
    normalized = list(dict.fromkeys(email.strip().lower() for email in emails if email.strip()))
    pipeline_scope = str((extra or {}).get("pipeline_run_id") or "").strip()
    if not all_results and not normalized and not pipeline_scope:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要处理的注册结果")
    job = Job(
        kind=kind,
        payload={
            "operation": operation,
            "emails": normalized,
            "all": all_results,
            **(extra or {}),
        },
        max_attempts=1,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _summary(job)


@router.post(
    "/results/check-plus",
    response_model=ResultOperationSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def check_plus_results(
    request: PlusCheckRequest,
    db: DatabaseSession,
) -> ResultOperationSummary:
    return _create_job(
        db,
        kind="results.plus_check",
        operation="plus_check",
        emails=request.emails,
        all_results=request.all,
        extra={
            "proxy": request.proxy.strip(),
            "pipeline_run_id": request.pipeline_run_id,
        },
    )


@router.post(
    "/results/publish",
    response_model=ResultOperationSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def publish_results(
    request: PublishResultsRequest,
    db: DatabaseSession,
) -> ResultOperationSummary:
    return _create_job(
        db,
        kind="results.publish",
        operation="publish",
        emails=request.emails,
        all_results=request.all,
        extra={"targets": request.targets},
    )


@router.get("/result-operations", response_model=ResultOperationListResponse)
def list_result_operations(
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ResultOperationListResponse:
    filters = [Job.kind.in_(_KINDS)]
    total = db.scalar(select(func.count()).select_from(Job).where(*filters)) or 0
    jobs = list(
        db.scalars(
            select(Job)
            .where(*filters)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return ResultOperationListResponse(
        items=[_summary(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/result-operations/{job_id}", response_model=ResultOperationSummary)
def get_result_operation(job_id: str, db: DatabaseSession) -> ResultOperationSummary:
    job = db.get(Job, job_id)
    if job is None or job.kind not in _KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "结果处理任务不存在")
    return _summary(job)


@router.post("/result-operations/{job_id}/cancel", response_model=ResultOperationSummary)
def cancel_result_operation(job_id: str, db: DatabaseSession) -> ResultOperationSummary:
    job = db.get(Job, job_id)
    if job is None or job.kind not in _KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "结果处理任务不存在")
    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
        job.status = JobStatus.CANCELED
        job.finished_at = utc_now()
        job.lease_owner = None
        job.lease_expires_at = None
        db.commit()
        db.refresh(job)
    return _summary(job)


@router.post(
    "/result-operations/{job_id}/retry",
    response_model=ResultOperationSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_result_operation(job_id: str, db: DatabaseSession) -> ResultOperationSummary:
    original = db.get(Job, job_id)
    if original is None or original.kind not in _KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "结果处理任务不存在")
    payload = original.payload if isinstance(original.payload, dict) else {}
    result = original.result if isinstance(original.result, dict) else {}
    resolved = [str(value) for value in payload.get("resolved_emails", [])]
    processed = {str(value) for value in result.get("processed_emails", [])}
    failed = [str(value) for value in result.get("failed_emails", [])]
    remaining = [email for email in resolved if email not in processed]
    emails = list(dict.fromkeys([*failed, *remaining]))
    if not emails and payload.get("all") and not resolved:
        job = Job(
            kind=original.kind,
            payload={**payload, "retry_of": original.id},
            max_attempts=1,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return _summary(job)
    if not emails:
        raise HTTPException(status.HTTP_409_CONFLICT, "该任务没有可重试的账号")
    job = Job(
        kind=original.kind,
        payload={**payload, "emails": emails, "all": False, "retry_of": original.id},
        max_attempts=1,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _summary(job)
