from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.kakao import KakaoTaskStatus
from gpt_auto_register.modules.kakao.repository import KakaoTaskRepository
from gpt_auto_register.modules.kakao.schemas import (
    KakaoEligibilityItem,
    KakaoEligibilityRequest,
    KakaoEligibilityResponse,
    KakaoTaskActionResponse,
    KakaoTaskIdsRequest,
    KakaoTaskListResponse,
    KakaoTaskSummary,
)
from gpt_auto_register.modules.kakao.state import (
    completed_extraction_emails,
    mark_extraction_completed,
    release_extraction_claim,
    synchronized_kakao_state,
)
from gpt_auto_register.modules.pipelines.repository import PipelineRepository

router = APIRouter(prefix="/kakao/tasks", tags=["kakao-tasks"])


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
        changed = mark_extraction_completed(db, item) or changed
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
    checked_at = utc_now().isoformat()
    items: list[KakaoEligibilityItem] = []
    completed = completed_extraction_emails(db, emails)
    for email in emails:
        eligible = email not in completed
        state_value = "eligible" if eligible else "already_extracted"
        error_value = "" if eligible else "该邮箱已生成过 Kakao 支付链接"
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


@router.post("/sync", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def sync_kakao_tasks(
    request: KakaoTaskIdsRequest,
    db: DatabaseSession,
) -> KakaoTaskActionResponse:
    tasks = KakaoTaskRepository(db).selected(request.task_ids, request.pipeline_run_id)
    if not tasks:
        return KakaoTaskActionResponse(processed=0)
    changed = False
    for task in tasks:
        changed = mark_extraction_completed(db, task) or changed
    if changed:
        db.commit()
    return KakaoTaskActionResponse(processed=len(tasks), failed=0)


@router.post("/payment-sync", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def sync_kakao_payment_statuses(
    request: KakaoTaskIdsRequest,
    db: DatabaseSession,
) -> KakaoTaskActionResponse:
    tasks = KakaoTaskRepository(db).selected(request.task_ids, request.pipeline_run_id)
    changed = False
    for task in tasks:
        changed = mark_extraction_completed(db, task) or changed
    if changed:
        db.commit()
    return KakaoTaskActionResponse(processed=len(tasks), failed=0)


@router.get("/{task_id}/upstream")
def get_kakao_task_upstream(task_id: str, db: DatabaseSession) -> object:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    return task.upstream_payload


@router.get("/{task_id}/details")
@synchronized_kakao_state
def get_kakao_task_details(task_id: str, db: DatabaseSession) -> object:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    return {
        "local": KakaoTaskSummary.model_validate(task).model_dump(mode="json"),
        "task": task.upstream_payload,
        "task_error": "",
        "kakao_status": {"payment_status": task.payment_status},
        "kakao_status_error": "",
    }


@router.post("/{task_id}/cancel", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def cancel_kakao_task(task_id: str, db: DatabaseSession) -> KakaoTaskActionResponse:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    if task.status in {KakaoTaskStatus.DONE, KakaoTaskStatus.FAILED, KakaoTaskStatus.CANCELED}:
        return KakaoTaskActionResponse(processed=0)
    task.status = KakaoTaskStatus.CANCELED
    task.payment_status = "canceled"
    task.error = "用户取消"
    release_extraction_claim(db, task)
    db.commit()
    return KakaoTaskActionResponse(processed=1)


@router.post("/{task_id}/retry", response_model=KakaoTaskActionResponse)
@synchronized_kakao_state
def retry_kakao_task(task_id: str, db: DatabaseSession) -> KakaoTaskActionResponse:
    task = KakaoTaskRepository(db).get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kakao 任务不存在")
    if task.email.strip().lower() in completed_extraction_emails(db, [task.email]):
        raise HTTPException(status.HTTP_409_CONFLICT, "该邮箱已生成过 Kakao 支付链接")
    release_extraction_claim(db, task)
    PipelineRepository(db).create_kakao(
        source_run_id=task.pipeline_run_id,
        emails=[task.email.strip().lower()],
    )
    db.commit()
    return KakaoTaskActionResponse(processed=1)
