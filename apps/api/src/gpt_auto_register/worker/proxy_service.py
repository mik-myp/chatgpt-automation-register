from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.modules.settings.schemas import ProxySettings
from gpt_auto_register.worker.runtime_service import SessionFactory, emit_event

_PROXY_PATTERN = re.compile(
    r"^(?:(?P<scheme>https?|socks5h?|socks4)://)?"
    r"(?:(?P<username>[^:@/\s]+):(?P<password>[^@/\s]+)@)?"
    r"(?P<host>\[[0-9a-fA-F:]+\]|[^:/\s]+):(?P<port>\d{1,5})$"
)
_COUNT_PARAMETERS = ("num", "count", "number", "quantity")


class ProxyApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyBatch:
    assignments: dict[str, list[str]]
    requested: int
    received: int
    duplicate_count: int
    invalid_count: int


def normalize_proxy(value: str) -> str:
    candidate = value.strip().strip("'\"")
    match = _PROXY_PATTERN.fullmatch(candidate)
    if match is None:
        raise ValueError(f"代理格式无效: {candidate[:120]}")
    port = int(match.group("port"))
    if port < 1 or port > 65535:
        raise ValueError(f"代理端口超出范围: {port}")
    scheme = (match.group("scheme") or "http").lower()
    credentials = ""
    if match.group("username"):
        credentials = f"{match.group('username')}:{match.group('password')}@"
    return f"{scheme}://{credentials}{match.group('host')}:{port}"


def _request_url(api_url: str, count: int, *, region: str = "") -> str:
    value = api_url.strip()
    if not value:
        raise ProxyApiError("未配置代理 API 链接地址")
    if "{count}" in value:
        value = value.replace("{count}", str(count))
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProxyApiError("代理 API 链接地址无效")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    existing = next(
        (name for name in _COUNT_PARAMETERS if any(key == name for key, _ in query)),
        None,
    )
    if existing:
        query = [(key, str(count) if key == existing else item) for key, item in query]
    elif "{count}" not in api_url:
        query.append(("num", str(count)))
    if region:
        normalized_region = region.strip().upper()
        found_region = any(key == "region" for key, _ in query)
        query = [
            (key, normalized_region if key == "region" else item) for key, item in query
        ]
        if not found_region:
            query.append(("region", normalized_region))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _proxy_candidates(value: object) -> list[str]:
    if isinstance(value, str):
        return [item for item in re.split(r"[\r\n,;\s]+", value) if item]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_proxy_candidates(item))
        return result
    if not isinstance(value, dict):
        return []
    for key in ("proxy", "address", "server"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return [candidate]
    host = value.get("ip") or value.get("host")
    port = value.get("port")
    if host and port:
        auth = ""
        username = value.get("username") or value.get("user")
        password = value.get("password") or value.get("pass")
        if username and password:
            auth = f"{username}:{password}@"
        scheme = str(value.get("scheme") or value.get("protocol") or "http")
        return [f"{scheme}://{auth}{host}:{port}"]
    result = []
    for key in ("data", "list", "proxies", "items", "result", "rows"):
        if key in value:
            result.extend(_proxy_candidates(value[key]))
    return result


class ProxyAllocator:
    def __init__(
        self,
        settings: ProxySettings,
        session_factory: SessionFactory,
        job_id: str,
        step: str,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.job_id = job_id
        self.step = step

    def allocate(self, account_keys: list[str], *, region: str = "") -> ProxyBatch:
        keys = list(dict.fromkeys(account_keys))
        attempts = self.settings.max_attempts_per_account
        requested = len(keys) * attempts
        if not self.settings.api_url.strip():
            message = "未配置代理 API 链接地址，新任务禁止使用直连或旧代理池"
            emit_event(
                self.session_factory,
                self.job_id,
                "proxy_api_not_configured",
                message,
                level="error",
                data={"step": self.step, "accounts": len(keys), "region": region},
            )
            raise ProxyApiError(message)
        emit_event(
            self.session_factory,
            self.job_id,
            "proxy_api_request_started",
            f"正在为 {len(keys)} 个账号请求 {requested} 个{region or '通用'}代理",
            data={
                "step": self.step,
                "accounts": len(keys),
                "attempts": attempts,
                "requested": requested,
                "region": region,
            },
        )
        try:
            response = httpx.get(
                _request_url(self.settings.api_url, requested, region=region),
                headers={"Accept": "application/json, text/plain"},
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            try:
                payload: object = response.json()
            except ValueError:
                payload = response.text
        except (httpx.HTTPError, ProxyApiError) as error:
            message = f"代理 API 请求失败: {error}"
            emit_event(
                self.session_factory,
                self.job_id,
                "proxy_api_request_failed",
                message,
                level="error",
                data={"step": self.step, "requested": requested, "region": region},
            )
            raise ProxyApiError(message) from error

        proxy_slots: list[str | None] = []
        seen: set[str] = set()
        duplicate_count = invalid_count = 0
        for candidate in _proxy_candidates(payload):
            try:
                normalized = normalize_proxy(candidate)
            except ValueError:
                invalid_count += 1
                proxy_slots.append(None)
                continue
            if normalized in seen:
                duplicate_count += 1
            else:
                seen.add(normalized)
            proxy_slots.append(normalized)

        assignments: dict[str, list[str]] = {}
        for index, key in enumerate(keys):
            start = index * attempts
            group = proxy_slots[start : start + attempts]
            if len(group) == attempts and all(group):
                assignments[key] = [str(proxy) for proxy in group]
        valid_count = sum(proxy is not None for proxy in proxy_slots)
        level = "info" if len(assignments) == len(keys) else "error"
        message = (
            f"代理 API 返回 {valid_count}/{requested} 个有效代理位置"
            if level == "info"
            else (
                f"代理数量不足或存在无效位置：需要 {requested}，"
                f"API 返回 {len(proxy_slots)} 项，其中有效代理位置 {valid_count} 个"
            )
        )
        emit_event(
            self.session_factory,
            self.job_id,
            "proxy_api_request_completed" if level == "info" else "proxy_api_insufficient",
            message,
            level=level,
            data={
                "step": self.step,
                "requested": requested,
                "returned": len(proxy_slots),
                "received": valid_count,
                "duplicates": duplicate_count,
                "invalid": invalid_count,
                "fully_allocated_accounts": len(assignments),
                "region": region,
            },
        )
        return ProxyBatch(assignments, requested, valid_count, duplicate_count, invalid_count)


def emit_proxy_attempt(
    session_factory: SessionFactory,
    job_id: str,
    *,
    email: str,
    item_id: str,
    step: str,
    attempt: int,
    proxy: str,
    started_at: object,
    succeeded: bool,
    error: str = "",
) -> None:
    finished_at = utc_now()
    emit_event(
        session_factory,
        job_id,
        "proxy_attempt_succeeded" if succeeded else "proxy_attempt_failed",
        f"{step}第 {attempt} 次代理尝试{'成功' if succeeded else '失败'} {email}",
        level="info" if succeeded else "warning",
        data={
            "email": email,
            "item_id": item_id,
            "step": step,
            "attempt": attempt,
            "proxy": proxy,
            "result": "succeeded" if succeeded else "failed",
            "failure_reason": error,
            "started_at": getattr(started_at, "isoformat", lambda: str(started_at))(),
            "finished_at": finished_at.isoformat(),
        },
    )
