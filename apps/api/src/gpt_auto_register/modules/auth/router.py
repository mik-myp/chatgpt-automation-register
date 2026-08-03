from fastapi import APIRouter, HTTPException, Request, Response, status

from gpt_auto_register.api.auth_dependencies import (
    CurrentSession,
    client_address,
    require_csrf,
    validate_origin,
)
from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.core.config import get_settings
from gpt_auto_register.db.models.auth import SetupState
from gpt_auto_register.infrastructure.authentication import (
    SESSION_COOKIE_NAME,
    AuthenticationService,
)
from gpt_auto_register.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    SessionResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_absolute_days * 86400,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> SessionResponse:
    validate_origin(request)
    settings = get_settings()
    setup = db.get(SetupState, 1)
    if setup is None or not setup.initialized:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "系统尚未初始化")
    service = AuthenticationService(db, settings)
    username = payload.username.strip().lower()
    address = client_address(request)
    if not service.login_allowed(username, address):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "登录尝试过于频繁，请稍后再试")
    user = service.verify_login(username, payload.password)
    service.record_login(username, address, succeeded=user is not None)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    authenticated = service.issue_session(
        user,
        client_address=address,
        user_agent=request.headers.get("user-agent", ""),
    )
    db.commit()
    set_session_cookie(response, authenticated.raw_token)
    return SessionResponse(
        username=user.username,
        role=user.role.value,
        csrf_token=authenticated.csrf_token,
    )


@router.get("/session", response_model=SessionResponse)
def session(authenticated: CurrentSession) -> SessionResponse:
    if authenticated is None:
        return SessionResponse(username="developer", role="admin", csrf_token="")
    return SessionResponse(
        username=authenticated.user.username,
        role=authenticated.user.role.value,
        csrf_token=authenticated.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: DatabaseSession,
    authenticated: CurrentSession,
) -> Response:
    require_csrf(request, authenticated)
    if authenticated is not None:
        AuthenticationService(db, get_settings()).revoke(authenticated.session.id)
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    request: Request,
    response: Response,
    db: DatabaseSession,
    authenticated: CurrentSession,
) -> Response:
    require_csrf(request, authenticated)
    if authenticated is not None:
        AuthenticationService(db, get_settings()).revoke_all(authenticated.user.id)
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
    authenticated: CurrentSession,
) -> Response:
    require_csrf(request, authenticated)
    if authenticated is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    if not AuthenticationService(db, get_settings()).change_password(
        authenticated.user, payload.current_password, payload.new_password
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "当前密码不正确")
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
