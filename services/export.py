from __future__ import annotations

import csv
import io
from datetime import date
from typing import AsyncIterator

from .repository import ISensorRepository


CSV_HEADERS = [
    "recorded_at", "work_id", "sim_time_sec", "power_on",
    "voltage", "current", "vacuum",
    "speed_actual", "speed_recommended",
    "current_target", "current_predicted",
    "position", "temperature", "image_filename",
    "phase", "buffer_ready",
]


class DailyExportService:
    def __init__(self, repository: ISensorRepository) -> None:
        self._repo = repository

    async def stream_csv(self, day: date) -> AsyncIterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_HEADERS)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        async for row in self._repo.iter_daily(day):
            writer.writerow([
                row.recorded_at.isoformat() if row.recorded_at else "",
                row.work_id,
                row.sim_time_sec,
                int(row.power_on),
                row.voltage,
                row.current,
                row.vacuum,
                row.speed_actual,
                row.speed_recommended if row.speed_recommended is not None else "",
                row.current_target,
                row.current_predicted if row.current_predicted is not None else "",
                row.position if row.position is not None else "",
                row.temperature if row.temperature is not None else "",
                row.image_filename or "",
                row.phase,
                int(row.buffer_ready),
            ])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)