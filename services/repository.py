from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import AsyncIterator

from sqlalchemy import select

from ..db.engine import Database
from ..db.models import SensorLog, WorkSession

log = logging.getLogger(__name__)


@dataclass
class SensorRecord:
    work_id: str
    sim_time_sec: int
    power_on: bool
    voltage: float
    current: float
    vacuum: float
    speed_actual: float
    speed_recommended: float | None
    current_target: float
    current_predicted: float | None
    position: float | None
    temperature: float | None
    image_filename: str | None
    phase: str
    buffer_ready: bool


class ISensorRepository(ABC):
    @abstractmethod
    async def start_session(self, work_id: str, source_file: str, target_current: float) -> int | None: ...

    @abstractmethod
    async def end_session(self, session_id: int | None, total_rows: int) -> None: ...

    @abstractmethod
    async def append(self, session_id: int | None, record: SensorRecord) -> None: ...

    @abstractmethod
    async def iter_daily(self, day: date) -> AsyncIterator[SensorLog]: ...


class NullSensorRepository(ISensorRepository):
    #DB 비활성 시 fallback. 모든 쓰기 작업은 무시

    async def start_session(self, work_id: str, source_file: str, target_current: float) -> int | None:
        return None

    async def end_session(self, session_id: int | None, total_rows: int) -> None:
        return None

    async def append(self, session_id: int | None, record: SensorRecord) -> None:
        return None

    async def iter_daily(self, day: date) -> AsyncIterator[SensorLog]:
        if False:
            yield  # type: ignore[unreachable]


class PostgresSensorRepository(ISensorRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def start_session(self, work_id: str, source_file: str, target_current: float) -> int | None:
        if not self._db.enabled or self._db.session_factory is None:
            return None
        try:
            async with self._db.session_factory() as session:
                ws = WorkSession(
                    work_id=work_id,
                    source_file=source_file,
                    target_current=target_current,
                    started_at=datetime.utcnow(),
                )
                session.add(ws)
                await session.commit()
                await session.refresh(ws)
                return ws.id
        except Exception as exc:
            log.warning("start_session failed: %s", exc)
            return None

    async def end_session(self, session_id: int | None, total_rows: int) -> None:
        if session_id is None or not self._db.enabled or self._db.session_factory is None:
            return
        try:
            async with self._db.session_factory() as session:
                ws = await session.get(WorkSession, session_id)
                if ws is not None:
                    ws.ended_at = datetime.utcnow()
                    ws.total_rows = total_rows
                    await session.commit()
        except Exception as exc:
            log.warning("end_session failed: %s", exc)

    async def append(self, session_id: int | None, record: SensorRecord) -> None:
        if not self._db.enabled or self._db.session_factory is None:
            return
        try:
            async with self._db.session_factory() as session:
                row = SensorLog(
                    session_id=session_id,
                    work_id=record.work_id,
                    recorded_at=datetime.utcnow(),
                    sim_time_sec=record.sim_time_sec,
                    power_on=record.power_on,
                    voltage=record.voltage,
                    current=record.current,
                    vacuum=record.vacuum,
                    speed_actual=record.speed_actual,
                    speed_recommended=record.speed_recommended,
                    current_target=record.current_target,
                    current_predicted=record.current_predicted,
                    position=record.position,
                    temperature=record.temperature,
                    image_filename=record.image_filename,
                    phase=record.phase,
                    buffer_ready=record.buffer_ready,
                )
                session.add(row)
                await session.commit()
        except Exception as exc:
            log.warning("append failed: %s", exc)

    async def iter_daily(self, day: date) -> AsyncIterator[SensorLog]:
        if not self._db.enabled or self._db.session_factory is None:
            return
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        async with self._db.session_factory() as session:
            stmt = (
                select(SensorLog)
                .where(SensorLog.recorded_at >= start, SensorLog.recorded_at < end)
                .order_by(SensorLog.recorded_at.asc(), SensorLog.id.asc())
                .execution_options(yield_per=500)
            )
            result = await session.stream(stmt)
            async for row in result.scalars():
                yield row


def build_repository(database: Database) -> ISensorRepository:
    if database.enabled:
        return PostgresSensorRepository(database)
    log.info("Using NullSensorRepository (DB unavailable)")
    return NullSensorRepository()