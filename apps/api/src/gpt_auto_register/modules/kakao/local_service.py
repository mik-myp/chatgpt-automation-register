from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Any
from urllib.parse import urlsplit

from gpt_auto_register.modules.kakao import extractor


class KakaoExtractionError(RuntimeError):
    def __init__(self, message: str, *, category: str, retryable: bool) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@dataclass(frozen=True)
class KakaoExtractionResult:
    payment_url: str
    checkout_session_id: str
    payment_method_id: str
    stripe_redirect_url: str

    def as_payload(self) -> dict[str, str]:
        return {
            "payment_url": self.payment_url,
            "checkout_session_id": self.checkout_session_id,
            "payment_method_id": self.payment_method_id,
            "stripe_redirect_url": self.stripe_redirect_url,
        }


def workflow_config(
    email: str,
    *,
    request_timeout: int,
    poll_timeout: int,
    promo_id: str,
) -> dict[str, Any]:
    request_timeout = max(5, min(120, request_timeout))
    poll_timeout = max(30, min(300, poll_timeout))
    steps: dict[str, dict[str, Any]] = {}
    definitions = (
        ("token_check", "KR", "kr", request_timeout, 3),
        ("checkout_create", "KR", "kr", request_timeout, 1),
        ("stripe_bootstrap", "KR", "kr", request_timeout, 1),
        ("promotion_update", "VN", "vn", request_timeout, 1),
        ("provider_refresh", "KR", "kr", request_timeout, 1),
        ("taxes", "KR", "kr", request_timeout, 1),
        ("payment_confirm", "KR", "kr", request_timeout, 1),
        ("approve", "KR", "kr", request_timeout, 2),
        ("redirect_poll", "KR", "kr", poll_timeout, 1),
    )
    for order, (name, country, role, timeout, attempts) in enumerate(definitions, start=1):
        steps[name] = {
            "order": order,
            "country": country,
            "proxy_role": role,
            "http_backend": "requests",
            "timeout": timeout,
            "attempts": attempts,
        }
    return {
        "billing": {"email": email, "apartment_probability": 0.65},
        "promo_mode": "campaign" if promo_id else "off",
        "promo_id": promo_id,
        "steps": steps,
    }


def classify_extraction_error(error: Exception) -> KakaoExtractionError:
    message = str(error) or error.__class__.__name__
    if isinstance(error, extractor.TaskStopped):
        return KakaoExtractionError(message, category="canceled", retryable=False)
    if extractor.is_account_error(message):
        return KakaoExtractionError(message, category="account", retryable=False)
    if extractor.is_checkout_shape_error(message):
        return KakaoExtractionError(message, category="checkout", retryable=True)
    if extractor.is_proxy_health_error(message) or extractor.is_direct_proxy_error(message):
        return KakaoExtractionError(message, category="proxy", retryable=True)
    return KakaoExtractionError(message, category="upstream", retryable=True)


def extract_payment_link(
    *,
    access_token: str,
    email: str,
    kr_proxy: str,
    vn_proxy: str,
    request_timeout: int,
    poll_timeout: int,
    promo_id: str,
    stop_event: Event | None = None,
    log: Callable[[str, str], None] | None = None,
    verify_proxy_countries: bool = True,
) -> KakaoExtractionResult:
    if not access_token.strip():
        raise KakaoExtractionError("缺少 Access Token", category="prerequisite", retryable=False)
    if "@" not in email:
        raise KakaoExtractionError("缺少有效账号邮箱", category="prerequisite", retryable=False)
    if not kr_proxy or not vn_proxy:
        raise KakaoExtractionError(
            "Kakao 需要完整的 KR/VN 代理对", category="proxy", retryable=True
        )
    if kr_proxy == vn_proxy:
        raise KakaoExtractionError("KR 与 VN 代理不得相同", category="proxy", retryable=True)

    callback = log or (lambda _message, _level: None)
    try:
        with extractor.event_logger(callback):
            if verify_proxy_countries:
                kr_ok, kr_detail = extractor.preflight_proxy(kr_proxy, "checkout")
                callback(f"[代理预检][KR] {kr_detail}", "info" if kr_ok else "warning")
                if not kr_ok:
                    raise RuntimeError(f"KR 代理出口预检失败: {kr_detail}")
                vn_ok, vn_detail = extractor.preflight_proxy(vn_proxy, "promotion")
                callback(f"[代理预检][VN] {vn_detail}", "info" if vn_ok else "warning")
                if not vn_ok:
                    raise RuntimeError(f"VN 代理出口预检失败: {vn_detail}")
            payload = extractor.kakao_link(
                access_token,
                kr_proxy,
                vn_proxy,
                kr_proxy,
                stop_event=stop_event,
                workflow_config=workflow_config(
                    email,
                    request_timeout=request_timeout,
                    poll_timeout=poll_timeout,
                    promo_id=promo_id,
                ),
            )
    except Exception as error:
        raise classify_extraction_error(error) from error

    payment_url = str(payload.get("provider_redirect_url") or "")
    host = urlsplit(payment_url).hostname or ""
    if "nicepay" not in host.lower() and "kakao" not in host.lower():
        raise KakaoExtractionError(
            f"最终跳转不是 Kakao/Nicepay: {payment_url[:180]}",
            category="response",
            retryable=True,
        )
    return KakaoExtractionResult(
        payment_url=payment_url,
        checkout_session_id=str(payload.get("checkout_session_id") or ""),
        payment_method_id=str(payload.get("payment_method_id") or ""),
        stripe_redirect_url=str(payload.get("stripe_redirect_url") or ""),
    )
