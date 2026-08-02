"""Registration-time account security steps.

This module intentionally returns structured outcomes and never logs passwords,
email OTPs, TOTP secrets, access tokens, or generated TOTP codes.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import pyotp

logger = logging.getLogger(__name__)


def password_outcome(flow: Any, requested: bool) -> dict[str, Any]:
    status = str(getattr(flow, "password_registration_status", "not_attempted"))
    has_password = bool(getattr(flow.result, "password", ""))
    if status == "set":
        return {"requested": requested, "status": "set", "error": ""}
    if requested and status == "unsupported":
        return {
            "requested": True,
            "status": "unsupported",
            "error": "OpenAI 本次选择了 passwordless_signup，无法在注册链路中设置密码",
        }
    if requested and status == "failed":
        return {
            "requested": True,
            "status": "failed",
            "error": "OpenAI 注册密码接口未确认成功",
        }
    if requested and has_password:
        return {"requested": True, "status": "available", "error": ""}
    if requested:
        return {
            "requested": True,
            "status": "unsupported",
            "error": "当前登录或注册分支没有可用的密码设置步骤",
        }
    return {"requested": requested, "status": "not_requested", "error": ""}


def _json(response: Any, step: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(f"{step}失败: HTTP {response.status_code}")
    try:
        value = response.json()
    except Exception as error:
        raise RuntimeError(f"{step}失败: 响应不是有效 JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{step}失败: 响应格式错误")
    return value


def enable_authenticator_mfa(
    flow: Any,
    mail_provider: Any,
    *,
    email: str,
    otp_timeout: int,
) -> str:
    """Reauthenticate and activate a TOTP factor, returning its Base32 secret."""
    logger.info("开始启用 Authenticator App MFA")
    issued_after = time.time()
    csrf_token = flow.get_csrf_token()
    query = urlencode(
        {
            "connection": "password",
            "login_hint": email,
            "reauth": "password",
            "max_age": "0",
            "ext-oai-did": flow.result.device_id,
        }
    )
    signin_url = f"https://chatgpt.com/api/auth/signin/openai?{query}"
    headers = flow._common_headers("https://chatgpt.com/")
    headers.update(
        {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://chatgpt.com",
        }
    )
    signin = flow.session.post(
        signin_url,
        headers=headers,
        data={
            "callbackUrl": "https://chatgpt.com/?action=enable&factor=totp",
            "csrfToken": csrf_token,
            "json": "true",
        },
        timeout=30,
    )
    auth_url = str(_json(signin, "发起 MFA 重认证").get("url") or "")
    if not auth_url:
        raise RuntimeError("发起 MFA 重认证失败: 响应缺少授权地址")

    trigger = flow.session.get(
        auth_url,
        headers=flow._common_headers("https://chatgpt.com/"),
        timeout=30,
        allow_redirects=True,
    )
    if trigger.status_code >= 400:
        raise RuntimeError(f"触发 MFA 邮箱验证失败: HTTP {trigger.status_code}")
    otp_headers = flow._common_headers("https://auth.openai.com/email-verification")
    otp_headers["Content-Type"] = "application/json"
    continue_url = ""
    for attempt in range(2):
        otp_code = mail_provider.wait_for_otp(
            email,
            timeout=max(10, int(otp_timeout)),
            issued_after=issued_after,
        )
        validated = flow.session.post(
            "https://auth.openai.com/api/accounts/email-otp/validate",
            headers=otp_headers,
            json={"code": otp_code},
            timeout=30,
        )
        if validated.status_code == 200:
            continue_url = str(
                _json(validated, "验证 MFA 邮箱验证码").get("continue_url") or ""
            )
            if continue_url:
                break
        if attempt == 0:
            logger.warning("MFA 邮箱验证码首次验证失败，重新发送后重试")
            issued_after = time.time()
            if not flow.kickoff_otp_delivery("mfa_reauth_retry"):
                flow.send_otp("https://auth.openai.com/email-verification")
    if not continue_url:
        raise RuntimeError("验证 MFA 邮箱验证码失败: 响应缺少继续地址")
    callback = flow.session.get(
        continue_url,
        headers=flow._common_headers("https://auth.openai.com/email-verification"),
        timeout=30,
        allow_redirects=True,
    )
    if callback.status_code >= 400:
        raise RuntimeError(f"刷新 MFA 重认证会话失败: HTTP {callback.status_code}")
    _, access_token = flow.get_auth_session()
    if not access_token:
        raise RuntimeError("刷新 MFA 重认证会话失败: 缺少 Access Token")

    api_headers = flow._common_headers("https://chatgpt.com/")
    api_headers.update(
        {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "oai-device-id": flow.result.device_id,
            "oai-language": "zh-CN",
        }
    )
    enrollment = flow.session.post(
        "https://chatgpt.com/backend-api/accounts/mfa/enroll",
        headers=api_headers,
        json={"factor_type": "totp"},
        timeout=30,
    )
    enrollment_data = _json(enrollment, "创建 Authenticator App MFA")
    secret = str(enrollment_data.get("secret") or "")
    session_id = str(enrollment_data.get("session_id") or "")
    if not secret or not session_id:
        raise RuntimeError("创建 Authenticator App MFA 失败: 响应字段不完整")

    activation = flow.session.post(
        "https://chatgpt.com/backend-api/accounts/mfa/user/activate_enrollment",
        headers=api_headers,
        json={
            "code": pyotp.TOTP(secret).now(),
            "factor_type": "totp",
            "session_id": session_id,
        },
        timeout=30,
    )
    activation_data = _json(activation, "激活 Authenticator App MFA")
    if activation_data.get("success") is not True:
        raise RuntimeError("激活 Authenticator App MFA 失败: 服务端未确认成功")
    confirmed = flow.session.get(
        "https://chatgpt.com/api/auth/session",
        headers=flow._common_headers("https://chatgpt.com/"),
        timeout=30,
    )
    session_data = _json(confirmed, "确认 Authenticator App MFA 状态")
    user = session_data.get("user") if isinstance(session_data.get("user"), dict) else {}
    if user.get("mfa") is not True:
        raise RuntimeError("Authenticator App MFA 激活后，服务端会话未确认启用")
    logger.info("Authenticator App MFA 已启用并由服务端确认")
    return secret


def security_outcome(
    flow: Any,
    mail_provider: Any,
    options: dict[str, Any],
) -> dict[str, Any]:
    mode = str(options.get("password_mode") or ("random" if options.get("set_password", True) else "none"))
    password = password_outcome(flow, mode != "none")
    mfa_requested = bool(options.get("enable_authenticator_mfa", False))
    mfa: dict[str, Any] = {
        "requested": mfa_requested,
        "status": "not_requested",
        "error": "",
    }
    secret = ""
    if mfa_requested:
        try:
            secret = enable_authenticator_mfa(
                flow,
                mail_provider,
                email=flow.result.email,
                otp_timeout=int(options.get("mfa_otp_timeout") or 180),
            )
            mfa["status"] = "enabled"
        except Exception as error:
            mfa.update(status="failed", error=str(error))
            logger.warning("Authenticator App MFA 启用失败: %s", error)
    return {"password": password, "mfa": mfa, "totp_secret": secret}
