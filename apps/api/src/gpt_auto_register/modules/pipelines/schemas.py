from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gpt_auto_register.db.models.kakao import KakaoTaskStatus
from gpt_auto_register.db.models.pipeline import PipelineItemStatus, PipelineStatus


class PipelineRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
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
    status: PipelineItemStatus
    eligibility_state: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class PipelineCardAllocationSummary(BaseModel):
    card_id: str
    card_code: str
    allocated_count: int
    created_count: int
    duplicate_count: int
    failed_count: int


class PipelineRunDetail(PipelineRunSummary):
    config_snapshot: dict[str, object]
    items: list[PipelineItemSummary]
    cards: list[PipelineCardAllocationSummary]


class BulkPipelineAction(StrEnum):
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"


class BulkPipelineRequest(BaseModel):
    action: BulkPipelineAction
    run_ids: list[str] = Field(min_length=1)


class BulkPipelineResponse(BaseModel):
    processed: int
    skipped: int


class RetryPipelineItemsRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1)


class PipelineEventSummary(BaseModel):
    id: int
    sequence: int
    level: str
    event_type: str
    message: str
    data: dict[str, object]
    created_at: datetime


class PipelineEventListResponse(BaseModel):
    items: list[PipelineEventSummary]
    last_sequence: int
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
    deliverable: bool


class PipelineDeliveryListResponse(BaseModel):
    items: list[PipelineDeliverySummary]
    total: int
    limit: int
    offset: int


class CopyPipelineDeliveriesRequest(BaseModel):
    task_ids: list[str] = Field(default_factory=list)
    all_deliverable: bool = False


class CopyPipelineDeliveriesResponse(BaseModel):
    text: str
    copied: int
    skipped: int
