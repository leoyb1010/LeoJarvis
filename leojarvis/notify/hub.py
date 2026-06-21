from __future__ import annotations

import json
from fastapi import WebSocket


class NotifyHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def push(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def push_event(self, payload: dict) -> dict:
        """带每日打断预算的推送：紧急或当天未超额 → 即时推送并计数；超额的非紧急通知
        仍然推送但标记 delivery=digest（前端可安静展示、不弹打断式 toast），避免丢事件。"""
        from . import budget
        verdict = budget.classify(payload)
        if verdict["interrupt"]:
            await self.push(payload)
            if not verdict["urgent"]:
                budget.record()
        else:
            await self.push({**payload, "delivery": "digest"})
        return verdict


hub = NotifyHub()
