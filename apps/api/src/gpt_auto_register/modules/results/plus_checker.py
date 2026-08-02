import base64
import json
from datetime import UTC, datetime
from typing import Any


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _token_account_id(access_token: str) -> str:
    try:
        payload_part = access_token.split(".")[1]
        padding = "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part + padding))
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return ""
    auth = _mapping(payload.get("https://api.openai.com/auth"))
    return str(auth.get("chatgpt_account_id") or payload.get("chatgpt_account_id") or "")


def _subscription_name(entitlement: dict[str, Any]) -> str:
    value = entitlement.get("subscription_plan")
    if isinstance(value, dict):
        value = value.get("id") or value.get("name") or value.get("title")
    return str(value or "").strip().lower()


def _expired(value: object) -> bool | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            expires_at = datetime.fromtimestamp(value, UTC)
        else:
            expires_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= datetime.now(UTC)
    except (ValueError, TypeError, OSError):
        return None


def _select_account(
    accounts: dict[str, Any],
    token_account_id: str,
) -> tuple[str, dict[str, Any], str]:
    candidates = [
        (str(key), _mapping(value)) for key, value in accounts.items() if isinstance(value, dict)
    ]
    if token_account_id:
        for key, value in candidates:
            account = _mapping(value.get("account"))
            account_id = str(account.get("account_id") or account.get("id") or key)
            if account_id == token_account_id or key == token_account_id:
                return account_id, value, ""
        return "", {}, "Access Token 对应的账号不在检查响应中"
    if len(candidates) == 1:
        key, value = candidates[0]
        account = _mapping(value.get("account"))
        return str(account.get("account_id") or account.get("id") or key), value, ""
    if not candidates:
        return "", {}, "检查响应中没有账号数据"
    return "", {}, "检查响应包含多个账号，但 Access Token 中没有明确账号 ID"


def _classify(payload: object, access_token: str) -> dict[str, object]:
    root = _mapping(payload)
    accounts = _mapping(root.get("accounts"))
    account_id, record, selection_error = _select_account(
        accounts,
        _token_account_id(access_token),
    )
    if selection_error:
        return {
            "state": "unknown",
            "label": "无法确认",
            "is_plus": None,
            "error": selection_error,
        }

    account = _mapping(record.get("account"))
    entitlement = _mapping(record.get("entitlement"))
    plan_type = str(account.get("plan_type") or "").strip().lower()
    subscription_plan = _subscription_name(entitlement)
    active_value = entitlement.get("has_active_subscription")
    active = active_value if isinstance(active_value, bool) else None
    expires_value = entitlement.get("expires_at") or entitlement.get("subscription_expires_at")
    expired = _expired(expires_value)
    evidence = {
        "account_id": account_id,
        "plan_type": plan_type,
        "subscription_plan": subscription_plan,
        "has_active_subscription": active,
        "expires_at": str(expires_value or "") or None,
    }

    if account.get("is_deactivated") is True:
        return {
            **evidence,
            "state": "deactivated",
            "label": "账号已停用",
            "is_plus": False,
            "error": "",
        }

    plus_plan = plan_type in {"plus", "chatgpt_plus", "chatgptplusplan"}
    subscription_is_plus = not subscription_plan or "plus" in subscription_plan
    if plus_plan and active is True and subscription_is_plus and expired is not True:
        return {
            **evidence,
            "state": "plus",
            "label": "Plus 已生效",
            "is_plus": True,
            "error": "",
        }
    if plus_plan and active is False:
        return {
            **evidence,
            "state": "not_plus",
            "label": "Plus 未生效",
            "is_plus": False,
            "error": "订阅权益未处于有效状态",
        }
    if plan_type == "free" and active is False:
        return {
            **evidence,
            "state": "free",
            "label": "Free",
            "is_plus": False,
            "error": "",
        }
    if active is True and not plus_plan:
        return {
            **evidence,
            "state": "other_plan",
            "label": "其他有效套餐",
            "is_plus": False,
            "error": "有效订阅不是 Plus 套餐",
        }
    return {
        **evidence,
        "state": "unknown",
        "label": "无法确认",
        "is_plus": None,
        "error": "套餐与订阅权益字段缺失或互相矛盾",
    }


def check_plus(access_token: str, proxy: str = "") -> dict[str, object]:
    from curl_cffi import requests as cffi_requests

    account_id = _token_account_id(access_token)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    proxies: Any = {"http": proxy, "https": proxy} if proxy else None
    try:
        response = cffi_requests.get(
            "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27",
            headers=headers,
            proxies=proxies,
            impersonate="chrome110",
            timeout=20,
        )
    except Exception as error:
        return {
            "state": "error",
            "label": "检查失败",
            "is_plus": None,
            "error": str(error),
        }
    if response.status_code == 401:
        return {
            "state": "invalid_token",
            "label": "令牌已失效",
            "is_plus": None,
            "error": "HTTP 401",
        }
    if response.status_code == 403:
        return {
            "state": "forbidden",
            "label": "无权检查",
            "is_plus": None,
            "error": "HTTP 403",
        }
    if response.status_code == 429:
        return {
            "state": "rate_limited",
            "label": "请求过于频繁",
            "is_plus": None,
            "error": "HTTP 429",
        }
    if response.status_code != 200:
        return {
            "state": "error",
            "label": "检查失败",
            "is_plus": None,
            "error": f"HTTP {response.status_code}",
        }
    try:
        payload: object = json.loads(response.text)
        return _classify(payload, access_token)
    except (TypeError, ValueError) as error:
        return {
            "state": "unknown",
            "label": "无法确认",
            "is_plus": None,
            "error": f"无法解析检查响应: {error}",
        }
