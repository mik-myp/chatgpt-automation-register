from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx


class KakaoApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class KakaoClient:
    def __init__(self, base_url: str, timeout: int) -> None:
        normalized = base_url.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Kakao Base URL 无效")
        self.base_url = normalized
        self.timeout = timeout

    def list_tasks(self, card: str, *, page: int = 1, page_size: int = 100) -> object:
        return self.request(
            "GET",
            "api/kakao-link/tasks",
            params={
                "card": card,
                "status": "",
                "page": page,
                "page_size": page_size,
            },
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool | None] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> object:
        try:
            response = httpx.request(
                method,
                urljoin(f"{self.base_url}/", path.lstrip("/")),
                params=params,
                json=json_body,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            try:
                payload = error.response.json()
            except ValueError:
                payload = error.response.text[:300]
            raise KakaoApiError(
                f"Kakao API 请求失败 (HTTP {status_code}): {payload}",
                status_code if status_code < 500 else 502,
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise KakaoApiError(f"Kakao API 连接失败: {error}") from error

    def check_eligibility(self, access_tokens: list[str]) -> object:
        return self.request(
            "POST",
            "api/promo-coupon/check",
            json_body={"accessTokens": access_tokens},
        )

    def create_tasks(
        self,
        *,
        card: str,
        access_tokens: list[str],
        plan_type: str,
        promo_code: str,
    ) -> object:
        return self.request(
            "POST",
            "api/kakao-link/tasks",
            json_body={
                "card": card,
                "accessTokens": access_tokens,
                "plan_type": plan_type,
                "promo_code": promo_code,
            },
        )

    def task_statuses(self, job_ids: list[str]) -> object:
        return self.request(
            "GET",
            "api/kakao-link/tasks/statuses",
            params={"job_ids": ",".join(job_ids)},
        )

    def task_detail(self, job_id: str) -> object:
        return self.request("GET", f"api/kakao-link/tasks/{quote(job_id, safe='')}")

    def cancel_task(self, job_id: str) -> object:
        return self.request(
            "POST", f"api/kakao-link/tasks/{quote(job_id, safe='')}/cancel"
        )

    def retry_task(self, job_id: str) -> object:
        return self.request(
            "POST", f"api/kakao-link/tasks/{quote(job_id, safe='')}/retry"
        )

    def kakao_status(self, job_id: str) -> object:
        return self.request("GET", f"api/kakao-status/{quote(job_id, safe='')}")

    def list_all_tasks(self, card: str) -> list[dict[str, Any]]:
        page_size = 100
        tasks: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(1, 1001):
            batch = payload_tasks(self.list_tasks(card, page=page, page_size=page_size))
            added = 0
            for index, task in enumerate(batch):
                identity = str(
                    task.get("job_id")
                    or task.get("id")
                    or f"{page}:{index}:{task!r}"
                )
                if identity in seen:
                    continue
                seen.add(identity)
                tasks.append(task)
                added += 1
            if len(batch) < page_size or added == 0:
                break
        return tasks


def payload_tasks(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if payload.get("job_id") or payload.get("id"):
        return [payload]
    items: list[dict[str, Any]] = []
    for key in ("tasks", "items", "results", "active_duplicates"):
        value = payload.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    for key in ("task", "data"):
        value = payload.get(key)
        if isinstance(value, dict):
            items.extend(payload_tasks(value))
    return items
