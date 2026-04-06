from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from .models import Base

log = logging.getLogger(__name__)


class Database:
    #실패 시 비활성 상태로 유지

    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.enabled: bool = False

    async def connect(self) -> None:
        if not settings.database_enabled:
            log.info("Database disabled by configuration")
            return
        try:
            self.engine = create_async_engine(
                settings.database_url,
                echo=settings.db_echo,
                pool_pre_ping=True,
            )
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
            self.enabled = True
            log.info("Database connected: %s", _mask_url(settings.database_url))
        except Exception as exc:
            log.warning("Database connection failed, falling back to NullRepository: %s", exc)
            self.engine = None
            self.session_factory = None
            self.enabled = False

    async def disconnect(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.enabled = False


def _mask_url(url: str) -> str:
    if "@" not in url:
        return url
    head, tail = url.split("@", 1)
    if "://" in head and ":" in head.split("://", 1)[1]:
        scheme, rest = head.split("://", 1)
        user = rest.split(":", 1)[0]
        return f"{scheme}://{user}:***@{tail}"
    return url