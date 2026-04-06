from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── 요청 ──────────────────────────────────────────────

class StartWorkRequest(BaseModel):
    data_file: str | None = None
    target_current: float = 8000.0


class SetTargetRequest(BaseModel):
    target_current: float


class ManualInputRequest(BaseModel):
    current: float
    vacuum: float
    voltage: float = 0.0
    speed: float = 0.0
    target_current: float = 8000.0


# ── 응답 ──────────────────────────────────────────────

class StatusResponse(BaseModel):
    model_loaded: bool
    power_on: bool
    simulation_running: bool
    work_id: str
    selected_file: str
    started_at: str | None
    elapsed_time: int
    total_rows: int
    current_index: int
    target_current: float
    preview_point: dict[str, Any] | None


class DataFilesResponse(BaseModel):
    files: list[str]


class SimpleMessageResponse(BaseModel):
    message: str
    file: str | None = None
    total_rows: int | None = None
    preview_voltage: float | None = None


class ManualInputResponse(BaseModel):
    recommended_speed: float | None
    predicted_current: float | None
    target_current: float
    current_error: float | None
    buffer_filled: bool
    buffer_count: int