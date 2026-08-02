import threading
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.models.kakao import (
    KakaoClaimState,
    KakaoEmailClaim,
    KakaoTask,
    KakaoTaskStatus,
)
from gpt_auto_register.modules.kakao.client import (
    canonical_payment_url,
    normalized_payment_state,
)

_KAKAO_STATE_LOCK = threading.RLock()
_EXTRACTION_METADATA_KEY = "kakao_extraction"


class KakaoClaimConflictError(RuntimeError):
    pass


def synchronized_kakao_state[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with _KAKAO_STATE_LOCK:
            return function(*args, **kwargs)

    return wrapper


def task_status(value: object) -> KakaoTaskStatus:
    try:
        return KakaoTaskStatus(str(value or "queued").lower())
    except ValueError:
        return KakaoTaskStatus.QUEUED


_TASK_STATUS_RANK = {
    KakaoTaskStatus.QUEUED: 0,
    KakaoTaskStatus.EXTRACTING: 1,
    KakaoTaskStatus.DONE: 2,
    KakaoTaskStatus.FAILED: 2,
    KakaoTaskStatus.CANCELED: 2,
}
_TASK_TERMINAL = {
    KakaoTaskStatus.DONE,
    KakaoTaskStatus.FAILED,
    KakaoTaskStatus.CANCELED,
}
_PAYMENT_STATUS_RANK = {
    "waiting": 0,
    "ready": 0,
    "opened": 1,
    "succeeded": 2,
    "failed": 2,
    "canceled": 2,
    "expired": 2,
}
_PAYMENT_TERMINAL = {"succeeded", "failed", "canceled", "expired"}


def _advance_task_status(task: KakaoTask, incoming: KakaoTaskStatus) -> bool:
    current = task.status
    if current in _TASK_TERMINAL and incoming != current:
        return False
    if current is not None and _TASK_STATUS_RANK[incoming] < _TASK_STATUS_RANK[current]:
        return False
    task.status = incoming
    return True


def _advance_payment_status(task: KakaoTask, incoming: str) -> bool:
    current = str(task.payment_status or "")
    if not incoming:
        return False
    if current in _PAYMENT_TERMINAL and incoming != current:
        return False
    if _PAYMENT_STATUS_RANK.get(incoming, -1) < _PAYMENT_STATUS_RANK.get(current, -1):
        return False
    task.payment_status = incoming
    return True


def completed_extraction_emails(
    session: Session,
    emails: Iterable[str] | None = None,
) -> set[str]:
    requested = (
        {str(email).strip().lower() for email in emails if str(email).strip()}
        if emails is not None
        else None
    )
    credential_query = select(Credential)
    task_query = select(KakaoTask)
    claim_query = select(KakaoEmailClaim).where(KakaoEmailClaim.state == KakaoClaimState.COMPLETED)
    if requested is not None:
        if not requested:
            return set()
        credential_query = credential_query.where(func.lower(Credential.email).in_(requested))
        task_query = task_query.where(func.lower(KakaoTask.email).in_(requested))
        claim_query = claim_query.where(func.lower(KakaoEmailClaim.email).in_(requested))

    completed = {claim.email.strip().lower() for claim in session.scalars(claim_query)}
    for credential in session.scalars(credential_query):
        metadata = credential.metadata_json if isinstance(credential.metadata_json, dict) else {}
        extraction = metadata.get(_EXTRACTION_METADATA_KEY)
        if isinstance(extraction, dict) and extraction.get("completed") is True:
            completed.add(credential.email.strip().lower())
    for task in session.scalars(task_query):
        if str(task.payment_url or "").strip() or canonical_payment_url(
            task.upstream_payload or {}
        ):
            completed.add(task.email.strip().lower())
    return completed


def active_extraction_emails(
    session: Session,
    emails: Iterable[str] | None = None,
) -> set[str]:
    requested = (
        {str(email).strip().lower() for email in emails if str(email).strip()}
        if emails is not None
        else None
    )
    query = select(KakaoEmailClaim.email).where(KakaoEmailClaim.state == KakaoClaimState.ACTIVE)
    if requested is not None:
        if not requested:
            return set()
        query = query.where(func.lower(KakaoEmailClaim.email).in_(requested))
    return {str(email).strip().lower() for email in session.scalars(query)}


@synchronized_kakao_state
def claim_extraction(
    session: Session,
    email: str,
    pipeline_run_id: str,
    pipeline_item_id: str,
) -> bool:
    normalized = email.strip().lower()
    existing = session.get(KakaoEmailClaim, normalized)
    if existing is not None:
        return (
            existing.state == KakaoClaimState.ACTIVE
            and existing.pipeline_item_id == pipeline_item_id
        )
    try:
        with session.begin_nested():
            session.add(
                KakaoEmailClaim(
                    email=normalized,
                    state=KakaoClaimState.ACTIVE,
                    pipeline_run_id=pipeline_run_id,
                    pipeline_item_id=pipeline_item_id,
                )
            )
            session.flush()
    except IntegrityError:
        return False
    return True


def require_extraction_claim(
    session: Session,
    email: str,
    pipeline_run_id: str,
    pipeline_item_id: str,
) -> None:
    if not claim_extraction(session, email, pipeline_run_id, pipeline_item_id):
        raise KakaoClaimConflictError(f"邮箱已有 Kakao 提取任务：{email}")


def release_extraction_claim(session: Session, task: KakaoTask) -> None:
    claim = session.get(KakaoEmailClaim, task.email.strip().lower())
    if (
        claim is not None
        and claim.state == KakaoClaimState.ACTIVE
        and (claim.pipeline_item_id is None or claim.pipeline_item_id == task.pipeline_item_id)
    ):
        session.delete(claim)


def mark_extraction_completed(session: Session, task: KakaoTask) -> bool:
    payment_url = str(task.payment_url or "").strip() or canonical_payment_url(
        task.upstream_payload or {}
    )
    if not payment_url:
        return False

    changed = task.payment_url != payment_url
    task.payment_url = payment_url
    normalized_email = task.email.strip().lower()
    claim = session.get(KakaoEmailClaim, normalized_email)
    if claim is None:
        claim = KakaoEmailClaim(
            email=normalized_email,
            pipeline_run_id=task.pipeline_run_id,
            pipeline_item_id=task.pipeline_item_id,
        )
        session.add(claim)
        changed = True
    if claim.state != KakaoClaimState.COMPLETED:
        claim.state = KakaoClaimState.COMPLETED
        changed = True
    credential = session.get(Credential, task.email.strip().lower())
    if credential is None:
        return changed

    metadata = credential.metadata_json if isinstance(credential.metadata_json, dict) else {}
    current = metadata.get(_EXTRACTION_METADATA_KEY)
    current = current if isinstance(current, dict) else {}
    extraction = {
        **current,
        "completed": True,
        "completed_at": str(current.get("completed_at") or utc_now().isoformat()),
        "task_id": str(task.id or task.upstream_job_id),
        "upstream_job_id": task.upstream_job_id,
        "payment_url": payment_url,
    }
    if current != extraction:
        credential.metadata_json = {**metadata, _EXTRACTION_METADATA_KEY: extraction}
        changed = True
    return changed


def apply_upstream(
    task: KakaoTask,
    value: dict[str, Any],
    session: Session | None = None,
) -> None:
    task_advanced = _advance_task_status(task, task_status(value.get("status")))
    normalized = normalized_payment_state(value)
    payment_status = str(normalized["status"] or value.get("payment_status") or "")
    payment_advanced = _advance_payment_status(task, payment_status)
    if payment_advanced:
        task.payment_message = str(normalized["message"] or "") or task.payment_message
        task.payment_expires_at = normalized["expires_at"] or task.payment_expires_at
        task.payment_scanned = bool(task.payment_scanned or normalized["scanned"])
        task.payment_successful = bool(task.payment_successful or normalized["successful"])
    charged = value.get("card_charged")
    if charged is True or (charged is False and task.card_charged is None):
        task.card_charged = charged
    task.payment_url = canonical_payment_url(value) or task.payment_url
    task.error = str(value.get("error") or "") or task.error
    if task_advanced or payment_advanced or not task.upstream_payload:
        task.upstream_payload = value
    if session is not None:
        mark_extraction_completed(session, task)
        if not task.payment_url and task.status in {
            KakaoTaskStatus.FAILED,
            KakaoTaskStatus.CANCELED,
        }:
            release_extraction_claim(session, task)


def apply_payment(
    task: KakaoTask,
    value: dict[str, Any],
    session: Session | None = None,
) -> None:
    normalized = normalized_payment_state(value)
    if _advance_payment_status(task, str(normalized["status"] or "")):
        task.payment_message = str(normalized["message"] or "") or task.payment_message
        task.payment_expires_at = normalized["expires_at"] or task.payment_expires_at
        task.payment_scanned = bool(task.payment_scanned or normalized["scanned"])
        task.payment_successful = bool(task.payment_successful or normalized["successful"])
        task.upstream_payload = {**(task.upstream_payload or {}), "kakao_status": value}
    task.payment_url = canonical_payment_url(value) or task.payment_url
    if session is not None:
        mark_extraction_completed(session, task)


def apply_retry(
    task: KakaoTask,
    value: dict[str, Any],
    session: Session | None = None,
) -> None:
    task.status = KakaoTaskStatus.QUEUED
    task.payment_status = None
    task.payment_message = None
    task.payment_expires_at = None
    task.payment_scanned = False
    task.payment_successful = False
    task.error = None
    apply_upstream(task, value, session)
