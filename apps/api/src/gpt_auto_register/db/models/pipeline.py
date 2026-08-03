from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gpt_auto_register.core.encryption import EncryptedJSON, EncryptedText
from gpt_auto_register.db.base import Base
from gpt_auto_register.db.models.common import (
    JsonObject,
    TimestampMixin,
    enum_type,
    new_id,
)


class PipelineStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class PipelineRunKind(StrEnum):
    REGISTRATION = "registration"
    ACCOUNT_SECURITY = "account_security"
    KAKAO = "kakao"


class PipelineItemStatus(StrEnum):
    SCHEDULED = "scheduled"
    REGISTERING = "registering"
    REGISTERED = "registered"
    SUBMITTING = "submitting"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class PipelineRun(TimestampMixin, Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[PipelineRunKind] = mapped_column(
        enum_type(PipelineRunKind, "pipeline_run_kind"),
        default=PipelineRunKind.REGISTRATION,
        index=True,
        nullable=False,
    )
    source_pipeline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[PipelineStatus] = mapped_column(
        enum_type(PipelineStatus, "pipeline_status"),
        default=PipelineStatus.QUEUED,
        index=True,
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(32), default="current", nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    kakao_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_snapshot: Mapped[JsonObject] = mapped_column(
        EncryptedJSON(), default=dict, nullable=False
    )
    scheduled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    registered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kakao_task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineItem(TimestampMixin, Base):
    __tablename__ = "pipeline_items"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "position", name="uq_pipeline_items_run_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pipeline_run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    account_email: Mapped[str | None] = mapped_column(String(320), index=True)
    mail_url_snapshot: Mapped[str | None] = mapped_column(Text)
    registration_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("registration_runs.id", ondelete="SET NULL"), index=True
    )
    card_code_snapshot: Mapped[str | None] = mapped_column(EncryptedText())
    status: Mapped[PipelineItemStatus] = mapped_column(
        enum_type(PipelineItemStatus, "pipeline_item_status"),
        default=PipelineItemStatus.SCHEDULED,
        index=True,
        nullable=False,
    )
    eligibility_state: Mapped[str | None] = mapped_column(String(64))
    password_status: Mapped[str | None] = mapped_column(String(32))
    mfa_status: Mapped[str | None] = mapped_column(String(32))
    security_error: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
