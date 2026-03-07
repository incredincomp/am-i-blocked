"""FastAPI application factory for am-i-blocked."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from am_i_blocked_core.config import get_settings
from am_i_blocked_core.logging_helpers import configure_logging, get_logger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import api_router, ui_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger.info("am-i-blocked API starting", log_level=settings.log_level)
    yield
    logger.info("am-i-blocked API shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title="Am I Blocked?",
        description="Network self-diagnosis and routing assistant",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ui_router)

    import os
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


app = create_app()
