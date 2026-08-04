from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.core.config import get_settings
from gpt_auto_register.db.models.auth import User, UserRole
from gpt_auto_register.infrastructure.authentication import AuthenticationService
from gpt_auto_register.modules.users.schemas import (
    UserCreateRequest,
    UserListResponse,
    UserSummary,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def list_users(db: DatabaseSession) -> UserListResponse:
    users = list(db.scalars(select(User).order_by(User.created_at.asc(), User.username.asc())))
    return UserListResponse(
        items=[UserSummary.model_validate(user) for user in users],
        total=len(users),
    )


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, db: DatabaseSession) -> UserSummary:
    try:
        user = AuthenticationService(db, get_settings()).create_user(
            payload.username,
            payload.password,
            role=payload.role,
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在") from error
    return UserSummary.model_validate(user)


@router.patch("/{user_id}", response_model=UserSummary)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    db: DatabaseSession,
) -> UserSummary:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")

    next_role = payload.role if payload.role is not None else user.role
    next_active = payload.active if payload.active is not None else user.active
    removes_active_admin = (
        user.role == UserRole.ADMIN
        and user.active
        and (next_role != UserRole.ADMIN or not next_active)
    )
    if removes_active_admin:
        active_admins = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.active.is_(True))
        )
        if int(active_admins or 0) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "系统至少需要一个启用的管理员")

    user.role = next_role
    user.active = next_active
    db.commit()
    return UserSummary.model_validate(user)
