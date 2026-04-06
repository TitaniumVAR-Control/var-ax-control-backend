from __future__ import annotations

import asyncio
import logging
from datetime import date as date_cls, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..schemas import (
    DataFilesResponse,
    ManualInputRequest,
    ManualInputResponse,
    SetTargetRequest,
    SimpleMessageResponse,
    StartWorkRequest,
    StatusResponse,
)
from ..services.broadcast import BroadcastHub
from ..services.controller import ARXControllerService
from ..services.data_source import CsvSourceCatalog
from ..services.export import DailyExportService
from ..services.runner import make_preview_point
from ..services.session import SessionService
from .deps import (
    AppContext,
    get_broadcast,
    get_catalog,
    get_context,
    get_controller_service,
    get_export_service,
    get_session_service,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# 조회

@router.get("/status", response_model=StatusResponse)
async def get_status(
    session: SessionService = Depends(get_session_service),
    controller: ARXControllerService = Depends(get_controller_service),
) -> StatusResponse:
    snap = session.snapshot()
    return StatusResponse(
        model_loaded=controller.loaded,
        power_on=snap.power_on,
        simulation_running=snap.simulation_running,
        work_id=snap.work_id,
        selected_file=snap.selected_file,
        started_at=snap.started_at,
        elapsed_time=snap.elapsed_time,
        total_rows=snap.total_rows,
        current_index=snap.current_index,
        target_current=snap.target_current,
        preview_point=snap.preview_point,
    )


@router.get("/data-files", response_model=DataFilesResponse)
async def list_data_files(catalog: CsvSourceCatalog = Depends(get_catalog)) -> DataFilesResponse:
    return DataFilesResponse(files=catalog.list_files())


# 전원 / 시뮬레이션 제어

@router.post("/power-on", response_model=SimpleMessageResponse)
async def power_on(
    req: StartWorkRequest,
    ctx: AppContext = Depends(get_context),
) -> SimpleMessageResponse:
    if ctx.session_service.snapshot().simulation_running:
        raise HTTPException(status_code=400, detail="Stop simulation before changing power state")
    try:
        source = ctx.catalog.open(req.data_file or ctx.session_service.snapshot().selected_file or None)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {exc}") from exc

    preview = make_preview_point(source, req.target_current)
    await ctx.session_service.power_on(source, req.target_current, preview)
    ctx.controller_service.reset()

    snap = ctx.session_service.snapshot()
    await ctx.broadcast.monitor.broadcast({"type": "system_state", **_monitor_state(snap)})
    await ctx.broadcast.admin.broadcast(_admin_status(snap, ctx.controller_service))

    log.info("Power on: %s (%d rows)", source.source_name(), source.total())
    return SimpleMessageResponse(
        message="Power on",
        file=source.source_name(),
        total_rows=source.total(),
        preview_voltage=preview.get("voltage"),
    )


@router.post("/power-off", response_model=SimpleMessageResponse)
async def power_off(ctx: AppContext = Depends(get_context)) -> SimpleMessageResponse:
    task = await ctx.session_service.power_off()
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    ctx.controller_service.reset()

    snap = ctx.session_service.snapshot()
    await ctx.broadcast.monitor.broadcast({"type": "system_state", **_monitor_state(snap)})
    await ctx.broadcast.admin.broadcast(_admin_status(snap, ctx.controller_service))
    return SimpleMessageResponse(message="Power off")


@router.post("/start", response_model=SimpleMessageResponse)
async def start_simulation(
    req: StartWorkRequest,
    ctx: AppContext = Depends(get_context),
) -> SimpleMessageResponse:
    session = ctx.session_service
    snap = session.snapshot()
    if snap.simulation_running:
        raise HTTPException(status_code=400, detail="Simulation already running")
    if not snap.power_on or session.state.source is None:
        raise HTTPException(status_code=400, detail="Power on first")

    if req.data_file and req.data_file != snap.selected_file:
        try:
            new_source = ctx.catalog.open(req.data_file)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"File not found: {exc}") from exc
        preview = make_preview_point(new_source, req.target_current)
        await session.power_on(new_source, req.target_current, preview)

    ctx.controller_service.reset()
    db_session_id = await ctx.repository.start_session(
        work_id=session.snapshot().work_id,
        source_file=session.snapshot().selected_file,
        target_current=req.target_current,
    )
    await session.mark_running(req.target_current, db_session_id)

    runner = ctx.build_runner()
    task = asyncio.create_task(runner.run(), name="sim-runner")
    session.set_sim_task(task)

    snap = session.snapshot()
    await ctx.broadcast.monitor.broadcast({"type": "system_state", **_monitor_state(snap)})
    await ctx.broadcast.admin.broadcast(_admin_status(snap, ctx.controller_service))

    log.info("Simulation started: %s", snap.selected_file)
    return SimpleMessageResponse(
        message="Simulation started",
        file=snap.selected_file,
        total_rows=snap.total_rows,
    )


