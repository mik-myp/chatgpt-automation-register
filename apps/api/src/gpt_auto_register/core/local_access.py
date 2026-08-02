from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_LOCAL_NAMES = {"localhost", "testserver"}


def is_local_hostname(value: str | None) -> bool:
    if not value:
        return False
    hostname = value.strip().lower().rstrip(".")
    if hostname in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class LocalAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not is_local_hostname(request.url.hostname):
            return JSONResponse({"detail": "本地 API 拒绝非本机 Host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and not is_local_hostname(urlparse(origin).hostname):
            return JSONResponse({"detail": "本地 API 拒绝非本机 Origin"}, status_code=403)
        client_host = request.client.host if request.client else None
        if client_host not in {"testclient", None} and not is_local_hostname(client_host):
            return JSONResponse({"detail": "本地 API 拒绝远程客户端"}, status_code=403)
        return await call_next(request)
