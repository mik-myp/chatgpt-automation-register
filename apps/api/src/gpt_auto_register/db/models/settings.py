from typing import Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from gpt_auto_register.db.base import Base
from gpt_auto_register.db.models.common import TimestampMixin


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
