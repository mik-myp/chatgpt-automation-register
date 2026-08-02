from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.kakao import KakaoCard, KakaoTask, KakaoTaskStatus
from gpt_auto_register.modules.cards.allocator import (
    CardAllocationError,
    CardAllocator,
    card_allocation_guard,
)
from gpt_auto_register.modules.kakao.client import (
    KakaoApiError,
    KakaoClient,
    canonical_payment_url,
    payload_tasks,
)
from gpt_auto_register.modules.kakao.repository import KakaoTaskRepository
from gpt_auto_register.modules.kakao.schemas import (
    KakaoCreateTasksRequest,
    KakaoCreateTasksResponse,
    KakaoEligibilityItem,
    KakaoEligibilityRequest,
    KakaoEligibilityResponse,
    KakaoTaskActionResponse,
    KakaoTaskIdsRequest,
    KakaoTaskListResponse,
    KakaoTaskSummary,
)
from gpt_auto_register.modules.kakao.state import (
    apply_payment,
    apply_retry,
    apply_upstream,
    synchronized_kakao_state,
    task_status,
)
from gpt_auto_register.modules.pipelines.repository import PipelineRepository
from gpt_auto_register.modules.settings.service import SettingsService

router = APIRouter(prefix="/kakao/tasks", tags=["kakao-tasks"])


