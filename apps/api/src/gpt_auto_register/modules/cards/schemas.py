from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from gpt_auto_register.db.models.kakao import CardBatchStatus


class CardInventoryItem(BaseModel):
    id: str
    code: str
    batch_id: str
    batch_name: str
    batch_status: CardBatchStatus
    position: int
    active: bool
    run_count: int
    allocated_count: int
    created_count: int
    duplicate_count: int
    failed_count: int
    cached_charged: int | None
    cached_pending: int | None
    cached_remaining: int | None
    usage_error: str | None
    usage_checked_at: datetime | None
    created_at: datetime


class CardInventoryResponse(BaseModel):
    items: list[CardInventoryItem]
    total: int
    limit: int
    offset: int


class CardInventoryStats(BaseModel):
    total: int
    active: int
    inactive: int
    batches: int


class ImportCardsRequest(BaseModel):
    text: str = Field(min_length=1)
    batch_name: str = Field(default="", max_length=128)


class ImportCardsResponse(BaseModel):
    batch_id: str | None
    inserted: int
    duplicates: int


class BulkCardAction(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    DELETE = "delete"


class BulkCardRequest(BaseModel):
    action: BulkCardAction
    card_ids: list[str] = Field(min_length=1)


class BulkCardResponse(BaseModel):
    processed: int
    skipped: int


class CardSelectionRequest(BaseModel):
    target_count: int = Field(ge=1)


class CardUsageItem(BaseModel):
    card_id: str
    code: str
    charged: int
    pending: int
    remaining: int
    error: str | None


class CardSelectionResponse(BaseModel):
    slots: list[str]
    usage: list[CardUsageItem]


class CardUsageResponse(BaseModel):
    items: list[CardUsageItem]
