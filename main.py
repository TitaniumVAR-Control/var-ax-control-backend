from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.admin import router as admin_router
from .api.deps import AppContext
from .api.websocket import router as ws_router
from .config import settings


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def create_app() -> FastAPI:
    _configure_logging()
    ctx = AppContext()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await ctx.startup()
        app.state.ctx = ctx
        try:
            yield
        finally:
            await ctx.shutdown()

    app = FastAPI(title="VAR Monitoring Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(admin_router)
    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "model_loaded": ctx.controller_service.loaded,
            "db_enabled": ctx.database.enabled,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )