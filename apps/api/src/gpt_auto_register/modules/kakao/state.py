import threading
from collections.abc import Callable
from functools import wraps
from typing import Any

from gpt_auto_register.db.models.kakao import KakaoTask, KakaoTaskStatus
from gpt_auto_register.modules.kakao.client import (
    canonical_payment_url,
    normalized_payment_state,
)

_KAKAO_STATE_LOCK = threading.RLock()


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


def apply_upstream(task: KakaoTask, value: dict[str, Any]) -> None:
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


def apply_payment(task: KakaoTask, value: dict[str, Any]) -> None:
    normalized = normalized_payment_state(value)
    if not _advance_payment_status(task, str(normalized["status"] or "")):
        return
    task.payment_message = str(normalized["message"] or "") or task.payment_message
    task.payment_expires_at = normalized["expires_at"] or task.payment_expires_at
    task.payment_scanned = bool(task.payment_scanned or normalized["scanned"])
    task.payment_successful = bool(task.payment_successful or normalized["successful"])
    task.upstream_payload = {**(task.upstream_payload or {}), "kakao_status": value}


def apply_retry(task: KakaoTask, value: dict[str, Any]) -> None:
    task.status = KakaoTaskStatus.QUEUED
    task.payment_status = None
    task.payment_message = None
    task.payment_expires_at = None
    task.payment_scanned = False
    task.payment_successful = False
    task.error = None
    apply_upstream(task, value)
