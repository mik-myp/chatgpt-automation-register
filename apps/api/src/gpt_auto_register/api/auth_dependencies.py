from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.security import token_hash, tokens_equal, verify_password
from gpt_auto_register.db.models.auth import SetupState
from gpt_auto_register.infrastructure.authentication import (
    SESSION_COOKIE_NAME,
    AuthenticatedSession,
    AuthenticationService,
)


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def validate_origin(request: Request) -> None:
    settings = get_settings()
    if not settings.authentication_enabled:
        return
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or origin not in settings.trusted_origin_set:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "请求来源不受信任")


def require_authenticated(request: Request, db: DatabaseSession) -> AuthenticatedSession | None:
    settings = get_settings()
    if not settings.authentication_enabled or not getattr(
        request.app.state, "authentication_enabled", True
    ):
        return None
    setup = db.get(SetupState, 1)
    if setup is None or not setup.initialized:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "系统尚未初始化")
    raw_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    authenticated = AuthenticationService(db, settings).authenticate(raw_token)
    if authenticated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已失效")
    request.state.authenticated = authenticated
    return authenticated


CurrentSession = Annotated[AuthenticatedSession | None, Depends(require_authenticated)]


def require_csrf(
    request: Request,
    authenticated: CurrentSession,
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"} or authenticated is None:
        return
    validate_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not tokens_equal(
        token_hash(supplied), authenticated.session.csrf_token_hash
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF 校验失败")


def require_reauthentication(
    authenticated: AuthenticatedSession | None,
    password: str,
) -> None:
    if authenticated is None:
        return
    if not password or not verify_password(authenticated.user.password_hash, password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要重新验证管理员密码")
