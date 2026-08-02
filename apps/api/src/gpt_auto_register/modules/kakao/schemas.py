from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from gpt_auto_register.db.models.kakao import KakaoTaskStatus


class KakaoTaskSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    upstream_job_id: str
    pipeline_run_id: str | None
    pipeline_item_id: str | None
    card_id: str
    email: str
    status: KakaoTaskStatus
    payment_status: str | None
    payment_message: str | None
    payment_expires_at: datetime | None
    payment_scanned: bool | None
    payment_successful: bool | None
    card_charged: bool | None
    payment_url: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class KakaoTaskListResponse(BaseModel):
    items: list[KakaoTaskSummary]
    total: int
    limit: int
    offset: int
    pipeline_run_id: str | None


class KakaoTaskIdsRequest(BaseModel):
    task_ids: list[str] = Field(default_factory=list)
    pipeline_run_id: str | None = None


class KakaoTaskActionResponse(BaseModel):
    processed: int
    failed: int = 0


class KakaoEligibilityRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    all: bool = False


class KakaoEligibilityItem(BaseModel):
    email: str
    eligible: bool
    state: str
    error: str = ""


class KakaoEligibilityResponse(BaseModel):
    items: list[KakaoEligibilityItem]


class KakaoCreateTasksRequest(BaseModel):
    emails: list[str] = Field(min_length=1)


class KakaoCreateTasksResponse(BaseModel):
    created: int
    duplicates: int
