from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegistrationResultSummary(BaseModel):
    email: str
    has_password: bool
    chatgpt_password: str | None = None
    totp_secret: str | None = None
    has_access_token: bool
    has_session_token: bool
    has_refresh_token: bool
    password_status: str | None = None
    mfa_status: str | None = None
    plus_state: str | None = None
    plus_label: str | None = None
    plus_is_active: bool | None = None
    plus_error: str | None = None
    plus_checked_at: datetime | None = None
    plus_plan_type: str | None = None
    plus_subscription_plan: str | None = None
    plus_has_active_subscription: bool | None = None
    plus_expires_at: str | None = None
    created_at: datetime
    updated_at: datetime


class RegistrationResultDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    password: str | None
    access_token: str | None
    session_token: str | None
    refresh_token: str | None
    id_token: str | None
    device_id: str | None
    cookie_header: str | None
    totp_secret: str | None
    metadata_json: dict[str, object]
    created_at: datetime
    updated_at: datetime


class RegistrationResultListResponse(BaseModel):
    items: list[RegistrationResultSummary]
    total: int
    limit: int
    offset: int


class BulkResultRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    all: bool = False


class BulkResultResponse(BaseModel):
    processed: int


class PlusCheckRequest(BulkResultRequest):
    proxy: str = ""


class PlusCheckItem(BaseModel):
    email: str
    state: str
    label: str
    is_plus: bool | None = None
    error: str = ""
    account_id: str = ""
    plan_type: str = ""
    subscription_plan: str = ""
    has_active_subscription: bool | None = None
    expires_at: str | None = None


class PlusCheckResponse(BaseModel):
    items: list[PlusCheckItem]


class PublishResultsRequest(BulkResultRequest):
    targets: list[Literal["cpa", "sub2api"]] = Field(min_length=1)


class PublishResultsResponse(BaseModel):
    processed: int
    succeeded: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class ExportResultsResponse(BaseModel):
    items: list[RegistrationResultDetail]


ResultTokenFilter = Literal[
    "all",
    "access",
    "session",
    "refresh",
    "plus",
    "not_plus",
    "plus_unknown",
]
