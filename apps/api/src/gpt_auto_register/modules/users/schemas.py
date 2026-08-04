from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from gpt_auto_register.db.models.auth import UserRole


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: UserRole
    active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=1024)
    role: UserRole = UserRole.USER


class UserUpdateRequest(BaseModel):
    role: UserRole | None = None
    active: bool | None = None
