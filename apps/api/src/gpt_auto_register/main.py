from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gpt_auto_register.api.router import api_router
from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.local_access import LocalAccessMiddleware
from gpt_auto_register.worker import WorkerManager

worker_manager = WorkerManager()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_runtime_directories()
    worker_enabled = bool(getattr(application.state, "worker_enabled", True))
    if worker_enabled:
        worker_manager.start()
    try:
        yield
    finally:
        if worker_enabled:
            worker_manager.stop()


def create_app(*, worker_enabled: bool = True) -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.state.worker_enabled = worker_enabled
    application.add_middleware(LocalAccessMiddleware)
    application.include_router(api_router, prefix="/api")
    return application


app = create_app()
