from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from gpt_auto_register.db.models.accounts import AccountStatus, MailType


class AccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    mail_type: MailType
    status: AccountStatus
    claimed_at: datetime | None
    finished_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    password_status: str = "not_set"
    mfa_status: str = "not_enabled"
    security_error: str | None = None


class AccountDetail(AccountSummary):
    password: str | None
    client_id: str | None
    refresh_token: str | None
    mail_url: str | None


class AccountListResponse(BaseModel):
    items: list[AccountSummary]
    total: int
    limit: int
    offset: int


class AccountStats(BaseModel):
    total: int
    available: int
    in_use: int
    done: int
    failed: int


class ImportAccountsRequest(BaseModel):
    text: str = Field(min_length=1)


class ImportAccountsResponse(BaseModel):
    inserted: int
    updated: int
    unchanged: int
    invalid: int
    invalid_lines: list[int]


class ClaimAccountRequest(BaseModel):
    email: str | None = None


class BulkAccountAction(StrEnum):
    RELEASE = "release"
    RESET = "reset"
    DELETE = "delete"
    SET_PASSWORD = "set_password"
    ENABLE_MFA = "enable_mfa"


class BulkAccountRequest(BaseModel):
    action: BulkAccountAction
    emails: list[str] = Field(min_length=1)


class BulkAccountResponse(BaseModel):
    processed: int
    skipped: int
    job_id: str | None = None


class AccountMaintenanceAction(StrEnum):
    RESET_FAILED = "reset_failed"
    RELEASE_STALE = "release_stale"
    DELETE_STATUS = "delete_status"


class AccountMaintenanceRequest(BaseModel):
    action: AccountMaintenanceAction
    status: AccountStatus | None = None
    stale_minutes: int = Field(default=30, ge=1, le=1440)


class AccountMaintenanceResponse(BaseModel):
    processed: int
    skipped: int = 0
