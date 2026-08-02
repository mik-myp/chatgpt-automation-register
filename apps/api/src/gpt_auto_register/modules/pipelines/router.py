import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.jobs import Job, JobEvent, JobStatus
from gpt_auto_register.db.models.kakao import KakaoTask, KakaoTaskStatus
from gpt_auto_register.db.models.pipeline import (
    PipelineItem,
    PipelineRun,
    PipelineRunKind,
    PipelineStatus,
)
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.cards.allocator import (
    CardAllocationError,
    CardAllocator,
    card_allocation_guard,
)
from gpt_auto_register.modules.kakao.state import completed_extraction_emails
from gpt_auto_register.modules.pipelines.candidates import (
    list_kakao_candidate_credentials,
    list_security_candidate_credentials,
)
from gpt_auto_register.modules.pipelines.delivery import (
    account_copy_fingerprint,
    format_deliveries,
    list_deliveries,
    list_security_deliveries,
    plus_check_fields,
)
from gpt_auto_register.modules.pipelines.repository import PipelineRepository
from gpt_auto_register.modules.pipelines.schemas import (
    BulkPipelineAction,
    BulkPipelineRequest,
    BulkPipelineResponse,
    ConfirmPipelineDeliveryCopiesRequest,
    ConfirmPipelineDeliveryCopiesResponse,
    CopyPipelineDeliveriesRequest,
    CopyPipelineDeliveriesResponse,
    CopySecurityCredentialsRequest,
    CreateKakaoPipelineRequest,
    CreateSecurityPipelineRequest,
    KakaoPipelineCandidate,
    KakaoPipelineCandidateList,
    KakaoPipelineCandidatePage,
    PipelineCardAllocationSummary,
    PipelineCardAssignmentSummary,
    PipelineDeliveryCopyMark,
    PipelineDeliveryListResponse,
    PipelineEventListResponse,
    PipelineEventSummary,
    PipelineItemSummary,
    PipelineRunCreateRequest,
    PipelineRunDetail,
    PipelineRunListResponse,
    PipelineRunSummary,
    RetryPipelineItemsRequest,
    SecurityPipelineCandidate,
    SecurityPipelineCandidateList,
    SecurityPipelineCandidatePage,
)
from gpt_auto_register.modules.settings.service import SettingsService

router = APIRouter(prefix="/pipelines/runs", tags=["pipeline-runs"])


def _event_summary(event: JobEvent) -> PipelineEventSummary:
    return PipelineEventSummary(
        id=event.id,
        sequence=event.sequence,
        level=event.level,
        event_type=event.event_type,
        message=event.message,
        data=event.data,
        created_at=event.created_at,
    )


def _fixed_password(db: DatabaseSession) -> str:
    registration = SettingsService(db).registration_internal()
    return registration.fixed_password if registration.password_mode == "fixed" else ""


def _account_copy_history(db: DatabaseSession, emails: list[str]) -> dict[str, str]:
    history: dict[str, str] = {}
    for email, credential in AccountRepository(db).credentials(emails).items():
        metadata = credential.metadata_json or {}
        delivery_copy = metadata.get("delivery_copy")
        if not isinstance(delivery_copy, dict):
            continue
        fingerprint = str(delivery_copy.get("account_fingerprint") or "")
        if fingerprint:
            history[email] = fingerprint
    return history


def _security_state(
    credential: Credential | None, fixed_password: str
) -> tuple[str, str, str | None, bool, bool]:
    metadata = (
        credential.metadata_json
        if credential and isinstance(credential.metadata_json, dict)
        else {}
    )
    security = metadata.get("account_security")
    security = security if isinstance(security, dict) else {}
    password = security.get("password")
    password = password if isinstance(password, dict) else {}
    mfa = security.get("mfa")
    mfa = mfa if isinstance(mfa, dict) else {}
    password_status = str(
        password.get("status") or ("set" if credential and credential.password else "not_set")
    )
    mfa_status = str(
        mfa.get("status") or ("enabled" if credential and credential.totp_secret else "not_enabled")
    )
    has_password = bool(credential and credential.password) or (
        bool(fixed_password) and password_status in {"set", "available"}
    )
    needs_password = not has_password or password_status not in {"set", "available"}
    needs_mfa = not bool(credential and credential.totp_secret) or mfa_status != "enabled"
    error = str(mfa.get("error") or password.get("error") or "") or None
    return password_status, mfa_status, error, needs_password, needs_mfa


