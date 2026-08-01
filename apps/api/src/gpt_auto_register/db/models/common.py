from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column

from gpt_auto_register.db.base import utc_now


def new_id() -> str:
    return str(uuid4())


def enum_type(enum_class: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        values_callable=lambda values: [value.value for value in values],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


JsonObject = dict[str, Any]


def json_object_column() -> MappedColumn[JsonObject]:
    return mapped_column(JSON, default=dict, nullable=False)
