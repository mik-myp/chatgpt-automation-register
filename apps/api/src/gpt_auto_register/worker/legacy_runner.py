from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

RESULT_PREFIX = "__GPT_AUTO_RESULT__:"


def _load_runtime() -> Path:
    path = Path(os.environ["GPT_AUTO_LEGACY_RUNTIME_PATH"]).expanduser().resolve()
    if not (path / "auth_flow.py").is_file():
        raise RuntimeError(f"注册协议运行目录无效: {path}")
    sys.path.insert(0, str(path))
    return path


def _sms_callback(config: dict[str, Any]) -> object | None:
    if not config.get("enabled") or not config.get("api_key"):
        return None
    from sms_provider import PhoneCallbackController

    legacy = {
        "sms_api_key": config.get("api_key", ""),
        "sms_country": config.get("country", "52"),
        "sms_service": config.get("service", "dr"),
        "sms_max_price": config.get("max_price", ""),
        "sms_reuse_phone": config.get("reuse_phone", False),
        "sms_phone_success_max": config.get("phone_success_max", 3),
        "sms_strict_whitelist": config.get("strict_whitelist", False),
        "sms_allowed_countries": config.get("allowed_countries", ""),
        "sms_auto_min_stock": config.get("auto_min_stock", 20),
        "sms_auto_max_price": config.get("auto_max_price", ""),
        "sms_max_phone_attempts": config.get("max_phone_attempts", 3),
        "sms_per_phone_timeout": config.get("per_phone_timeout", 80),
    }
    return PhoneCallbackController(
        provider_key=str(config.get("provider") or "smsbower"),
        config=legacy,
        service=str(config.get("service") or "dr"),
        country=str(config.get("country") or "52"),
        auto_select_country=bool(config.get("auto_country")),
    )


def _register(payload: dict[str, Any]) -> dict[str, Any]:
    from account_security import security_outcome
    from auth_flow import AuthFlow
    from config import Config

    account = payload["account"]
    options = payload["registration"]
    mail_options = payload.get("mail", {})
    os.environ["WEBUI_ALLOW_LOGIN"] = "1" if options.get("allow_existing_login", True) else "0"
    os.environ["OTP_TIMEOUT"] = str(int(options.get("otp_timeout") or 180))
    config = Config(proxy=str(options.get("proxy") or "").strip() or None)
    mail_type = str(account.get("mail_type") or "outlook")
    if mail_options.get("source") == "cf_temp":
        from mail_cf import CFTempEmailProvider

        mail = CFTempEmailProvider(
            api_url=str(mail_options.get("cf_api_url") or ""),
            admin_token=str(mail_options.get("cf_admin_token") or ""),
            domain=str(mail_options.get("cf_domain") or ""),
        )
    elif mail_type == "link":
        from mail_link import LinkMailProvider

        mail = LinkMailProvider(
            email=account["email"],
            mail_url=account.get("mail_url", ""),
        )
    else:
        from mail_outlook import OutlookMailProvider

        mail = OutlookMailProvider(
            email=account["email"],
            password=account.get("password", ""),
            client_id=account.get("client_id", ""),
            refresh_token=account.get("refresh_token", ""),
        )

    sms = _sms_callback(payload.get("sms", {}))
    flow = AuthFlow(config, sms_callback=sms)
    password_mode = str(
        options.get("password_mode") or ("random" if options.get("set_password", True) else "none")
    )
    fixed_password = str(options.get("fixed_password") or "")
    if password_mode == "fixed" and not fixed_password:
        raise RuntimeError("固定密码模式需要先在系统设置中填写密码")
    partial = False
    try:
        result = flow.run_register(
            mail,
            password_mode=password_mode,
            password=fixed_password if password_mode == "fixed" else "",
        ).to_dict()
        security = security_outcome(flow, mail, options)
        result["security"] = {
            "password": security["password"],
            "mfa": security["mfa"],
        }
        if security["password"].get("status") == "set" and security["password_value"]:
            result["password"] = security["password_value"]
        result["totp_secret"] = security["totp_secret"]
    except RuntimeError:
        result = flow.result.to_dict()
        if not any(result.get(key) for key in ("access_token", "session_token", "refresh_token")):
            raise
        partial = True
        result["security"] = {
            "password": security_outcome(
                flow, mail, {**options, "enable_authenticator_mfa": False}
            )["password"],
            "mfa": {
                "requested": bool(options.get("enable_authenticator_mfa", False)),
                "status": "skipped_partial",
                "error": "注册流程仅获得部分凭证，未执行 MFA",
            },
        }
        result["totp_secret"] = ""
    finally:
        if sms is not None and hasattr(sms, "cleanup"):
            sms.cleanup()
    return {"ok": True, "credential": result, "partial": partial}