@router.post("/stop", response_model=SimpleMessageResponse)
async def stop_simulation(ctx: AppContext = Depends(get_context)) -> SimpleMessageResponse:
    task = await ctx.session_service.mark_stopped(reset_preview=True)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    ctx.controller_service.reset()

    snap = ctx.session_service.snapshot()
    await ctx.broadcast.monitor.broadcast({"type": "system_state", **_monitor_state(snap)})
    await ctx.broadcast.admin.broadcast(_admin_status(snap, ctx.controller_service))
    return SimpleMessageResponse(message="Simulation stopped")


@router.post("/reload-model")
async def reload_model(controller: ARXControllerService = Depends(get_controller_service)) -> dict:
    return {"success": controller.load()}


@router.post("/set-target")
async def set_target(
    req: SetTargetRequest,
    session: SessionService = Depends(get_session_service),
) -> dict:
    session.set_target(req.target_current)
    log.info("Target current set to %s", req.target_current)
    return {"target_current": req.target_current}


@router.post("/manual-input", response_model=ManualInputResponse)
async def manual_input(
    req: ManualInputRequest,
    controller: ARXControllerService = Depends(get_controller_service),
    broadcast: BroadcastHub = Depends(get_broadcast),
) -> ManualInputResponse:
    if not controller.loaded or controller.controller is None:
        raise HTTPException(status_code=400, detail="Model not loaded")
    ctrl = controller.controller
    ctrl.update(current=req.current, speed=req.speed, vacuum=req.vacuum, voltage=req.voltage)
    recommended = ctrl.compute_speed(req.target_current)
    predicted = ctrl.predict_current()
    error = req.target_current - req.current if recommended is not None else None

    await broadcast.monitor.broadcast({
        "type": "sensor",
        "timestamp": "",
        "current": req.current,
        "vacuum": req.vacuum,
        "voltage": req.voltage,
        "descentSpeed": req.speed,
        "elapsedTime": 0,
        "recommended_speed": recommended,
        "predicted_current": predicted,
        "target_current": req.target_current,
        "current_error": error,
        "buffer_filled": ctrl.buffer_ready,
        "current_index": 0,
        "total_rows": 0,
    })

    return ManualInputResponse(
        recommended_speed=recommended,
        predicted_current=predicted,
        target_current=req.target_current,
        current_error=error,
        buffer_filled=ctrl.buffer_ready,
        buffer_count=ctrl.buffer_count,
    )


# 일별 데이터 내보내기

@router.get("/export/daily")
async def export_daily(
    day: str | None = Query(None, description="YYYY-MM-DD, 미지정 시 오늘"),
    export: DailyExportService = Depends(get_export_service),
) -> StreamingResponse:
    try:
        target_day = date_cls.fromisoformat(day) if day else datetime.utcnow().date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}") from exc

    filename = f"sensor_log_{target_day.isoformat()}.csv"
    return StreamingResponse(
        export.stream_csv(target_day),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# 내부 payload 빌더

def _monitor_state(snap) -> dict:
    return {
        "power_on": snap.power_on,
        "simulation_running": snap.simulation_running,
        "work_id": snap.work_id,
        "selected_file": snap.selected_file,
        "started_at": snap.started_at,
        "elapsed_time": snap.elapsed_time,
        "current_index": snap.current_index,
        "total_rows": snap.total_rows,
        "target_current": snap.target_current,
        "preview_point": snap.preview_point,
    }


def _admin_status(snap, controller: ARXControllerService) -> dict:
    base = {
        "type": "status",
        "power_on": snap.power_on,
        "simulation_running": snap.simulation_running,
        "work_id": snap.work_id,
        "selected_file": snap.selected_file,
        "started_at": snap.started_at,
        "elapsed_time": snap.elapsed_time,
        "current_index": snap.current_index,
        "total_rows": snap.total_rows,
        "target_current": snap.target_current,
        "buffer_filled": controller.buffer_ready,
        "buffer_count": controller.buffer_count,
    }
    if snap.preview_point:
        base.update({
            "current": snap.preview_point.get("current", 0.0),
            "vacuum": snap.preview_point.get("vacuum", 0.0),
            "voltage": snap.preview_point.get("voltage", 0.0),
            "actual_speed": snap.preview_point.get("descentSpeed", 0.0),
            "recommended_speed": snap.preview_point.get("recommended_speed"),
            "predicted_current": snap.preview_point.get("predicted_current"),
            "current_error": snap.preview_point.get("current_error"),
        })
    return base