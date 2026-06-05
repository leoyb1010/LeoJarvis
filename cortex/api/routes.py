from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .. import db
from ..agent.loop import approve_action, run_agent
from ..agent.tools import TOOLBUS
from ..briefing.builder import build_today
from ..notify.hub import hub
from ..scheduler import run_ingest_cycle

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "ts": int(time.time()), "service": "cortex"}


# ---------- Agent 中枢 ----------

class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/agent/chat")
def agent_chat(req: ChatRequest) -> dict:
    return run_agent([m.model_dump() for m in req.messages])


class ApproveRequest(BaseModel):
    id: str
    decision: str = Field(pattern="^(approve|reject)$")


@router.post("/agent/approve")
def agent_approve(req: ApproveRequest) -> dict:
    return approve_action(req.id, req.decision)


@router.get("/agent/tools")
def agent_tools() -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in TOOLBUS.all()]


# ---------- 能力模块（只读，供仪表盘瓷砖直接取数，无需 LLM）----------

@router.get("/system/status")
def system_status() -> dict:
    from ..agent import sysinfo
    return {"raw": sysinfo.system_status(), "hotspots": None}


@router.get("/services")
def services_status() -> list[dict]:
    from ..agent import services
    return services.status_all()


@router.get("/agents")
def agents_list() -> list[dict]:
    from ..agent import agents_ctrl
    return agents_ctrl.list_agents()


class JournalEntry(BaseModel):
    text: str


@router.get("/journal")
def journal_list(q: str = "") -> list[dict]:
    from ..agent import journal
    return journal.search_entries(q) if q else journal.list_entries()


@router.post("/journal")
def journal_add(entry: JournalEntry) -> dict:
    from ..agent import journal
    eid = journal.add_entry(entry.text.strip())
    return {"ok": bool(eid), "id": eid}


@router.post("/ingest/run")
async def ingest_run() -> dict:
    return await run_ingest_cycle()


@router.get("/briefing/today")
def briefing_today() -> dict:
    return build_today()


class Feedback(BaseModel):
    event_id: str
    signal: str = Field(pattern="^(important|useless)$")


@router.post("/feedback")
def feedback(fb: Feedback) -> dict:
    ts = db.now_ms()
    with db.conn() as c:
        c.execute("INSERT INTO feedback(id,event_id,ts,signal) VALUES(?,?,?,?)",
                  (uuid.uuid4().hex, fb.event_id, ts, fb.signal))
        row = c.execute("SELECT title FROM events WHERE id=?", (fb.event_id,)).fetchone()
    if row:
        statement = f"Leo 认为类似『{row['title']}』的信息{'很重要' if fb.signal == 'important' else '没用'}"
        db.insert_memory(statement, subject=row["title"],
                         confidence=0.85, salience=0.9 if fb.signal == "important" else 0.25,
                         source_events=[fb.event_id])
    return {"ok": True}


@router.get("/events")
def events(hours: int = 24) -> list[dict]:
    since = int((time.time() - hours * 3600) * 1000)
    return [dict(r) for r in db.query_events(since)]


@router.get("/memories")
def memories(limit: int = 100) -> list[dict]:
    return [dict(r) for r in db.list_memories(limit)]


@router.post("/memory/reflect")
def memory_reflect(hours: int = 24) -> dict:
    from ..memory.reflect import reflect
    return reflect(hours=hours)


@router.websocket("/ws/notify")
async def ws_notify(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