def _mail_test(payload: dict[str, Any]) -> dict[str, Any]:
    from mail_cf import CFTempEmailProvider

    config = payload["mail"]
    provider = CFTempEmailProvider(
        api_url=str(config.get("cf_api_url") or ""),
        admin_token=str(config.get("cf_admin_token") or ""),
        domain=str(config.get("cf_domain") or ""),
    )
    return {"ok": True, "email": provider.create_mailbox()}


def _sms_test(payload: dict[str, Any]) -> dict[str, Any]:
    from sms_provider import create_sms_provider

    config = payload["sms"]
    legacy = {
        "sms_api_key": config.get("api_key", ""),
        "sms_country": config.get("country", "52"),
        "sms_service": config.get("service", "dr"),
        "sms_max_price": config.get("max_price", ""),
        "sms_reuse_phone": config.get("reuse_phone", False),
        "sms_phone_success_max": config.get("phone_success_max", 3),
    }
    provider = create_sms_provider(str(config.get("provider") or "smsbower"), legacy)
    return {"ok": True, "balance": provider.get_balance()}


def _sms_countries(payload: dict[str, Any]) -> dict[str, Any]:
    from sms_provider import (
        OPENAI_SMS_COUNTRIES,
        SMS_COUNTRY_NAMES_CN,
        create_sms_provider,
    )

    config = payload["sms"]
    legacy = {
        "sms_api_key": config.get("api_key", ""),
        "sms_country": config.get("country", "52"),
        "sms_service": config.get("service", "dr"),
        "sms_max_price": config.get("max_price", ""),
    }
    rows: list[dict[str, Any]] = []
    if config.get("api_key"):
        provider = create_sms_provider(str(config.get("provider") or "smsbower"), legacy)
        try:
            rows = provider.get_top_countries(service=str(config.get("service") or "dr"))
        except NotImplementedError:
            rows = []
    by_id = {str(row.get("country") or ""): row for row in rows}
    ids = by_id.keys() if by_id else SMS_COUNTRY_NAMES_CN.keys()
    countries = [
        {
            "id": country_id,
            "name": SMS_COUNTRY_NAMES_CN.get(country_id, f"国家 {country_id}"),
            "safe": country_id in OPENAI_SMS_COUNTRIES,
            "price": by_id.get(country_id, {}).get("price"),
            "count": by_id.get(country_id, {}).get("count"),
        }
        for country_id in ids
    ]
    countries.sort(
        key=lambda value: (
            value["price"] is None,
            value["price"] if value["price"] is not None else 0,
            int(value["id"]) if str(value["id"]).isdigit() else 9999,
        )
    )
    return {"ok": True, "items": countries, "live": bool(rows)}


def _export(payload: dict[str, Any]) -> dict[str, Any]:
    from webui.exporter import run_exports

    config = payload["export"]
    cpa = config.get("cpa", {})
    sub2api = config.get("sub2api", {})
    return {
        "ok": True,
        "results": run_exports(
            payload["credential"],
            cpa_cfg=(
                {
                    "enabled": True,
                    "cpa_url": cpa.get("url", ""),
                    "cpa_mgmt_key": cpa.get("key", ""),
                    "cpa_timeout": cpa.get("timeout", 30),
                }
                if cpa.get("enabled")
                else None
            ),
            sub2api_cfg=(
                {
                    "enabled": True,
                    "sub2api_url": sub2api.get("url", ""),
                    "sub2api_api_key": sub2api.get("key", ""),
                    "sub2api_timeout": sub2api.get("timeout", 30),
                    "sub2api_group_ids": config.get("sub2api_group_ids", ""),
                }
                if sub2api.get("enabled")
                else None
            ),
        ),
    }


