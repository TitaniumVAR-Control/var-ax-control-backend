from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import settings
from .broadcast import BroadcastHub
from .controller import ARXControllerService
from .data_source import CsvReplaySource, SensorFrame
from .repository import ISensorRepository, SensorRecord
from .session import SessionService

log = logging.getLogger(__name__)


def make_preview_point(source: CsvReplaySource, target_current: float) -> dict[str, Any]:
    #power_on 직후 / stop 이후 모니터에 보낼 프리뷰.
    frame = source.read(0) if source.total() > 0 else SensorFrame("", 0, 0, 0, 0)
    return {
        "timestamp": "",
        "current": 0.0,
        "vacuum": 0.0,
        "voltage": frame.voltage,
        "descentSpeed": 0.0,
        "elapsedTime": 0,
        "recommended_speed": None,
        "predicted_current": None,
        "target_current": target_current,
        "current_error": None,
        "buffer_filled": False,
        "current_index": 0,
        "total_rows": source.total(),
    }


class SimulationRunner:
    def __init__(
        self,
        session_service: SessionService,
        controller_service: ARXControllerService,
        broadcast: BroadcastHub,
        repository: ISensorRepository,
    ) -> None:
        self._session = session_service
        self._controller = controller_service
        self._broadcast = broadcast
        self._repo = repository

    async def run(self) -> None:
        source = self._session.state.source
        if source is None:
            log.warning("run() called without source")
            return

        ctrl_svc = self._controller
        ctrl = ctrl_svc.controller
        seed_steps = ctrl_svc.seed_steps
        snapshot = self._session.snapshot()
        target_current = snapshot.target_current
        db_session_id = snapshot.db_session_id
        work_id = snapshot.work_id
        total = source.total()
        tick = settings.tick_interval_sec

        try:
            for idx in range(total):
                if not self._session.snapshot().simulation_running:
                    break

                frame = source.read(idx)
                # 동적으로 target 변경 반영
                target_current = self._session.snapshot().target_current

                recommended_speed: float | None = None
                predicted_current: float | None = None
                applied_speed = frame.speed
                current_value = frame.current
                phase = "Warmup"

                if ctrl is not None:
                    if idx < seed_steps:
                        # 시드 구간: 실측을 그대로 주입
                        ctrl.update(
                            current=current_value,
                            speed=applied_speed,
                            vacuum=frame.vacuum,
                            voltage=frame.voltage,
                        )
                        if ctrl.buffer_ready:
                            predicted_current = ctrl.predict_current()
                            recommended_speed = ctrl.compute_speed(target_current)
                        phase = ctrl.phase
                    else:
                        # 폐루프: 추천 속도로 다음 전류 예측 후 버퍼 갱신
                        recommended_speed = ctrl.compute_speed(target_current)
                        if recommended_speed is not None:
                            applied_speed = recommended_speed
                        predicted_current = ctrl.predict_next_current_for_speed(
                            speed=applied_speed,
                            vacuum=frame.vacuum,
                            voltage=frame.voltage,
                        )
                        if predicted_current is not None:
                            current_value = predicted_current
                        ctrl.update(
                            current=current_value,
                            speed=applied_speed,
                            vacuum=frame.vacuum,
                            voltage=frame.voltage,
                        )
                        phase = ctrl.phase

                current_error = (
                    target_current - current_value if recommended_speed is not None else None
                )
                buffer_ready = ctrl_svc.buffer_ready

                monitor_payload = {
                    "type": "sensor",
                    "timestamp": frame.timestamp,
                    "current": current_value,
                    "vacuum": frame.vacuum,
                    "voltage": frame.voltage,
                    "descentSpeed": applied_speed,
                    "elapsedTime": idx,
                    "recommended_speed": recommended_speed,
                    "predicted_current": predicted_current,
                    "target_current": target_current,
                    "current_error": current_error,
                    "buffer_filled": buffer_ready,
                    "current_index": idx + 1,
                    "total_rows": total,
                }

                admin_payload = {
                    "type": "status",
                    "power_on": True,
                    "simulation_running": True,
                    "work_id": work_id,
                    "selected_file": source.source_name(),
                    "started_at": self._session.snapshot().started_at,
                    "elapsed_time": idx,
                    "current_index": idx,
                    "total_rows": total,
                    "current": current_value,
                    "vacuum": frame.vacuum,
                    "voltage": frame.voltage,
                    "actual_speed": applied_speed,
                    "recommended_speed": recommended_speed,
                    "predicted_current": predicted_current,
                    "target_current": target_current,
                    "current_error": current_error,
                    "buffer_filled": buffer_ready,
                    "buffer_count": ctrl_svc.buffer_count,
                }

                await self._session.update_tick(idx, monitor_payload)
                await self._broadcast.monitor.broadcast(monitor_payload)
                await self._broadcast.admin.broadcast(admin_payload)

                await self._repo.append(
                    db_session_id,
                    SensorRecord(
                        work_id=work_id,
                        sim_time_sec=idx,
                        power_on=True,
                        voltage=frame.voltage,
                        current=current_value,
                        vacuum=frame.vacuum,
                        speed_actual=applied_speed,
                        speed_recommended=recommended_speed,
                        current_target=target_current,
                        current_predicted=predicted_current,
                        position=frame.position,
                        temperature=frame.temperature,
                        image_filename=frame.image_filename,
                        phase=phase,
                        buffer_ready=buffer_ready,
                    ),
                )

                await asyncio.sleep(tick)

            await self._repo.end_session(db_session_id, total)
            await self._broadcast.admin.broadcast({"type": "finished", "work_id": work_id})
            log.info("Simulation finished: %s", work_id)

        except asyncio.CancelledError:
            await self._repo.end_session(db_session_id, self._session.snapshot().current_index)
            log.info("Simulation cancelled")
            raise
        except Exception:
            log.exception("Simulation loop crashed")
            raise