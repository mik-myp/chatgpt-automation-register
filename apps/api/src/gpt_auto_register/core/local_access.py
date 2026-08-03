from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gpt_auto_register.core.config import get_settings


def origin_matches_request_host(request: Request) -> bool:
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin:
        return False
    origin_url = urlsplit(origin)
    if origin_url.scheme not in {"http", "https"} or not origin_url.netloc:
        return False
    return origin_url.netloc.lower() == request.headers.get("host", "").lower()


class TrustedAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        origin = request.headers.get("origin", "").rstrip("/")
        if settings.environment == "production":
            if origin and not origin_matches_request_host(request):
                return JSONResponse({"detail": "API 拒绝跨来源请求"}, status_code=403)
            return await call_next(request)

        hostname = (request.url.hostname or "").lower().rstrip(".")
        allowed_hosts = {value.lower().rstrip(".") for value in settings.trusted_host_list}
        if hostname not in allowed_hosts and "*" not in allowed_hosts:
            return JSONResponse({"detail": "API 拒绝不受信任的 Host"}, status_code=403)
        current_origin = f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/")
        if origin and origin != current_origin and origin not in settings.trusted_origin_set:
            return JSONResponse({"detail": "API 拒绝不受信任的 Origin"}, status_code=403)
        return await call_next(request)


# Compatibility alias for integrations importing the old middleware name.
LocalAccessMiddleware = TrustedAccessMiddleware
