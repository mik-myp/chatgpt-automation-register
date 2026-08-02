from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gpt_auto_register.db.base import Base
from gpt_auto_register.db.models.common import (
    JsonObject,
    TimestampMixin,
    enum_type,
    json_object_column,
    new_id,
)


class CardBatchStatus(StrEnum):
    READY = "ready"
    CONSUMED = "consumed"
    ARCHIVED = "archived"


class KakaoCardBatch(TimestampMixin, Base):
    __tablename__ = "kakao_card_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[CardBatchStatus] = mapped_column(
        enum_type(CardBatchStatus, "card_batch_status"),
        default=CardBatchStatus.READY,
        index=True,
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KakaoCard(TimestampMixin, Base):
    __tablename__ = "kakao_cards"
    __table_args__ = (
        UniqueConstraint("batch_id", "position", name="uq_kakao_cards_batch_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("kakao_card_batches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PipelineCardAllocation(Base):
    __tablename__ = "pipeline_card_allocations"

    pipeline_run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), primary_key=True
    )
    card_id: Mapped[str] = mapped_column(
        ForeignKey("kakao_cards.id", ondelete="RESTRICT"), primary_key=True
    )
    allocated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class KakaoTaskStatus(StrEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


class KakaoTask(TimestampMixin, Base):
    __tablename__ = "kakao_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    upstream_job_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"), index=True
    )
    pipeline_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_items.id", ondelete="SET NULL"), index=True
    )
    card_id: Mapped[str | None] = mapped_column(
        ForeignKey("kakao_cards.id", ondelete="SET NULL"), index=True
    )
    card_code_snapshot: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(320), index=True)
    status: Mapped[KakaoTaskStatus] = mapped_column(
        enum_type(KakaoTaskStatus, "kakao_task_status"), index=True, nullable=False
    )
    payment_status: Mapped[str | None] = mapped_column(String(64), index=True)
    payment_message: Mapped[str | None] = mapped_column(Text)
    payment_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    payment_scanned: Mapped[bool | None] = mapped_column(Boolean)
    payment_successful: Mapped[bool | None] = mapped_column(Boolean)
    card_charged: Mapped[bool | None] = mapped_column(Boolean)
    payment_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    upstream_payload: Mapped[JsonObject] = json_object_column()
