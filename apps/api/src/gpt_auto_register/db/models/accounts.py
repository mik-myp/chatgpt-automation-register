from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gpt_auto_register.core.encryption import EncryptedJSON, EncryptedText
from gpt_auto_register.db.base import Base
from gpt_auto_register.db.models.common import (
    JsonObject,
    TimestampMixin,
    enum_type,
    json_object_column,
    new_id,
)


class AccountStatus(StrEnum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    DONE = "done"
    FAILED = "failed"


class MailType(StrEnum):
    OUTLOOK = "outlook"
    LINK = "link"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class OutlookAccount(TimestampMixin, Base):
    __tablename__ = "outlook_accounts"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    password: Mapped[str | None] = mapped_column(EncryptedText())
    client_id: Mapped[str | None] = mapped_column(EncryptedText())
    refresh_token: Mapped[str | None] = mapped_column(EncryptedText())
    mail_type: Mapped[MailType] = mapped_column(
        enum_type(MailType, "mail_type"), default=MailType.OUTLOOK, nullable=False
    )
    mail_url: Mapped[str | None] = mapped_column(EncryptedText())
    status: Mapped[AccountStatus] = mapped_column(
        enum_type(AccountStatus, "account_status"),
        default=AccountStatus.AVAILABLE,
        index=True,
        nullable=False,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class RegistrationRun(TimestampMixin, Base):
    __tablename__ = "registration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    status: Mapped[RunStatus] = mapped_column(
        enum_type(RunStatus, "registration_run_status"),
        default=RunStatus.QUEUED,
        index=True,
        nullable=False,
    )
    error_category: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[JsonObject] = mapped_column(
        EncryptedJSON(), default=dict, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Credential(TimestampMixin, Base):
    __tablename__ = "credentials"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    password: Mapped[str | None] = mapped_column(EncryptedText())
    access_token: Mapped[str | None] = mapped_column(EncryptedText())
    session_token: Mapped[str | None] = mapped_column(EncryptedText())
    refresh_token: Mapped[str | None] = mapped_column(EncryptedText())
    id_token: Mapped[str | None] = mapped_column(EncryptedText())
    device_id: Mapped[str | None] = mapped_column(EncryptedText())
    cookie_header: Mapped[str | None] = mapped_column(EncryptedText())
    totp_secret: Mapped[str | None] = mapped_column(EncryptedText())
    metadata_json: Mapped[JsonObject] = json_object_column()
