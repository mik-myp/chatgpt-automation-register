from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gpt_auto_register.core.config import get_settings


class TrustedAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        hostname = (request.url.hostname or "").lower().rstrip(".")
        allowed_hosts = {value.lower().rstrip(".") for value in settings.trusted_host_list}
        if hostname not in allowed_hosts and "*" not in allowed_hosts:
            return JSONResponse({"detail": "API 拒绝不受信任的 Host"}, status_code=403)
        origin = request.headers.get("origin", "").rstrip("/")
        current_origin = f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/")
        if origin and origin != current_origin and origin not in settings.trusted_origin_set:
            return JSONResponse({"detail": "API 拒绝不受信任的 Origin"}, status_code=403)
        return await call_next(request)


# Compatibility alias for integrations importing the old middleware name.
LocalAccessMiddleware = TrustedAccessMiddleware
