import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.encryption import ensure_master_key
from gpt_auto_register.core.security import random_token
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.auth import SetupState
from gpt_auto_register.db.session import SessionLocal

logger = logging.getLogger(__name__)


@asynccontextmanager
async def application_lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_runtime_directories()
    authentication_enabled = bool(
        settings.authentication_enabled
        and getattr(application.state, "authentication_enabled", True)
    )
    initialized = False
    if authentication_enabled:
        with SessionLocal() as session:
            ensure_master_key(session)
            state = session.get(SetupState, 1)
            initialized = bool(state and state.initialized)
    if authentication_enabled and not initialized:
        token = random_token()
        expires_at = utc_now() + timedelta(minutes=settings.setup_token_minutes)
        application.state.setup_token = token
        application.state.setup_token_expires_at = expires_at
        logger.warning(
            "First-time setup token (expires %s): %s",
            expires_at.isoformat(),
            token,
        )
    else:
        application.state.setup_token = ""
        application.state.setup_token_expires_at = None
    yield
