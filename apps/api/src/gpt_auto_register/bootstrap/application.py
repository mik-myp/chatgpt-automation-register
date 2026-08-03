from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gpt_auto_register.api.router import api_router
from gpt_auto_register.bootstrap.lifecycle import application_lifespan
from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.local_access import TrustedAccessMiddleware
from gpt_auto_register.db.session import SessionLocal


def create_app(
    *,
    authentication_enabled: bool | None = None,
    worker_enabled: bool | None = None,
) -> FastAPI:
    # worker_enabled remains accepted for compatibility; API and Worker are now separate processes.
    del worker_enabled
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=application_lifespan,
    )
    application.state.authentication_enabled = (
        settings.authentication_enabled
        if authentication_enabled is None
        else authentication_enabled
    )
    application.state.session_factory = SessionLocal
    application.add_middleware(TrustedAccessMiddleware)
    if settings.environment != "production":
        application.add_middleware(
            CORSMiddleware,
            allow_origins=sorted(settings.trusted_origin_set),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["Accept", "Content-Type", "X-CSRF-Token", "X-Reauth-Password"],
        )
    application.include_router(api_router, prefix="/api")
    if settings.frontend_dist_path.is_dir():
        assets_path = settings.frontend_dist_path / "assets"
        if assets_path.is_dir():
            application.mount("/assets", StaticFiles(directory=assets_path), name="assets")

        @application.get("/{path:path}", include_in_schema=False)
        def serve_spa(path: str) -> FileResponse:
            root = settings.frontend_dist_path.resolve()
            requested = (root / path).resolve()
            if requested.is_relative_to(root) and requested.is_file():
                return FileResponse(requested)
            return FileResponse(root / "index.html")

    return application