def _client(db: DatabaseSession) -> KakaoClient:
    settings = SettingsService(db).kakao_internal()
    if not settings.base_url:
        raise HTTPException(status.HTTP_409_CONFLICT, "请先配置 Kakao Base URL")
    try:
        return KakaoClient(settings.base_url, settings.timeout)
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.get("", response_model=KakaoTaskListResponse)
def list_kakao_tasks(
    db: DatabaseSession,
    pipeline_run_id: str | None = None,
    task_status: Annotated[KakaoTaskStatus | None, Query(alias="status")] = None,
    payment_status: str = "",
    search: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KakaoTaskListResponse:
    if pipeline_run_id and PipelineRepository(db).get(pipeline_run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "流水线轮次不存在")

    items, total = KakaoTaskRepository(db).list_page(
        pipeline_run_id=pipeline_run_id,
        status=task_status,
        payment_status=payment_status.strip(),
        search=search.strip(),
        limit=limit,
        offset=offset,
    )
    changed = False
    for item in items:
        if not item.payment_url:
            item.payment_url = canonical_payment_url(item.upstream_payload or {}) or None
            changed = changed or bool(item.payment_url)
    if changed:
        db.commit()
    return KakaoTaskListResponse(
        items=[KakaoTaskSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        pipeline_run_id=pipeline_run_id,
    )


@router.post("/check", response_model=KakaoEligibilityResponse)
def check_kakao_eligibility(
    request: KakaoEligibilityRequest,
    db: DatabaseSession,
) -> KakaoEligibilityResponse:
    emails = list(dict.fromkeys(email.strip().lower() for email in request.emails if email.strip()))
    if request.all:
        emails = list(
            db.scalars(
                select(Credential.email)
                .where(
                    Credential.access_token.is_not(None),
                    Credential.access_token != "",
                )
                .order_by(Credential.created_at)
            )
        )
    if not emails:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要检查的注册结果")
    credentials = {
        value.email: value
        for value in db.scalars(select(Credential).where(Credential.email.in_(emails)))
    }
    tokens = [credentials[email].access_token for email in emails if credentials.get(email)]
    if len(tokens) != len(emails) or any(not token for token in tokens):
        raise HTTPException(status.HTTP_409_CONFLICT, "部分注册结果缺少 Access Token")
    client = _client(db)
    checked_at = utc_now().isoformat()
    items: list[KakaoEligibilityItem] = []
    for start in range(0, len(emails), 50):
        group_emails = emails[start : start + 50]
        try:
            values = payload_tasks(
                client.check_eligibility(
                    [str(credentials[email].access_token) for email in group_emails]
                )
            )
        except KakaoApiError as error:
            raise HTTPException(error.status_code, str(error)) from error
        by_index = {
            str(value.get("index")): value for value in values if value.get("index") is not None
        }
        for index, email in enumerate(group_emails):
            value = by_index.get(str(index)) or (values[index] if index < len(values) else {})
            eligible = value.get("eligible") is True
            state_value = str(value.get("state") or "unknown")
            error_value = str(value.get("error") or "")
            credential = credentials[email]
            credential.metadata_json = {
                **credential.metadata_json,
                "kakao_eligible": eligible,
                "kakao_state": state_value,
                "kakao_error": error_value,
                "kakao_checked_at": checked_at,
            }
            items.append(
                KakaoEligibilityItem(
                    email=email,
                    eligible=eligible,
                    state=state_value,
                    error=error_value,
                )
            )
    db.commit()
    return KakaoEligibilityResponse(items=items)


@router.post("/create", response_model=KakaoCreateTasksResponse)
def create_kakao_tasks(
    request: KakaoCreateTasksRequest,
    db: DatabaseSession,
) -> KakaoCreateTasksResponse:
    emails = list(dict.fromkeys(email.strip().lower() for email in request.emails if email.strip()))
    credentials = {
        value.email: value
        for value in db.scalars(select(Credential).where(Credential.email.in_(emails)))
    }
    if any(not credentials.get(email) or not credentials[email].access_token for email in emails):
        raise HTTPException(status.HTTP_409_CONFLICT, "部分注册结果缺少 Access Token")
    try:
        with card_allocation_guard():
            slots, _ = CardAllocator(db).select(len(emails))
            client = _client(db)
            settings = SettingsService(db).kakao_internal()
            created = duplicates = 0
            for email, card_code in zip(emails, slots, strict=True):
                payload = client.create_tasks(
                    card=card_code,
                    access_tokens=[str(credentials[email].access_token)],
                    plan_type=settings.plan_type,
                    promo_code=settings.promo_code,
                )
                card = db.scalar(select(KakaoCard).where(KakaoCard.code == card_code))
                if card is None:
                    continue
                for value in payload_tasks(payload):
                    upstream_id = str(value.get("job_id") or value.get("id") or "")
                    if not upstream_id:
                        continue
                    existing = db.scalar(
                        select(KakaoTask).where(KakaoTask.upstream_job_id == upstream_id)
                    )
                    if existing:
                        duplicates += 1
                        continue
                    task = KakaoTask(
                        upstream_job_id=upstream_id,
                        card_id=card.id,
                        card_code_snapshot=card.code,
                        email=email,
                        status=task_status(value.get("status")),
                    )
                    apply_upstream(task, value)
                    db.add(task)
                    created += 1
            db.commit()
        return KakaoCreateTasksResponse(created=created, duplicates=duplicates)
    except (CardAllocationError, KakaoApiError) as error:
        status_code = (
            error.status_code if isinstance(error, KakaoApiError) else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code, str(error)) from error


@router.post("/sync", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def sync_kakao_tasks(
    request: KakaoTaskIdsRequest,
    db: DatabaseSession,
) -> KakaoTaskActionResponse:
    tasks = KakaoTaskRepository(db).selected(request.task_ids, request.pipeline_run_id)
    if not tasks:
        return KakaoTaskActionResponse(processed=0)
    processed = failed = 0
    client = _client(db)
    for start in range(0, len(tasks), 50):
        group = tasks[start : start + 50]
        try:
            values = payload_tasks(client.task_statuses([task.upstream_job_id for task in group]))
            by_id = {str(value.get("job_id") or value.get("id") or ""): value for value in values}
            for task in group:
                value = by_id.get(task.upstream_job_id)
                if value is None:
                    failed += 1
                    continue
                apply_upstream(task, value)
                processed += 1
        except KakaoApiError:
            failed += len(group)
    db.commit()
    return KakaoTaskActionResponse(processed=processed, failed=failed)


@router.post("/payment-sync", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def sync_kakao_payment_statuses(
    request: KakaoTaskIdsRequest,
    db: DatabaseSession,
) -> KakaoTaskActionResponse:
    tasks = [
        task
        for task in KakaoTaskRepository(db).selected(request.task_ids, request.pipeline_run_id)
        if task.status == KakaoTaskStatus.DONE
        and task.payment_status not in {"succeeded", "failed", "canceled", "expired"}
    ]
    if not tasks:
        return KakaoTaskActionResponse(processed=0)
    client = _client(db)

    def fetch(task: KakaoTask) -> tuple[str, object]:
        try:
            return task.id, client.kakao_status(task.upstream_job_id)
        except KakaoApiError as error:
            return task.id, error

    workers = min(8, len(tasks))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = dict(executor.map(fetch, tasks))
    processed = failed = 0
    for task in tasks:
        value = results.get(task.id)
        if isinstance(value, KakaoApiError) or not isinstance(value, dict):
            failed += 1
            continue
        apply_payment(task, value)
        processed += 1
    db.commit()
    return KakaoTaskActionResponse(processed=processed, failed=failed)


@router.get("/{task_id}/upstream")
def get_kakao_task_upstream(task_id: str, db: DatabaseSession) -> object:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    try:
        return _client(db).task_detail(task.upstream_job_id)
    except KakaoApiError as error:
        raise HTTPException(error.status_code, str(error)) from error


@router.get("/{task_id}/details")
@synchronized_kakao_state
def get_kakao_task_details(task_id: str, db: DatabaseSession) -> object:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    client = _client(db)
    detail: object | None = None
    kakao_status: object | None = None
    detail_error = kakao_error = ""
    try:
        detail = client.task_detail(task.upstream_job_id)
        if isinstance(detail, dict):
            apply_upstream(task, detail)
    except KakaoApiError as error:
        detail_error = str(error)
    try:
        kakao_status = client.kakao_status(task.upstream_job_id)
        if isinstance(kakao_status, dict):
            apply_payment(task, kakao_status)
    except KakaoApiError as error:
        kakao_error = str(error)
    db.commit()
    return {
        "local": KakaoTaskSummary.model_validate(task).model_dump(mode="json"),
        "task": detail,
        "task_error": detail_error,
        "kakao_status": kakao_status,
        "kakao_status_error": kakao_error,
    }


@router.post("/{task_id}/cancel", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def cancel_kakao_task(task_id: str, db: DatabaseSession) -> KakaoTaskActionResponse:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    try:
        payload = _client(db).cancel_task(task.upstream_job_id)
        values = payload_tasks(payload)
        apply_upstream(task, values[0] if values else {"status": "canceled"})
        db.commit()
        return KakaoTaskActionResponse(processed=1)
    except KakaoApiError as error:
        raise HTTPException(error.status_code, str(error)) from error


@router.post("/{task_id}/retry", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def retry_kakao_task(task_id: str, db: DatabaseSession) -> KakaoTaskActionResponse:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    try:
        payload = _client(db).retry_task(task.upstream_job_id)
        values = payload_tasks(payload)
        apply_retry(task, values[0] if values else {"status": "queued"})
        db.commit()
        return KakaoTaskActionResponse(processed=1)
    except KakaoApiError as error:
        raise HTTPException(error.status_code, str(error)) from error
