from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class Channel:
    def __init__(self, name: str) -> None:
        self._name = name
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)
        log.info("[%s] client connected (total=%d)", self._name, len(self._clients))

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("[%s] client disconnected (total=%d)", self._name, len(self._clients))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if not self._clients:
            return
        message = json.dumps(payload, ensure_ascii=False, default=str)
        dead: list[WebSocket] = []
        # 스냅샷 복사로 순회 중 변경 방지
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


class BroadcastHub:
    def __init__(self) -> None:
        self.monitor = Channel("monitor")
        self.admin = Channel("admin")