def _busy_security_emails(db: DatabaseSession) -> set[str]:
    return {
        str(email).strip().lower()
        for job in db.scalars(
            select(Job).where(
                Job.kind == "account.security",
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        for email in job.payload.get("emails", [])
        if str(email).strip()
    }


def _busy_kakao_emails(db: DatabaseSession) -> set[str]:
    pipeline_emails = {
        str(email).strip().lower()
        for email in db.scalars(
            select(PipelineItem.account_email)
            .join(PipelineRun, PipelineRun.id == PipelineItem.pipeline_run_id)
            .where(
                PipelineRun.kind == PipelineRunKind.KAKAO,
                PipelineRun.status.in_(
                    [PipelineStatus.QUEUED, PipelineStatus.RUNNING, PipelineStatus.PAUSED]
                ),
                PipelineItem.account_email.is_not(None),
            )
        )
        if email
    }
    task_emails = {
        str(email).strip().lower()
        for email in db.scalars(
            select(KakaoTask.email).where(
                KakaoTask.status.in_([KakaoTaskStatus.QUEUED, KakaoTaskStatus.EXTRACTING])
            )
        )
        if email
    }
    return pipeline_emails | task_emails


def _kakao_candidate(credential: Credential) -> KakaoPipelineCandidate:
    metadata = credential.metadata_json if isinstance(credential.metadata_json, dict) else {}
    pipeline = metadata.get("kakao_pipeline")
    pipeline = pipeline if isinstance(pipeline, dict) else {}
    return KakaoPipelineCandidate(
        email=credential.email,
        eligibility_state=(str(metadata.get("kakao_state") or pipeline.get("state") or "") or None),
        eligibility_error=(str(metadata.get("kakao_error") or pipeline.get("error") or "") or None),
        eligibility_checked_at=(
            metadata.get("kakao_checked_at") or pipeline.get("checked_at") or None
        ),
    )


def _eligible_kakao_accounts(
    db: DatabaseSession,
    requested: list[str],
    *,
    allowed_emails: set[str] | None = None,
) -> list[str]:
    credentials = AccountRepository(db).credentials(requested)
    busy_emails = _busy_kakao_emails(db)
    completed_emails = completed_extraction_emails(db, requested)
    return [
        email
        for email in requested
        if (credential := credentials.get(email)) is not None
        and bool(credential.access_token)
        and email not in busy_emails
        and email not in completed_emails
        and (allowed_emails is None or email in allowed_emails)
    ]


def _create_kakao_pipeline(
    db: DatabaseSession,
    requested: list[str],
    *,
    source_run_id: str | None = None,
    allowed_emails: set[str] | None = None,
) -> PipelineRunSummary:
    completed_emails = completed_extraction_emails(db, requested)
    if completed_emails:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"所选账号中有 {len(completed_emails)} 个已生成过 Kakao 支付链接，请刷新后重新选择",
        )
    eligible = _eligible_kakao_accounts(
        db,
        requested,
        allowed_emails=allowed_emails,
    )
    if not eligible:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "所选账号正在其他 Kakao 轮次中、缺少 Access Token、不属于来源轮次或已完成提取",
        )
    try:
        with card_allocation_guard():
            card_slots, _ = CardAllocator(db).select(len(eligible))
            run = PipelineRepository(db).create_kakao(
                source_run_id=source_run_id,
                emails=eligible,
                card_slots=card_slots,
            )
            db.commit()
    except CardAllocationError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.refresh(run)
    return PipelineRunSummary.model_validate(run)


def _eligible_security_accounts(
    db: DatabaseSession,
    requested: list[str],
    *,
    allowed_emails: set[str] | None = None,
) -> tuple[list[str], dict[str, tuple[str, str]]]:
    credentials = AccountRepository(db).credentials(requested)
    account_emails = set(
        db.scalars(select(OutlookAccount.email).where(OutlookAccount.email.in_(requested)))
    )
    busy_emails = _busy_security_emails(db)
    fixed_password = _fixed_password(db)
    eligible: list[str] = []
    states: dict[str, tuple[str, str]] = {}
    for email in requested:
        credential = credentials.get(email)
        if (
            email not in account_emails
            or credential is None
            or email in busy_emails
            or (allowed_emails is not None and email not in allowed_emails)
        ):
            continue
        password_status, mfa_status, _, needs_password, needs_mfa = _security_state(
            credential, fixed_password
        )
        if not needs_password and not needs_mfa:
            continue
        eligible.append(email)
        states[email] = (password_status, mfa_status)
    return eligible, states


