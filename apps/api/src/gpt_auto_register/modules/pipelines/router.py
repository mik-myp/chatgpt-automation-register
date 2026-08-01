from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.models.pipeline import PipelineStatus
from gpt_auto_register.modules.pipelines.repository import PipelineRepository
from gpt_auto_register.modules.pipelines.schemas import (
    BulkPipelineAction,
    BulkPipelineRequest,
    BulkPipelineResponse,
    PipelineCardAllocationSummary,
    PipelineEventListResponse,
    PipelineEventSummary,
    PipelineItemSummary,
    PipelineRunCreateRequest,
    PipelineRunDetail,
    PipelineRunListResponse,
    PipelineRunSummary,
    RetryPipelineItemsRequest,
)
from gpt_auto_register.modules.settings.service import SettingsService

router = APIRouter(prefix="/pipelines/runs", tags=["pipeline-runs"])


def _card_hint(code: str) -> str:
    if len(code) <= 8:
        return "*" * len(code)
    return f"{code[:4]}...{code[-4:]}"


@router.get("", response_model=PipelineRunListResponse)
def list_pipeline_runs(
    db: DatabaseSession,
    pipeline_status: Annotated[PipelineStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PipelineRunListResponse:
    items, total = PipelineRepository(db).list_page(
        status=pipeline_status,
        limit=limit,
        offset=offset,
    )
    return PipelineRunListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=PipelineRunSummary, status_code=status.HTTP_201_CREATED)
def create_pipeline_run(
    request: PipelineRunCreateRequest,
    db: DatabaseSession,
) -> PipelineRunSummary:
    email = request.email.strip().lower()

    defaults = SettingsService(db).registration_internal()
    registration = defaults.model_dump()
    overrides: dict[str, object] = {}
    for field in ("concurrency", "otp_timeout", "proxy", "proxy_pool"):
        value = getattr(request, field)
        if value is None:
            continue
        registration[field] = value
        overrides[field] = value
    registration.update(
        want_access_token=True,
        want_session_token=True,
        want_refresh_token=True,
    )
    target_count = 1 if request.mode == "single" else request.target_count
    run = PipelineRepository(db).create(
        mode=request.mode,
        target_count=target_count,
        email=email or None,
        kakao_enabled=request.kakao_enabled,
        config_snapshot={
            "registration": registration,
            "overrides": overrides,
            "inherit_unset_fields": True,
        },
    )
    db.commit()
    db.refresh(run)
    return PipelineRunSummary.model_validate(run)


@router.post("/batch", response_model=BulkPipelineResponse)
def bulk_pipeline_action(request: BulkPipelineRequest, db: DatabaseSession) -> BulkPipelineResponse:
    run_ids = list(dict.fromkeys(run_id.strip() for run_id in request.run_ids if run_id.strip()))
    processed = 0
    if request.action == BulkPipelineAction.CANCEL:
        processed = PipelineRepository(db).cancel_runs(run_ids)
    elif request.action == BulkPipelineAction.PAUSE:
        processed = PipelineRepository(db).pause_runs(run_ids)
    elif request.action == BulkPipelineAction.RESUME:
        processed = PipelineRepository(db).resume_runs(run_ids)
    db.commit()
    return BulkPipelineResponse(processed=processed, skipped=len(run_ids) - processed)


@router.get("/{run_id}/events", response_model=PipelineEventListResponse)
def list_pipeline_events(
    run_id: str,
    db: DatabaseSession,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> PipelineEventListResponse:
    run = PipelineRepository(db).get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")
    events = PipelineRepository(db).events(run_id, after, limit)
    return PipelineEventListResponse(
        items=[
            PipelineEventSummary(
                id=event.id,
                sequence=event.sequence,
                level=event.level,
                event_type=event.event_type,
                message=event.message,
                data=event.data,
                created_at=event.created_at,
            )
            for event in events
        ],
        last_sequence=events[-1].sequence if events else after,
        terminal=run.status
        in {PipelineStatus.COMPLETED, PipelineStatus.FAILED, PipelineStatus.CANCELED},
    )


@router.post("/{run_id}/items/retry", response_model=BulkPipelineResponse)
def retry_pipeline_items(
    run_id: str,
    request: RetryPipelineItemsRequest,
    db: DatabaseSession,
) -> BulkPipelineResponse:
    if PipelineRepository(db).get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")
    item_ids = list(dict.fromkeys(value.strip() for value in request.item_ids if value.strip()))
    processed = PipelineRepository(db).retry_items(run_id, item_ids)
    db.commit()
    return BulkPipelineResponse(processed=processed, skipped=len(item_ids) - processed)


@router.get("/{run_id}", response_model=PipelineRunDetail)
def get_pipeline_run(run_id: str, db: DatabaseSession) -> PipelineRunDetail:
    repository = PipelineRepository(db)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")

    cards = [
        PipelineCardAllocationSummary(
            card_id=allocation.card_id,
            card_hint=_card_hint(code),
            allocated_count=allocation.allocated_count,
            created_count=allocation.created_count,
            duplicate_count=allocation.duplicate_count,
            failed_count=allocation.failed_count,
        )
        for allocation, code in repository.card_allocations(run_id)
    ]
    return PipelineRunDetail(
        **PipelineRunSummary.model_validate(run).model_dump(),
        config_snapshot=run.config_snapshot,
        items=[PipelineItemSummary.model_validate(item) for item in repository.items(run_id)],
        cards=cards,
    )
