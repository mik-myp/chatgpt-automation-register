from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gpt_auto_register.db.models.kakao import KakaoTaskStatus
from gpt_auto_register.db.models.pipeline import (
    PipelineItemStatus,
    PipelineRunKind,
    PipelineStatus,
)


class PipelineRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: PipelineRunKind
    source_pipeline_run_id: str | None
    status: PipelineStatus
    mode: str
    target_count: int
    kakao_enabled: bool
    scheduled_count: int
    registered_count: int
    failed_count: int
    kakao_task_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PipelineRunListResponse(BaseModel):
    items: list[PipelineRunSummary]
    total: int
    limit: int
    offset: int


class PipelineRunCreateRequest(BaseModel):
    mode: Literal["single", "batch"] = "single"
    email: str = Field(default="", max_length=320)
    target_count: int = Field(default=1, ge=1, le=10000)
    concurrency: int | None = Field(default=None, ge=1, le=50)
    otp_timeout: int | None = Field(default=None, ge=1, le=300)
    proxy: str | None = None
    proxy_pool: str | None = None
    kakao_enabled: bool = True


class PipelineItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    account_email: str | None
    registration_run_id: str | None
    card_code_snapshot: str | None = None
    status: PipelineItemStatus
    eligibility_state: str | None
    password_status: str | None
    mfa_status: str | None
    security_error: str | None
    error: str | None
    plus_state: str | None = None
    plus_label: str | None = None
    plus_is_active: bool | None = None
    plus_error: str | None = None
    plus_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PipelineCardAssignmentSummary(BaseModel):
    task_id: str
    email: str
    status: KakaoTaskStatus
    payment_status: str | None
    card_charged: bool | None


class PipelineCardAllocationSummary(BaseModel):
    card_id: str
    card_code: str
    allocated_count: int
    created_count: int
    duplicate_count: int
    failed_count: int
    assignments: list[PipelineCardAssignmentSummary] = Field(default_factory=list)


class PipelineRunDetail(PipelineRunSummary):
    config_snapshot: dict[str, object]


class PipelineItemListResponse(BaseModel):
    items: list[PipelineItemSummary]
    total: int
    limit: int
    offset: int


class PipelineCardAllocationListResponse(BaseModel):
    items: list[PipelineCardAllocationSummary]
    total: int
    limit: int
    offset: int


class BulkPipelineAction(StrEnum):
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    DELETE = "delete"


class BulkPipelineRequest(BaseModel):
    action: BulkPipelineAction
    run_ids: list[str] = Field(min_length=1)


class BulkPipelineResponse(BaseModel):
    processed: int
    skipped: int


class RetryPipelineItemsRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1)


class SecurityPipelineCandidate(BaseModel):
    email: str
    password_status: str
    mfa_status: str
    security_error: str | None = None
    needs_password: bool
    needs_mfa: bool


class SecurityPipelineCandidateList(BaseModel):
    items: list[SecurityPipelineCandidate]


class SecurityPipelineCandidatePage(SecurityPipelineCandidateList):
    total: int
    limit: int
    offset: int


class CreateSecurityPipelineRequest(BaseModel):
    emails: list[str] = Field(min_length=1)


class KakaoPipelineCandidate(BaseModel):
    email: str
    eligibility_state: str | None = None
    eligibility_error: str | None = None
    eligibility_checked_at: datetime | None = None


class KakaoPipelineCandidateList(BaseModel):
    items: list[KakaoPipelineCandidate]


class KakaoPipelineCandidatePage(KakaoPipelineCandidateList):
    total: int
    limit: int
    offset: int


class CreateKakaoPipelineRequest(BaseModel):
    emails: list[str] = Field(min_length=1)


class CopySecurityCredentialsRequest(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    all_completed: bool = False


class PipelineEventSummary(BaseModel):
    id: int
    cursor: int
    sequence: int
    level: str
    event_type: str
    message: str
    data: dict[str, object]
    created_at: datetime


class PipelineEventListResponse(BaseModel):
    items: list[PipelineEventSummary]
    last_cursor: int
    terminal: bool


class PipelineDeliverySummary(BaseModel):
    task_id: str
    upstream_job_id: str
    email: str
    task_status: KakaoTaskStatus
    payment_status: str | None
    payment_message: str | None
    payment_url: str | None
    payment_expires_at: datetime | None
    card_charged: bool | None
    mail_url: str | None
    chatgpt_password: str | None
    totp_secret: str | None
    password_status: str
    mfa_status: str
    account_format: Literal["security_credentials", "mail_access", "unavailable"]
    account_missing_reason: str | None
    payment_copyable: bool
    account_copyable: bool
    deliverable: bool
    plus_state: str | None = None
    plus_label: str | None = None
    plus_is_active: bool | None = None
    plus_error: str | None = None
    plus_checked_at: datetime | None = None


class PipelineDeliveryListResponse(BaseModel):
    items: list[PipelineDeliverySummary]
    total: int
    limit: int
    offset: int


class CopyPipelineDeliveriesRequest(BaseModel):
    task_ids: list[str] = Field(default_factory=list)
    all_deliverable: bool = False
    copy_type: Literal["payment_links", "account_info"]


class PipelineDeliveryCopyMark(BaseModel):
    email: str
    fingerprint: str


class CopyPipelineDeliveriesResponse(BaseModel):
    text: str
    copied: int
    skipped: int
    security_credentials: int = 0
    mail_access: int = 0
    missing_mail_url: int = 0
    duplicates: int = 0
    plus_restricted: int = 0
    copy_marks: list[PipelineDeliveryCopyMark] = Field(default_factory=list)


class ConfirmPipelineDeliveryCopiesRequest(BaseModel):
    copy_marks: list[PipelineDeliveryCopyMark] = Field(default_factory=list)


class ConfirmPipelineDeliveryCopiesResponse(BaseModel):
    processed: int
