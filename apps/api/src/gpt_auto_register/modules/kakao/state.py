from typing import Any

from gpt_auto_register.db.models.kakao import KakaoTask, KakaoTaskStatus
from gpt_auto_register.modules.kakao.client import (
    canonical_payment_url,
    normalized_payment_state,
)


def task_status(value: object) -> KakaoTaskStatus:
    try:
        return KakaoTaskStatus(str(value or "queued").lower())
    except ValueError:
        return KakaoTaskStatus.QUEUED


def apply_upstream(task: KakaoTask, value: dict[str, Any]) -> None:
    task.status = task_status(value.get("status"))
    normalized = normalized_payment_state(value)
    payment_status = str(normalized["status"] or value.get("payment_status") or "")
    if payment_status:
        task.payment_status = payment_status
        task.payment_message = str(normalized["message"] or "") or task.payment_message
        task.payment_expires_at = normalized["expires_at"] or task.payment_expires_at
        task.payment_scanned = bool(normalized["scanned"])
        task.payment_successful = bool(normalized["successful"])
    charged = value.get("card_charged")
    if isinstance(charged, bool):
        task.card_charged = charged
    task.payment_url = canonical_payment_url(value) or task.payment_url
    task.error = str(value.get("error") or "") or task.error
    task.upstream_payload = value


def apply_payment(task: KakaoTask, value: dict[str, Any]) -> None:
    normalized = normalized_payment_state(value)
    task.payment_status = str(normalized["status"] or "") or task.payment_status
    task.payment_message = str(normalized["message"] or "") or task.payment_message
    task.payment_expires_at = normalized["expires_at"] or task.payment_expires_at
    task.payment_scanned = bool(normalized["scanned"])
    task.payment_successful = bool(normalized["successful"])
    task.upstream_payload = {**(task.upstream_payload or {}), "kakao_status": value}
