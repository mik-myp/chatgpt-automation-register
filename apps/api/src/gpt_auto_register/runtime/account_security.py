"""Registration-time account security steps.

This module intentionally returns structured outcomes and never logs passwords,
email OTPs, TOTP secrets, access tokens, or generated TOTP codes.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode, urlparse

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


def _backend_headers(flow: Any, access_token: str) -> dict[str, str]:
    headers = {
        str(key): str(value)
        for key, value in flow._common_headers("https://chatgpt.com/").items()
    }
    headers.update(
        {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "oai-device-id": flow.result.device_id,
            "oai-language": "zh-CN",
        }
    )
    return headers


def _session_cookie(flow: Any) -> str:
    container = getattr(flow.session, "cookies", None)
    jar = getattr(container, "jar", None)
    try:
        cookies = list(jar if jar is not None else container or [])
    except Exception:
        cookies = []
    for cookie in reversed(cookies):
        if getattr(cookie, "name", "") == "__Secure-next-auth.session-token":
            value = str(getattr(cookie, "value", "") or "")
            if value:
                return value
    extractor = getattr(flow, "_extract_session_cookie", None)
    return str(extractor() if callable(extractor) else "")


def _prefer_fresh_session_cookie(flow: Any, previous: str) -> str:
    """Collapse duplicate NextAuth cookies, preferring a value issued by reauthentication."""
    name = "__Secure-next-auth.session-token"
    cookies = []
    try:
        container = flow.session.cookies
        jar = getattr(container, "jar", None)
        source = jar if jar is not None else container
        cookies = [cookie for cookie in source if getattr(cookie, "name", "") == name]
    except Exception:
        return _session_cookie(flow)
    values = [str(getattr(cookie, "value", "") or "") for cookie in cookies]
    fresh = next((value for value in reversed(values) if value and value != previous), "")
    selected = fresh or next((value for value in reversed(values) if value), "")
    if not selected:
        return ""
    for cookie in cookies:
        try:
            flow.session.cookies.delete(
                name,
                domain=str(getattr(cookie, "domain", "") or ""),
                path=str(getattr(cookie, "path", "") or "/"),
            )
        except Exception:
            continue
    flow.session.cookies.set(name, selected, domain=".chatgpt.com", path="/", secure=True)
    flow.result.session_token = selected
    builder = getattr(flow, "_build_chatgpt_cookie_header", None)
    if callable(builder):
        flow.result.cookie_header = builder()
    return selected


def _mfa_enabled(flow: Any, access_token: str) -> bool:
    response = flow.session.get(
        "https://chatgpt.com/backend-api/accounts/mfa_info",
        headers=_backend_headers(flow, access_token),
        timeout=30,
    )
    data = _json(response, "确认 Authenticator App MFA 状态")
    factors = data.get("factors") if isinstance(data.get("factors"), dict) else {}
    totp = factors.get("totp") if isinstance(factors, dict) else []
    return data.get("mfa_enabled") is True and isinstance(totp, list) and bool(totp)


def verify_authenticator_mfa(flow: Any) -> bool:
    _, access_token = flow.get_auth_session()
    if not access_token:
        raise RuntimeError("验证 MFA 状态失败: 缺少 Access Token")
    return _mfa_enabled(flow, access_token)


def _reauthenticate(
    flow: Any,
    mail_provider: Any,
    *,
    email: str,
    otp_timeout: int,
    callback_url: str,
    screen_hint: str = "",
    post_login_add_password: bool = False,
    force_login: bool = False,
    password: str = "",
) -> str:
    """Complete OpenAI reauthentication and return the final landing URL."""
    flow._account_security_used_password = False
    issued_after = time.time()
    previous_session_token = _session_cookie(flow)
    csrf_token = flow.get_csrf_token()
    query_data = {
        "connection": "password",
        "login_hint": email,
        "reauth": "password",
        "max_age": "0",
        "ext-oai-did": flow.result.device_id,
    }
    if screen_hint:
        query_data["screen_hint"] = screen_hint
    if post_login_add_password:
        query_data["post_login_add_password"] = "true"
    if force_login:
        query_data["prompt"] = "login"
    signin_url = f"https://chatgpt.com/api/auth/signin/openai?{urlencode(query_data)}"
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
        data={"callbackUrl": callback_url, "csrfToken": csrf_token, "json": "true"},
        timeout=30,
    )
    auth_url = str(_json(signin, "发起账号重认证").get("url") or "")
    if not auth_url:
        raise RuntimeError("发起账号重认证失败: 响应缺少授权地址")

    trigger = flow.session.get(
        auth_url,
        headers=flow._common_headers("https://chatgpt.com/"),
        timeout=30,
        allow_redirects=True,
    )
    if trigger.status_code >= 400:
        raise RuntimeError(f"触发账号重认证失败: HTTP {trigger.status_code}")
    _prefer_fresh_session_cookie(flow, previous_session_token)
    landing_url = str(getattr(trigger, "url", "") or "")
    logger.info("账号重认证落点: %s", urlparse(landing_url).path or "/")
    if urlparse(landing_url).path == "/api/accounts/authorize":
        sentinel_token = flow.get_sentinel_token(flow.result.device_id)
        step = flow.authorize_continue(
            email=email,
            sentinel_token=sentinel_token,
            screen_hint="login",
            referer=landing_url,
            trace_step="account_security_authorize_continue",
        )
        page_type = str(flow._extract_page_type(step) or "")
        continue_extractor = getattr(flow, "_extract_continue_url_from_step", None)
        landing_url = str(
            continue_extractor(step)
            if callable(continue_extractor)
            else step.get("continue_url") or ""
        )
        if page_type == "email_otp_verification" and not landing_url:
            landing_url = "https://auth.openai.com/email-verification"
        if not landing_url:
            raise RuntimeError(f"账号重认证中间态无法继续: {page_type or '未知页面'}")
        logger.info("账号重认证继续页面: %s", urlparse(landing_url).path or "/")
    trigger_body = str(getattr(trigger, "text", "") or "")
    if "reset_password_start" in trigger_body:
        send_headers = flow._common_headers(landing_url or "https://auth.openai.com/reset-password")
        send_headers["Content-Type"] = "application/json"
        sent = flow.session.post(
            "https://auth.openai.com/api/accounts/password/send-otp",
            headers=send_headers,
            timeout=30,
        )
        if sent.status_code != 200:
            body = str(getattr(sent, "text", "") or "")[:300]
            raise RuntimeError(f"发送密码设置验证码失败: HTTP {sent.status_code} - {body}")
        landing_url = "https://auth.openai.com/email-verification"
    continue_url = ""
    if "/log-in/password" in landing_url:
        if not password:
            raise RuntimeError("账号重认证需要当前 ChatGPT 密码")
        flow.get_sentinel_token(flow.result.device_id)
        step = flow.login_password_verify(password)
        flow._account_security_used_password = True
        extractor = getattr(flow, "_extract_continue_url_from_step", None)
        continue_url = str(
            extractor(step) if callable(extractor) else step.get("continue_url") or ""
        )
    elif "/email-verification" in landing_url or not landing_url:
        otp_headers = flow._common_headers("https://auth.openai.com/email-verification")
        otp_headers["Content-Type"] = "application/json"
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
                continue_url = str(_json(validated, "验证账号邮箱验证码").get("continue_url") or "")
                if continue_url:
                    break
            if attempt == 0:
                logger.warning("账号邮箱验证码首次验证失败，重新发送后重试")
                issued_after = time.time()
                if not flow.kickoff_otp_delivery("account_security_reauth_retry"):
                    flow.send_otp("https://auth.openai.com/email-verification")
    else:
        continue_url = landing_url
    if not continue_url:
        raise RuntimeError("账号重认证失败: 响应缺少继续地址")
    callback = flow.session.get(
        continue_url,
        headers=flow._common_headers("https://auth.openai.com/email-verification"),
        timeout=30,
        allow_redirects=True,
    )
    if callback.status_code >= 400:
        raise RuntimeError(f"刷新账号重认证会话失败: HTTP {callback.status_code}")
    _prefer_fresh_session_cookie(flow, previous_session_token)
    final_url = str(getattr(callback, "url", "") or continue_url)
    logger.info("账号重认证回调落点: %s", urlparse(final_url).path or "/")
    return final_url


def _password_eligibility(flow: Any, access_token: str, action: str) -> bool:
    response = flow.session.get(
        f"https://chatgpt.com/backend-api/accounts/{action}_password/eligibility",
        headers=_backend_headers(flow, access_token),
        timeout=30,
    )
    return _json(response, "检查密码设置资格").get("eligible") is True


def set_account_password(
    flow: Any,
    mail_provider: Any,
    *,
    email: str,
    password: str,
    otp_timeout: int,
) -> str:
    """Add or change the account password through OpenAI's reset flow."""
    if len(password) < 12:
        raise RuntimeError("ChatGPT 密码至少需要 12 个字符")
    operation = ""
    initial_access_token = ""
    try:
        _, initial_access_token = flow.get_auth_session()
        if initial_access_token:
            if _password_eligibility(flow, initial_access_token, "add"):
                operation = "add"
            elif _password_eligibility(flow, initial_access_token, "change"):
                operation = "reset"
    except RuntimeError as error:
        if "HTTP 401" not in str(error):
            raise
        logger.info("密码操作前的账号会话已失效，将通过重认证确定操作类型")
    current_password = str(getattr(flow.result, "password", "") or password)
    landing_url = _reauthenticate(
        flow,
        mail_provider,
        email=email,
        otp_timeout=otp_timeout,
        callback_url="https://chatgpt.com/#settings/Security",
        screen_hint="login",
        post_login_add_password=True,
        password=current_password,
    )
    if "/reset-password/new-password" not in landing_url:
        raise RuntimeError(f"密码重认证未进入设置页面: {landing_url or '未知地址'}")
    if getattr(flow, "_account_security_used_password", False) and current_password == password:
        flow.result.password = password
        logger.info("账号已接受配置的 ChatGPT 密码，无需重复重置")
        return password
    if not operation and getattr(flow, "_account_security_used_password", False):
        operation = "reset"
    if not operation:
        _, refreshed_access_token = flow.get_auth_session()
        if not refreshed_access_token:
            raise RuntimeError("设置密码失败: 缺少 Access Token")
        if _password_eligibility(flow, refreshed_access_token, "add"):
            operation = "add"
        elif _password_eligibility(flow, refreshed_access_token, "change"):
            operation = "reset"
    if not operation:
        raise RuntimeError("当前账号不允许添加或修改密码")

    try:
        from sentinel import get_sentinel_token
    except ImportError:
        from gpt_auto_register.runtime.sentinel import get_sentinel_token

    sentinel_token, sentinel_so_token = get_sentinel_token(
        flow.session,
        device_id=flow.result.device_id,
        flow="password_reset",
        require_so_token=False,
        **flow._sentinel_fp_kwargs(),
    )
    headers = flow._common_headers("https://auth.openai.com/reset-password/new-password")
    headers["Content-Type"] = "application/json"
    headers["openai-sentinel-token"] = sentinel_token
    if sentinel_so_token:
        headers["openai-sentinel-so-token"] = sentinel_so_token
    response = flow.session.post(
        f"https://auth.openai.com/api/accounts/password/{operation}",
        headers=headers,
        json={"password": password},
        timeout=30,
    )
    _json(response, "设置 ChatGPT 密码")
    if operation == "add":
        try:
            _, refreshed_access_token = flow.get_auth_session()
            if not refreshed_access_token:
                refreshed_access_token = initial_access_token
            if _password_eligibility(flow, refreshed_access_token, "add"):
                raise RuntimeError("设置密码后，服务端仍显示可以添加密码")
        except RuntimeError as error:
            if "HTTP 401" not in str(error):
                raise
            logger.info("密码设置后当前会话已失效，需要在后续操作中重新认证")
    flow.result.password = password
    logger.info("ChatGPT 密码已设置并由服务端确认")
    return password


