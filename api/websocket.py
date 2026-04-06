from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..services.broadcast import BroadcastHub
from ..services.controller import ARXControllerService
from ..services.session import SessionService
from .admin import _admin_status, _monitor_state
from .deps import get_broadcast, get_controller_service, get_session_service

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/monitor")
async def ws_monitor(
    ws: WebSocket,
    hub: BroadcastHub = Depends(get_broadcast),
    session: SessionService = Depends(get_session_service),
) -> None:
    await ws.accept()
    await hub.monitor.add(ws)
    try:
        snap = session.snapshot()
        await ws.send_text(json.dumps(
            {"type": "system_state", **_monitor_state(snap)},
            ensure_ascii=False,
        ))
        while True:
            await ws.receive_text()  
    except WebSocketDisconnect:
        pass
    finally:
        await hub.monitor.remove(ws)


@router.websocket("/ws/admin")
async def ws_admin(
    ws: WebSocket,
    hub: BroadcastHub = Depends(get_broadcast),
    session: SessionService = Depends(get_session_service),
    controller: ARXControllerService = Depends(get_controller_service),
) -> None:
    await ws.accept()
    await hub.admin.add(ws)
    try:
        await ws.send_text(json.dumps(
            _admin_status(session.snapshot(), controller),
            ensure_ascii=False,
            default=str,
        ))
        while True:
            raw = await ws.receive_text()
            try:
                cmd = json.loads(raw)
            except json.JSONDecodeError:
                continue
            action = cmd.get("action")
            if action == "set_target":
                try:
                    session.set_target(float(cmd.get("value", 8000.0)))
                except (TypeError, ValueError):
                    continue
    except WebSocketDisconnect:
        pass
    finally:
        await hub.admin.remove(ws)