from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .data_source import CsvReplaySource


@dataclass
class SessionSnapshot:
    power_on: bool = False
    simulation_running: bool = False
    work_id: str = ""
    selected_file: str = ""
    started_at: str | None = None
    elapsed_time: int = 0
    current_index: int = 0
    total_rows: int = 0
    target_current: float = 8000.0
    preview_point: dict[str, Any] | None = None
    db_session_id: int | None = None


@dataclass
class SessionState:
    snapshot: SessionSnapshot = field(default_factory=SessionSnapshot)
    source: CsvReplaySource | None = None
    sim_task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionService:

    def __init__(self) -> None:
        self.state = SessionState()

    #  조회 

    def snapshot(self) -> SessionSnapshot:
        return self.state.snapshot

    #  변경 

    async def power_on(
        self,
        source: CsvReplaySource,
        target_current: float,
        preview_point: dict[str, Any],
    ) -> None:
        async with self.state.lock:
            self.state.source = source
            self.state.snapshot = SessionSnapshot(
                power_on=True,
                simulation_running=False,
                work_id=source.session_id(),
                selected_file=source.source_name(),
                started_at=None,
                elapsed_time=0,
                current_index=0,
                total_rows=source.total(),
                target_current=target_current,
                preview_point=preview_point,
            )

    async def power_off(self) -> asyncio.Task | None:
        async with self.state.lock:
            task = self.state.sim_task
            self.state.sim_task = None
            self.state.source = None
            self.state.snapshot = SessionSnapshot()
            return task

    async def mark_running(self, target_current: float, db_session_id: int | None) -> None:
        async with self.state.lock:
            snap = self.state.snapshot
            snap.simulation_running = True
            snap.started_at = datetime.now().isoformat(timespec="seconds")
            snap.elapsed_time = 0
            snap.current_index = 0
            snap.target_current = target_current
            snap.db_session_id = db_session_id

    async def mark_stopped(self, reset_preview: bool = True) -> asyncio.Task | None:
        async with self.state.lock:
            snap = self.state.snapshot
            snap.simulation_running = False
            snap.started_at = None
            snap.elapsed_time = 0
            snap.current_index = 0
            snap.db_session_id = None
            if reset_preview and self.state.source is not None:
                # preview 는 power_on 유지 시 첫 행으로 복원
                from .runner import make_preview_point  # 순환 import 회피
                snap.preview_point = make_preview_point(self.state.source, snap.target_current)
            task = self.state.sim_task
            self.state.sim_task = None
            return task

    async def update_tick(self, index: int, preview_point: dict[str, Any]) -> None:
        async with self.state.lock:
            snap = self.state.snapshot
            snap.current_index = index
            snap.elapsed_time = index
            snap.preview_point = preview_point

    def set_sim_task(self, task: asyncio.Task) -> None:
        self.state.sim_task = task

    def set_target(self, target_current: float) -> None:
        self.state.snapshot.target_current = target_current