def _create_security_pipeline(
    db: DatabaseSession,
    requested: list[str],
    *,
    source_run_id: str | None = None,
    allowed_emails: set[str] | None = None,
) -> PipelineRunSummary:
    eligible, states = _eligible_security_accounts(
        db,
        requested,
        allowed_emails=allowed_emails,
    )
    if not eligible:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "所选账号均已完成安全设置、正在其他任务中或缺少凭据",
        )
    repository = PipelineRepository(db)
    run = repository.create_security(source_run_id=source_run_id, emails=eligible)
    for item in repository.items(run.id):
        password_status, mfa_status = states[item.account_email or ""]
        item.password_status = password_status
        item.mfa_status = mfa_status
    db.commit()
    db.refresh(run)
    return PipelineRunSummary.model_validate(run)


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
    return PipelineRunListResponse(
        items=[PipelineRunSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


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
    try:
        with card_allocation_guard():
            card_slots = (
                CardAllocator(db).select(target_count)[0] if request.kakao_enabled else None
            )
            run = PipelineRepository(db).create(
                mode=request.mode,
                target_count=target_count,
                email=email or None,
                kakao_enabled=request.kakao_enabled,
                card_slots=card_slots,
                config_snapshot={
                    "registration": registration,
                    "overrides": overrides,
                    "inherit_unset_fields": True,
                },
            )
            db.commit()
    except CardAllocationError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
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
    elif request.action == BulkPipelineAction.DELETE:
        processed = PipelineRepository(db).delete_runs(run_ids)
    db.commit()
    return BulkPipelineResponse(processed=processed, skipped=len(run_ids) - processed)


@router.get("/security-candidates", response_model=SecurityPipelineCandidatePage)
def list_global_security_pipeline_candidates(
    db: DatabaseSession,
    search: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SecurityPipelineCandidatePage:
    busy_emails = _busy_security_emails(db)
    fixed_password = _fixed_password(db)
    credentials, total = list_security_candidate_credentials(
        db,
        busy_emails=busy_emails,
        fixed_password_available=bool(fixed_password),
        search=search,
        limit=limit,
        offset=offset,
    )
    candidates: list[SecurityPipelineCandidate] = []
    for credential in credentials:
        password_status, mfa_status, error, needs_password, needs_mfa = _security_state(
            credential, fixed_password
        )
        candidates.append(
            SecurityPipelineCandidate(
                email=credential.email,
                password_status=password_status,
                mfa_status=mfa_status,
                security_error=error,
                needs_password=needs_password,
                needs_mfa=needs_mfa,
            )
        )
    return SecurityPipelineCandidatePage(
        items=candidates,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/security-runs",
    response_model=PipelineRunSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_global_security_pipeline_run(
    request: CreateSecurityPipelineRequest,
    db: DatabaseSession,
) -> PipelineRunSummary:
    requested = list(
        dict.fromkeys(email.strip().lower() for email in request.emails if email.strip())
    )
    return _create_security_pipeline(db, requested)


@router.get("/kakao-candidates", response_model=KakaoPipelineCandidatePage)
def list_global_kakao_pipeline_candidates(
    db: DatabaseSession,
    search: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KakaoPipelineCandidatePage:
    busy_emails = _busy_kakao_emails(db)
    credentials, total = list_kakao_candidate_credentials(
        db,
        busy_emails=busy_emails,
        search=search,
        limit=limit,
        offset=offset,
    )
    candidates = [_kakao_candidate(credential) for credential in credentials]
    return KakaoPipelineCandidatePage(
        items=candidates,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/kakao-runs",
    response_model=PipelineRunSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_global_kakao_pipeline_run(
    request: CreateKakaoPipelineRequest,
    db: DatabaseSession,
) -> PipelineRunSummary:
    requested = list(
        dict.fromkeys(email.strip().lower() for email in request.emails if email.strip())
    )
    return _create_kakao_pipeline(db, requested)


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
        items=[_event_summary(event) for event in events],
        last_sequence=events[-1].sequence if events else after,
        terminal=run.status
        in {PipelineStatus.COMPLETED, PipelineStatus.FAILED, PipelineStatus.CANCELED},
    )


@router.get("/{run_id}/events/stream", response_class=StreamingResponse)
def stream_pipeline_events(
    run_id: str,
    request: Request,
    db: DatabaseSession,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    if PipelineRepository(db).get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")

    async def stream() -> AsyncIterator[str]:
        sequence = after
        idle_ticks = 0
        while not await request.is_disconnected():
            with SessionLocal() as session:
                repository = PipelineRepository(session)
                run = repository.get(run_id)
                if run is None:
                    return
                events = repository.events(run_id, sequence, 200)
                terminal = run.status in {
                    PipelineStatus.COMPLETED,
                    PipelineStatus.FAILED,
                    PipelineStatus.CANCELED,
                }
                summaries = [_event_summary(event).model_dump(mode="json") for event in events]
            if summaries:
                idle_ticks = 0
                for index, summary in enumerate(summaries):
                    sequence = int(summary["sequence"])
                    payload = {
                        "event": summary,
                        "terminal": terminal and index == len(summaries) - 1,
                    }
                    encoded = json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    yield (f"id: {sequence}\ndata: {encoded}\n\n")
            elif terminal:
                yield 'data: {"terminal":true}\n\n'
            else:
                idle_ticks += 1
                if idle_ticks % 30 == 0:
                    yield ": keep-alive\n\n"
            if terminal:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{run_id}/items/retry", response_model=BulkPipelineResponse)
def retry_pipeline_items(
    run_id: str,
    request: RetryPipelineItemsRequest,
    db: DatabaseSession,
) -> BulkPipelineResponse:
    item_ids = list(dict.fromkeys(value.strip() for value in request.item_ids if value.strip()))
    repository = PipelineRepository(db)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")
    if run.kind == PipelineRunKind.ACCOUNT_SECURITY:
        processed = repository.retry_security_items(run_id, item_ids)
    elif run.kind == PipelineRunKind.KAKAO:
        processed = repository.retry_kakao_items(run_id, item_ids)
    else:
        processed = repository.retry_items(run_id, item_ids)
    db.commit()
    return BulkPipelineResponse(processed=processed, skipped=len(item_ids) - processed)


@router.get(
    "/{run_id}/security-candidates",
    response_model=SecurityPipelineCandidateList,
)
def list_security_pipeline_candidates(
    run_id: str,
    db: DatabaseSession,
) -> SecurityPipelineCandidateList:
    repository = PipelineRepository(db)
    run = repository.get(run_id)
    if run is None or run.kind != PipelineRunKind.REGISTRATION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "注册流水线轮次不存在")
    emails = list(
        dict.fromkeys(item.account_email for item in repository.items(run_id) if item.account_email)
    )
    credentials = AccountRepository(db).credentials(emails)
    fixed_password = _fixed_password(db)
    items = []
    for email in emails:
        password_status, mfa_status, error, needs_password, needs_mfa = _security_state(
            credentials.get(email), fixed_password
        )
        if not needs_password and not needs_mfa:
            continue
        items.append(
            SecurityPipelineCandidate(
                email=email,
                password_status=password_status,
                mfa_status=mfa_status,
                security_error=error,
                needs_password=needs_password,
                needs_mfa=needs_mfa,
            )
        )
    return SecurityPipelineCandidateList(items=items)


@router.post(
    "/{run_id}/security-runs",
    response_model=PipelineRunSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_security_pipeline_run(
    run_id: str,
    request: CreateSecurityPipelineRequest,
    db: DatabaseSession,
) -> PipelineRunSummary:
    repository = PipelineRepository(db)
    source = repository.get(run_id)
    if source is None or source.kind != PipelineRunKind.REGISTRATION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "注册流水线轮次不存在")
    requested = list(
        dict.fromkeys(email.strip().lower() for email in request.emails if email.strip())
    )
    source_emails = {
        str(item.account_email).lower() for item in repository.items(run_id) if item.account_email
    }
    return _create_security_pipeline(
        db,
        requested,
        source_run_id=source.id,
        allowed_emails=source_emails,
    )


@router.get(
    "/{run_id}/kakao-candidates",
    response_model=KakaoPipelineCandidateList,
)
def list_kakao_pipeline_candidates(
    run_id: str,
    db: DatabaseSession,
) -> KakaoPipelineCandidateList:
    repository = PipelineRepository(db)
    run = repository.get(run_id)
    if run is None or run.kind != PipelineRunKind.REGISTRATION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "注册流水线轮次不存在")
    emails = list(
        dict.fromkeys(item.account_email for item in repository.items(run_id) if item.account_email)
    )
    credentials = AccountRepository(db).credentials(emails)
    busy_emails = _busy_kakao_emails(db)
    completed_emails = completed_extraction_emails(db, emails)
    return KakaoPipelineCandidateList(
        items=[
            _kakao_candidate(credentials[email])
            for email in emails
            if email in credentials
            and credentials[email].access_token
            and email not in busy_emails
            and email not in completed_emails
        ]
    )


@router.post(
    "/{run_id}/kakao-runs",
    response_model=PipelineRunSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_kakao_pipeline_run(
    run_id: str,
    request: CreateKakaoPipelineRequest,
    db: DatabaseSession,
) -> PipelineRunSummary:
    repository = PipelineRepository(db)
    source = repository.get(run_id)
    if source is None or source.kind != PipelineRunKind.REGISTRATION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "注册流水线轮次不存在")
    requested = list(
        dict.fromkeys(email.strip().lower() for email in request.emails if email.strip())
    )
    source_emails = {
        str(item.account_email).lower() for item in repository.items(run_id) if item.account_email
    }
    return _create_kakao_pipeline(
        db,
        requested,
        source_run_id=source.id,
        allowed_emails=source_emails,
    )


@router.post(
    "/{run_id}/security-credentials/copy",
    response_model=CopyPipelineDeliveriesResponse,
)
def copy_security_pipeline_credentials(
    run_id: str,
    request: CopySecurityCredentialsRequest,
    db: DatabaseSession,
) -> CopyPipelineDeliveriesResponse:
    run = PipelineRepository(db).get(run_id)
    if run is None or run.kind != PipelineRunKind.ACCOUNT_SECURITY:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "安全处理流水线不存在")
    item_ids = None if request.all_completed else list(dict.fromkeys(request.item_ids))
    if item_ids == []:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要复制的账号")
    page = list_security_deliveries(
        db,
        run_id,
        fixed_password=_fixed_password(db),
        item_ids=item_ids,
    )
    (
        text,
        copied,
        skipped,
        security_credentials,
        mail_access,
        missing_mail_url,
        duplicates,
        plus_restricted,
        copy_marks,
    ) = format_deliveries(
        page.items,
        SettingsService(db).get().delivery_copy,
        "account_info",
        _account_copy_history(db, [item.email for item in page.items]),
    )
    return CopyPipelineDeliveriesResponse(
        text=text,
        copied=copied,
        skipped=skipped,
        security_credentials=security_credentials,
        mail_access=mail_access,
        missing_mail_url=missing_mail_url,
        duplicates=duplicates,
        plus_restricted=plus_restricted,
        copy_marks=[
            PipelineDeliveryCopyMark(email=email, fingerprint=fingerprint)
            for email, fingerprint in copy_marks
        ],
    )


@router.get("/{run_id}/deliveries", response_model=PipelineDeliveryListResponse)
def list_pipeline_deliveries(
    run_id: str,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PipelineDeliveryListResponse:
    if PipelineRepository(db).get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")
    page = list_deliveries(
        db,
        run_id,
        fixed_password=_fixed_password(db),
        limit=limit,
        offset=offset,
    )
    return PipelineDeliveryListResponse(
        items=page.items,
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.post("/{run_id}/deliveries/copy", response_model=CopyPipelineDeliveriesResponse)
def copy_pipeline_deliveries(
    run_id: str,
    request: CopyPipelineDeliveriesRequest,
    db: DatabaseSession,
) -> CopyPipelineDeliveriesResponse:
    if PipelineRepository(db).get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")
    task_ids = None if request.all_deliverable else list(dict.fromkeys(request.task_ids))
    if task_ids == []:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要复制的交付信息")
    page = list_deliveries(
        db,
        run_id,
        fixed_password=_fixed_password(db),
        task_ids=task_ids,
    )
    (
        text,
        copied,
        skipped,
        security_credentials,
        mail_access,
        missing_mail_url,
        duplicates,
        plus_restricted,
        copy_marks,
    ) = format_deliveries(
        page.items,
        SettingsService(db).get().delivery_copy,
        request.copy_type,
        _account_copy_history(db, [item.email for item in page.items]),
    )
    return CopyPipelineDeliveriesResponse(
        text=text,
        copied=copied,
        skipped=skipped,
        security_credentials=security_credentials,
        mail_access=mail_access,
        missing_mail_url=missing_mail_url,
        duplicates=duplicates,
        plus_restricted=plus_restricted,
        copy_marks=[
            PipelineDeliveryCopyMark(email=email, fingerprint=fingerprint)
            for email, fingerprint in copy_marks
        ],
    )


@router.post(
    "/{run_id}/deliveries/copy/confirm",
    response_model=ConfirmPipelineDeliveryCopiesResponse,
)
def confirm_pipeline_delivery_copies(
    run_id: str,
    request: ConfirmPipelineDeliveryCopiesRequest,
    db: DatabaseSession,
) -> ConfirmPipelineDeliveryCopiesResponse:
    run = PipelineRepository(db).get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")
    page = (
        list_security_deliveries(db, run_id, fixed_password=_fixed_password(db))
        if run.kind == PipelineRunKind.ACCOUNT_SECURITY
        else list_deliveries(db, run_id, fixed_password=_fixed_password(db))
    )
    current: dict[str, str] = {}
    for item in page.items:
        fingerprint = account_copy_fingerprint(item)
        if fingerprint:
            current[item.email.lower()] = fingerprint
    credentials = AccountRepository(db).credentials(list(current))
    processed = 0
    for mark in request.copy_marks:
        email = mark.email.strip().lower()
        if current.get(email) != mark.fingerprint:
            continue
        credential = credentials.get(email)
        if credential is None:
            continue
        metadata = credential.metadata_json or {}
        delivery_copy = metadata.get("delivery_copy")
        delivery_copy = delivery_copy if isinstance(delivery_copy, dict) else {}
        credential.metadata_json = {
            **metadata,
            "delivery_copy": {
                **delivery_copy,
                "account_fingerprint": mark.fingerprint,
                "account_copied_at": utc_now().isoformat(),
                "pipeline_run_id": run_id,
            },
        }
        processed += 1
    db.commit()
    return ConfirmPipelineDeliveryCopiesResponse(processed=processed)


@router.get("/{run_id}", response_model=PipelineRunDetail)
def get_pipeline_run(run_id: str, db: DatabaseSession) -> PipelineRunDetail:
    repository = PipelineRepository(db)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")

    credentials = AccountRepository(db).credentials(
        [item.account_email for item in repository.items(run_id) if item.account_email]
    )
    items = []
    for item in repository.items(run_id):
        values = PipelineItemSummary.model_validate(item).model_dump()
        values.update(plus_check_fields(credentials.get(item.account_email or "")))
        items.append(PipelineItemSummary.model_validate(values))
    assignments_by_card: dict[str, list[PipelineCardAssignmentSummary]] = {}
    assignments_by_code: dict[str, list[PipelineCardAssignmentSummary]] = {}
    for task in repository.card_assignments(run_id):
        assignment = PipelineCardAssignmentSummary(
            task_id=task.id,
            email=task.email,
            status=task.status,
            payment_status=task.payment_status,
            card_charged=task.card_charged,
        )
        if task.card_id:
            assignments_by_card.setdefault(task.card_id, []).append(assignment)
        if task.card_code_snapshot:
            assignments_by_code.setdefault(task.card_code_snapshot, []).append(assignment)
    cards = [
        PipelineCardAllocationSummary(
            card_id=allocation.card_id,
            card_code=code,
            allocated_count=allocation.allocated_count,
            created_count=allocation.created_count,
            duplicate_count=allocation.duplicate_count,
            failed_count=allocation.failed_count,
            assignments=assignments_by_card.get(
                allocation.card_id, assignments_by_code.get(code, [])
            ),
        )
        for allocation, code in repository.card_allocations(run_id)
    ]
    return PipelineRunDetail(
        **PipelineRunSummary.model_validate(run).model_dump(),
        config_snapshot=run.config_snapshot,
        items=items,
        cards=cards,
    )