def _export_test(payload: dict[str, Any]) -> dict[str, Any]:
    from webui.exporter import test_cpa, test_sub2api

    target = str(payload.get("target") or "")
    config = payload["export"]
    value = config.get(target, {})
    if target == "cpa":
        result = test_cpa(
            {
                "cpa_url": value.get("url", ""),
                "cpa_mgmt_key": value.get("key", ""),
                "cpa_timeout": value.get("timeout", 30),
            }
        )
    elif target == "sub2api":
        result = test_sub2api(
            {
                "sub2api_url": value.get("url", ""),
                "sub2api_api_key": value.get("key", ""),
                "sub2api_timeout": value.get("timeout", 30),
            }
        )
    else:
        raise RuntimeError("不支持的导出目标")
    return {"ok": bool(result.get("ok")), "result": result, "error": result.get("error")}


def _verify_mfa(payload: dict[str, Any]) -> dict[str, Any]:
    from account_security import verify_authenticator_mfa
    from auth_flow import AuthFlow
    from config import Config

    credential = payload["credential"]
    flow = AuthFlow(Config(proxy=str(payload.get("proxy") or "").strip() or None))
    flow.result.device_id = str(credential.get("device_id") or "")
    for part in str(credential.get("cookie_header") or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name and value:
            flow.session.cookies.set(name, value, domain="chatgpt.com")
    if not verify_authenticator_mfa(flow):
        raise RuntimeError("服务端安全设置未确认 Authenticator App MFA 已启用")
    return {"ok": True, "verified": True}


def _security_context(payload: dict[str, Any]) -> tuple[Any, Any]:
    from auth_flow import AuthFlow
    from config import Config

    account = payload["account"]
    credential = payload["credential"]
    mail_options = payload.get("mail", {})
    options = payload.get("registration", {})
    flow = AuthFlow(Config(proxy=str(options.get("proxy") or "").strip() or None))
    flow.result.email = str(account.get("email") or "")
    flow.result.device_id = str(credential.get("device_id") or "")
    flow.result.password = str(credential.get("password") or "")
    flow.result.access_token = str(credential.get("access_token") or "")
    flow.result.session_token = str(credential.get("session_token") or "")
    for part in str(credential.get("cookie_header") or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name and value:
            flow.session.cookies.set(name, value, domain="chatgpt.com")
    if flow.result.session_token:
        flow.session.cookies.set(
            "__Secure-next-auth.session-token",
            flow.result.session_token,
            domain="chatgpt.com",
        )
    if mail_options.get("source") == "cf_temp":
        from mail_cf import CFTempEmailProvider

        mail = CFTempEmailProvider(
            api_url=str(mail_options.get("cf_api_url") or ""),
            admin_token=str(mail_options.get("cf_admin_token") or ""),
            domain=str(mail_options.get("cf_domain") or ""),
        )
    elif account.get("mail_type") == "link":
        from mail_link import LinkMailProvider

        mail = LinkMailProvider(
            email=flow.result.email,
            mail_url=str(account.get("mail_url") or ""),
        )
    else:
        from mail_outlook import OutlookMailProvider

        mail = OutlookMailProvider(
            email=flow.result.email,
            password=str(account.get("password") or ""),
            client_id=str(account.get("client_id") or ""),
            refresh_token=str(account.get("refresh_token") or ""),
        )
    return flow, mail


def _flow_session_credential(flow: Any) -> dict[str, str]:
    builder = getattr(flow, "_build_chatgpt_cookie_header", None)
    cookie_header = str(builder() if callable(builder) else flow.result.cookie_header or "")
    return {
        "access_token": str(flow.result.access_token or ""),
        "session_token": str(flow.result.session_token or ""),
        "device_id": str(flow.result.device_id or ""),
        "cookie_header": cookie_header,
    }


def _refresh_authorization(payload: dict[str, Any]) -> dict[str, Any]:
    credential = payload["credential"]
    mode = str(payload.get("mode") or "session")
    flow, mail_provider = _security_context(payload)
    if mode == "session":
        session_token = str(credential.get("session_token") or "")
        if not session_token:
            cookie_value = getattr(flow, "_get_cookie_value_by_name", None)
            if callable(cookie_value):
                session_token = str(cookie_value("__Secure-next-auth.session-token") or "")
        result = flow.from_existing_credentials(
            session_token,
            str(credential.get("access_token") or ""),
            str(credential.get("device_id") or ""),
        )
    elif mode == "login":
        result = flow.run_protocol_login(
            mail_provider,
            str(payload.get("account", {}).get("email") or ""),
            str(credential.get("password") or ""),
        )
    else:
        raise RuntimeError(f"不支持的授权恢复模式: {mode}")
    value = result.to_dict()
    if not value.get("access_token"):
        raise RuntimeError("授权恢复后仍未获得 Access Token")
    return {"ok": True, "credential": value, "mode": mode}


def _enable_mfa(payload: dict[str, Any]) -> dict[str, Any]:
    from account_security import enable_authenticator_mfa

    options = payload.get("registration", {})
    flow, mail_provider = _security_context(payload)
    try:
        secret = enable_authenticator_mfa(
            flow,
            mail_provider,
            email=flow.result.email,
            otp_timeout=int(options.get("mfa_otp_timeout") or 180),
        )
    except Exception as error:
        return {"ok": False, "error": str(error), "credential": _flow_session_credential(flow)}
    return {
        "ok": True,
        "credential": {
            **_flow_session_credential(flow),
            "totp_secret": secret,
            "security": {"mfa": {"requested": True, "status": "enabled", "error": ""}},
        },
    }


def _set_password(payload: dict[str, Any]) -> dict[str, Any]:
    from account_security import set_account_password

    account = payload["account"]
    options = payload.get("registration", {})
    flow, mail_provider = _security_context(payload)
    mode = str(options.get("password_mode") or "random")
    password = str(options.get("fixed_password") or "")
    if mode == "random":
        password = flow._random_password(20)
    if not password:
        raise RuntimeError("系统设置中没有可用的 ChatGPT 密码")
    try:
        set_account_password(
            flow,
            mail_provider,
            email=str(account.get("email") or ""),
            password=password,
            otp_timeout=int(options.get("mfa_otp_timeout") or 180),
        )
    except Exception as error:
        return {"ok": False, "error": str(error), "credential": _flow_session_credential(flow)}
    return {
        "ok": True,
        "credential": {
            **_flow_session_credential(flow),
            "password": password,
            "security": {"password": {"requested": True, "status": "set", "error": ""}},
        },
    }


def main() -> None:
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
            force=True,
        )
        _load_runtime()
        payload = json.loads(sys.stdin.read())
        action = payload.get("action", "register")
        if action == "register":
            result = _register(payload)
        elif action == "sms_test":
            result = _sms_test(payload)
        elif action == "sms_countries":
            result = _sms_countries(payload)
        elif action == "mail_test":
            result = _mail_test(payload)
        elif action == "export":
            result = _export(payload)
        elif action == "export_test":
            result = _export_test(payload)
        elif action == "verify_mfa":
            result = _verify_mfa(payload)
        elif action == "enable_mfa":
            result = _enable_mfa(payload)
        elif action == "set_password":
            result = _set_password(payload)
        elif action == "refresh_authorization":
            result = _refresh_authorization(payload)
        else:
            raise RuntimeError(f"不支持的旧运行时操作: {action}")
    except Exception as error:
        trace = traceback.format_exc()
        print(trace, file=sys.stderr, end="")
        result = {"ok": False, "error": str(error), "traceback": trace}
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
