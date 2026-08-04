from collections.abc import Callable
from typing import Any

from gpt_auto_register.db.models.accounts import OutlookAccount
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.worker.runtime_service import call_legacy_runtime, emit_event


def classify_error(message: str) -> str:
    value = message.lower()
    account_patterns = (
        "wrong_email_otp_code",
        "invalid_grant",
        "imap xoauth2",
        "outlook otp timeout",
        "outlook imap account unusable",
        "user is authenticated but not connected",
        "outlook refresh failed",
        "authentication failed",
        "authenticate failed",
        "registration_disallowed",
        "邮件链接 otp timeout",
        "已有账号",
        "账号被",
        "refresh_token 失效",
    )
    network_patterns = (
        "tls",
        "ssl",
        "connection",
        "timeout",
        "proxy",
        "socks",
        "dns",
        "cloudflare",
        "403 forbidden",
        "connection reset",
        "connection aborted",
        "remote disconnected",
        "max retries exceeded",
        "csrf token 获取失败",
        "csrf token 失败",
        "/sentinel/req",
        "sentinel /req",
        "sentinel quickjs",
        "check_proxy 失败",
        "网络预检查",
        "curl: (35)",
        "curl: (28)",
        "curl: (6)",
        "curl: (7)",
        "http 429",
        "too many requests",
        "rate limit",
        "invalid_state",
    )
    if any(pattern in value for pattern in account_patterns):
        return "account"
    if any(pattern in value for pattern in network_patterns):
        return "network"
    return "unknown"


def emit(
    job_id: str,
    event_type: str,
    message: str,
    *,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    emit_event(
        SessionLocal,
        job_id,
        event_type,
        message,
        level=level,
        data=data,
    )


def legacy_call(
    payload: dict[str, Any],
    timeout: int = 1800,
    *,
    job_id: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return call_legacy_runtime(
        SessionLocal,
        payload,
        timeout,
        job_id=job_id,
        cancel_check=cancel_check,
    )


def account_payload(account: OutlookAccount) -> dict[str, Any]:
    return {
        "email": account.email,
        "password": account.password or "",
        "client_id": account.client_id or "",
        "refresh_token": account.refresh_token or "",
        "mail_type": account.mail_type.value,
        "mail_url": account.mail_url or "",
    }