def enable_authenticator_mfa(
    flow: Any,
    mail_provider: Any,
    *,
    email: str,
    otp_timeout: int,
) -> str:
    """Reauthenticate and activate a TOTP factor, returning its Base32 secret."""
    logger.info("开始启用 Authenticator App MFA")
    _reauthenticate(
        flow,
        mail_provider,
        email=email,
        otp_timeout=otp_timeout,
        callback_url="https://chatgpt.com/?action=enable&factor=totp",
        screen_hint="login",
        force_login=True,
        password=str(getattr(flow.result, "password", "") or ""),
    )
    _, access_token = flow.get_auth_session()
    if not access_token:
        raise RuntimeError("刷新 MFA 重认证会话失败: 缺少 Access Token")

    api_headers = _backend_headers(flow, access_token)
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
    if not _mfa_enabled(flow, access_token):
        raise RuntimeError("Authenticator App MFA 激活后，安全设置接口未确认启用")
    logger.info("Authenticator App MFA 已启用并由服务端确认")
    return secret


def security_outcome(
    flow: Any,
    mail_provider: Any,
    options: dict[str, Any],
) -> dict[str, Any]:
    mode = str(
        options.get("password_mode") or ("random" if options.get("set_password", True) else "none")
    )
    password = password_outcome(flow, mode != "none")
    if mode != "none" and password["status"] != "set":
        desired_password = str(options.get("fixed_password") or "")
        if mode == "random":
            desired_password = str(getattr(flow.result, "password", "") or "")
            if not desired_password:
                desired_password = flow._random_password(20)
        try:
            set_account_password(
                flow,
                mail_provider,
                email=flow.result.email,
                password=desired_password,
                otp_timeout=int(options.get("mfa_otp_timeout") or 180),
            )
            password = {"requested": True, "status": "set", "error": ""}
        except Exception as error:
            password = {"requested": True, "status": "failed", "error": str(error)}
            logger.warning("ChatGPT 密码设置失败: %s", error)
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
