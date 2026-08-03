from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError

from gpt_auto_register.api.auth_dependencies import client_address, validate_origin
from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.security import tokens_equal
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.auth import SetupState
from gpt_auto_register.infrastructure.authentication import AuthenticationService
from gpt_auto_register.modules.auth.router import set_session_cookie
from gpt_auto_register.modules.setup.schemas import (
    SetupInitializeRequest,
    SetupInitializeResponse,
    SetupPreflightResponse,
    SetupStatusResponse,
)

router = APIRouter(prefix="/setup", tags=["setup"])


def _is_initialized(db: DatabaseSession) -> bool:
    state = db.get(SetupState, 1)
    return bool(state and state.initialized)


@router.get("/status", response_model=SetupStatusResponse)
def setup_status(request: Request, db: DatabaseSession) -> SetupStatusResponse:
    return SetupStatusResponse(
        initialized=_is_initialized(db),
        authentication_enabled=bool(
            get_settings().authentication_enabled
            and getattr(request.app.state, "authentication_enabled", True)
        ),
    )


@router.get("/preflight", response_model=SetupPreflightResponse)
def setup_preflight(db: DatabaseSession) -> SetupPreflightResponse:
    if _is_initialized(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "系统已经初始化")
    settings = get_settings()
    settings.ensure_runtime_directories()
    return SetupPreflightResponse(
        database=settings.database_dialect,
        data_directory_writable=settings.data_path.exists() and settings.data_path.is_dir(),
        master_key_file=str(settings.resolved_master_key_file),
    )


@router.post("/initialize", response_model=SetupInitializeResponse)
def initialize(
    payload: SetupInitializeRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> SetupInitializeResponse:
    validate_origin(request)
    expires_at: datetime | None = getattr(request.app.state, "setup_token_expires_at", None)
    expected_token: str = getattr(request.app.state, "setup_token", "")
    now = utc_now()
    if (
        not expected_token
        or expires_at is None
        or (expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at) <= now
        or not tokens_equal(expected_token, payload.token)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "初始化令牌无效或已过期")

    try:
        state = db.get(SetupState, 1, with_for_update=True)
        if state is None:
            state = SetupState(id=1, initialized=False)
            db.add(state)
            db.flush()
        if state.initialized:
            raise HTTPException(status.HTTP_409_CONFLICT, "系统已经初始化")
        service = AuthenticationService(db, get_settings())
        user = service.create_user(payload.username, payload.password)
        state.initialized = True
        state.initialized_at = now
        state.administrator_id = user.id
        authenticated = service.issue_session(
            user,
            client_address=client_address(request),
            user_agent=request.headers.get("user-agent", ""),
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "系统已经初始化或用户名已存在") from error

    request.app.state.setup_token = ""
    request.app.state.setup_token_expires_at = None
    set_session_cookie(response, authenticated.raw_token)
    return SetupInitializeResponse(
        username=user.username,
        role=user.role.value,
        csrf_token=authenticated.csrf_token,
    )
