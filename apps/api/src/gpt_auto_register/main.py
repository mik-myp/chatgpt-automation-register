from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gpt_auto_register.api.router import api_router
from gpt_auto_register.core.config import get_settings
from gpt_auto_register.worker import WorkerManager

worker_manager = WorkerManager()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_runtime_directories()
    worker_manager.start()
    try:
        yield
    finally:
        worker_manager.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix="/api")
    return application


app = create_app()
