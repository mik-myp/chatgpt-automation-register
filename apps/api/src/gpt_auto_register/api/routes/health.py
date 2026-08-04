from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.core.config import get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    version: str


@router.get("/health", response_model=HealthResponse)
def health(db: DatabaseSession) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok", version=get_settings().app_version)
