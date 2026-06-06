from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .. import db, user_settings
from ..agent.loop import approve_action, run_agent
from ..agent.tools import TOOLBUS
from ..briefing.builder import build_today
from ..notify.hub import hub
from ..scheduler import run_ingest_cycle

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "ts": int(time.time()), "service": "leojarvis"}


class DeviceHeartbeatIn(BaseModel):
    device_id: str
    device_name: str = ""
    host_name: str = ""
    model: str = ""
    role: str = "mac"
    generated_at: int | None = None
    last_seen_ts: int | None = None
    health: int | float = 0
    status: str = "未知"
    metrics: dict = Field(default_factory=dict)
    modules: dict = Field(default_factory=dict)
    services: dict = Field(default_factory=dict)
    risks: list[dict] = Field(default_factory=list)
    privacy: str = ""


class RemoteDeviceIn(BaseModel):
    host: str
    name: str = ""
    user: str = ""
    port: int = 22
    enabled: bool = True


class RemoteLeoJarvisIn(BaseModel):
    name: str = ""
    host: str
    user: str = ""
    ssh_port: int = 22
    remote_port: int = 8787
    local_port: int | None = None
    enabled: bool = True


class SettingsIn(BaseModel):
    settings: dict = Field(default_factory=dict)


@router.get("/settings")
def get_settings() -> dict:
    return user_settings.load()


@router.patch("/settings")
def patch_settings(req: SettingsIn) -> dict:
    return user_settings.patch(req.settings)


class OpmlImportIn(BaseModel):
    opml: str = ""
    category: str = "OPML导入"
    domain: str = Field(default="business", pattern="^(business|life)$")
    limit: int = 8


def _parse_opml(text: str) -> list[dict]:
    """Extract feeds from OPML XML. Each outline with an xmlUrl becomes a feed.
    The nearest ancestor outline's text is used as the category when present."""
    import xml.etree.ElementTree as ET

    feeds: list[dict] = []
    try:
        root = ET.fromstring(text)
    except Exception:
        return feeds

    def walk(node, parent_label: str = "") -> None:
        for child in list(node):
            if not child.tag.endswith("outline"):
                walk(child, parent_label)
                continue
            xml_url = child.attrib.get("xmlUrl") or child.attrib.get("xmlurl")
            label = child.attrib.get("title") or child.attrib.get("text") or ""
            if xml_url:
                feeds.append({
                    "name": label or xml_url,
                    "url": xml_url.strip(),
                    "category": parent_label or "OPML导入",
                    "_label": label,
                })
            # a grouping outline (no xmlUrl) sets the category for its children
            walk(child, label if not xml_url else parent_label)

    walk(root)
    return feeds


@router.post("/settings/rss/import-opml")
def import_opml(req: OpmlImportIn) -> dict:
    """Parse an OPML document and merge its feeds into user RSS sources (dedup by URL)."""
    parsed = _parse_opml(req.opml or "")
    current = user_settings.load().get("rss", {}) or {}
    existing = list(current.get("sources", []) or [])
    seen = {str(f.get("url", "")).strip() for f in existing if isinstance(f, dict)}
    added = 0
    for feed in parsed:
        url = feed["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        existing.append({
            "name": feed["name"][:80],
            "url": url,
            "domain": req.domain,
            "category": feed.get("category") or req.category,
            "fulltext": False,
            "limit": int(req.limit),
            "enabled": True,
        })
        added += 1
    user_settings.patch({"rss": {"sources": existing}})
    return {"ok": True, "parsed": len(parsed), "added": added, "total": len(existing)}


@router.get("/settings/tuning")
def get_tuning() -> dict:
    """当前生效的阈值/节奏（settings.toml 叠加用户 overrides），供设置页展示与编辑。"""
    return {
        "judge": user_settings.effective("judge"),
        "schedule": user_settings.effective("schedule"),
        "guard": user_settings.effective("guard"),
        "intelligence": user_settings.effective("intelligence"),
        "overrides": user_settings.load().get("overrides", {}),
    }


@router.get("/settings/diagnostics")
def settings_diagnostics() -> dict:
    from ..agent import sysinfo
    from ..ingest.email_ingest import _apple_mail_db, _apple_mail_items, _email_accounts
    apple_items = _apple_mail_items(limit=5, unread_only=False)
    return {
        "settings_path": str(user_settings.SETTINGS_PATH),
        "email_accounts": [
            {"name": a.get("name") or a.get("user") or a.get("username"), "host": a.get("host") or a.get("imap_host") or a.get("provider"), "enabled": a.get("enabled", True)}
            for a in _email_accounts()
        ],
        "apple_mail": {
            "db": str(_apple_mail_db() or ""),
            "recent_count_sample": len(apple_items),
            "sample": [{"title": i.title, "source": i.source, "from": i.meta.get("from")} for i in apple_items[:3]],
        },
        "notifications": sysinfo.local_notifications(),
        "ai_tools": sysinfo.ai_tool_status(max_age=0, block=True),
    }


@router.get("/devices/ssh")
def list_ssh_devices() -> list[dict]:
    from .. import remote_status
    return remote_status.configured_hosts()


@router.post("/devices/ssh")
def add_ssh_device(req: RemoteDeviceIn) -> dict:
    from .. import remote_status
    return {"ok": True, "device": remote_status.add_host(host=req.host, name=req.name, user=req.user, port=req.port, enabled=req.enabled)}


@router.delete("/devices/ssh/{device_id}")
def remove_ssh_device(device_id: str) -> dict:
    from .. import remote_status
    return remote_status.remove_host(device_id)


@router.post("/devices/ssh/probe")
def probe_ssh_devices() -> dict:
    from .. import remote_status
    return remote_status.probe_all()


@router.get("/remote-cortex")
def remote_cortex_list() -> list[dict]:
    from .. import remote_cortex
    return remote_cortex.list_connections()


@router.post("/remote-cortex")
def remote_cortex_add(req: RemoteLeoJarvisIn) -> dict:
    from .. import remote_cortex
    return {"ok": True, "connection": remote_cortex.add_connection(**req.model_dump())}


@router.delete("/remote-cortex/{connection_id}")
def remote_cortex_remove(connection_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.remove_connection(connection_id)


@router.post("/remote-cortex/{connection_id}/connect")
def remote_cortex_connect(connection_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.connect(connection_id)


@router.post("/remote-cortex/{connection_id}/disconnect")
def remote_cortex_disconnect(connection_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.disconnect(connection_id)


@router.get("/remote-cortex/{connection_id}/cockpit")
def remote_cortex_cockpit(connection_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.fetch(connection_id, "/cockpit/overview")


@router.get("/remote-cortex/{connection_id}/system")
def remote_cortex_system(connection_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.fetch(connection_id, "/system/overview")


@router.get("/remote-cortex/{connection_id}/health")
def remote_cortex_health(connection_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.fetch(connection_id, "/health")


@router.get("/device/summary")
def device_summary() -> dict:
    from ..agent import sysinfo
    return sysinfo.device_summary()


@router.post("/devices/self-heartbeat")
def device_self_heartbeat() -> dict:
    from ..agent import sysinfo
    summary = sysinfo.device_summary()
    db.upsert_device_heartbeat(summary)
    return {"ok": True, "device": summary}


@router.post("/devices/heartbeat")
def device_heartbeat(req: DeviceHeartbeatIn) -> dict:
    summary = req.model_dump()
    db.upsert_device_heartbeat(summary)
    return {"ok": True, "device": summary}


@router.get("/devices")
def devices(limit: int = 50) -> list[dict]:
    from ..agent import sysinfo
    local = sysinfo.device_summary()
    db.upsert_device_heartbeat(local)
    rows = db.list_device_heartbeats(limit=limit)
    now = int(time.time())
    for row in rows:
        age = max(0, now - int(row.get("last_seen_ts") or row.get("generated_at") or now))
        row["age_seconds"] = age
        row["online"] = age < 180
    return sorted(rows, key=lambda r: (not r.get("online"), -(float(r.get("health") or 0)), -int(r.get("last_seen_ts") or 0)))


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


@router.get("/system/overview")
def system_overview() -> dict:
    from ..agent import sysinfo
    return sysinfo.structured_status()


@router.get("/system/ai-tools")
def system_ai_tools() -> list[dict]:
    from ..agent import sysinfo
    return sysinfo.ai_tool_status()


@router.post("/system/ai-tools/{tool_id}/upgrade")
def system_ai_tool_upgrade(tool_id: str) -> dict:
    from ..agent import sysinfo
    return sysinfo.ai_tool_upgrade(tool_id)


@router.get("/system/dev-tools")
def system_dev_tools() -> dict:
    from ..agent import sysinfo
    return sysinfo.dev_toolchain_status()


@router.get("/system/notifications")
def system_notifications() -> dict:
    from ..agent import sysinfo
    return sysinfo.local_notifications()


@router.get("/system/weather")
def system_weather(lat: float | None = None, lon: float | None = None, city: str | None = None) -> dict:
    from ..agent import sysinfo
    return sysinfo.weather(latitude=lat, longitude=lon, city=city)


@router.get("/services")
def services_status() -> list[dict]:
    from ..agent import services
    return services.status_all()


@router.get("/cockpit/overview")
def cockpit_overview() -> dict:
    from ..cockpit import overview
    return overview()


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


# ---------- 个人记事（Leonote-inspired） ----------

class PersonalNoteIn(BaseModel):
    title: str = ""
    content: str = ""
    excerpt: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"
    source_url: str = ""
    source_title: str = ""
    import_meta: dict = Field(default_factory=dict)
    favorite: bool = False
    pinned: bool = False
    archived: bool = False


class ImportUrlIn(BaseModel):
    url: str


class AttachmentImportIn(BaseModel):
    file_name: str
    mime_type: str = ""
    data_base64: str = ""
    text_content: str = ""
    note_id: str | None = None


@router.get("/personal-notes")
def personal_note_list(q: str = "", tag: str = "", status: str = "active") -> dict:
    from .. import personal_notes
    return {
        "ok": True,
        "notes": personal_notes.list_notes(q=q, tag=tag, status=status),
        "stats": personal_notes.note_stats(),
    }


@router.post("/personal-notes")
def personal_note_create(note: PersonalNoteIn) -> dict:
    from .. import personal_notes
    return {"ok": True, "note": personal_notes.save_note(note.model_dump())}


@router.get("/personal-notes/{note_id}")
def personal_note_get(note_id: str) -> dict:
    from .. import personal_notes
    note = personal_notes.get_note(note_id)
    return {
        "ok": bool(note),
        "note": note,
        "revisions": personal_notes.list_revisions(note_id),
        "attachments": personal_notes.list_attachments(note_id),
    }


@router.patch("/personal-notes/{note_id}")
def personal_note_update(note_id: str, note: PersonalNoteIn) -> dict:
    from .. import personal_notes
    return {"ok": True, "note": personal_notes.save_note(note.model_dump(), note_id=note_id, reason="manual")}


@router.delete("/personal-notes/{note_id}")
def personal_note_delete(note_id: str) -> dict:
    from .. import personal_notes
    return {"ok": personal_notes.delete_note(note_id)}


@router.post("/personal-notes/import-url")
def personal_note_import_url(req: ImportUrlIn) -> dict:
    from .. import personal_notes
    return {"ok": True, "note": personal_notes.import_url(req.url)}


@router.post("/personal-notes/import-attachment")
def personal_note_import_attachment(req: AttachmentImportIn) -> dict:
    from .. import personal_notes
    return {"ok": True, **personal_notes.attach_file(
        file_name=req.file_name,
        mime_type=req.mime_type,
        data_base64=req.data_base64,
        text_content=req.text_content,
        note_id=req.note_id,
    )}


@router.post("/ingest/run")
async def ingest_run() -> dict:
    return await run_ingest_cycle()


# ---------- Personal Intelligence Hub ----------

class IntelligenceTargetIn(BaseModel):
    label: str = ""
    query: str
    kind: str = "topic"
    enabled: bool = True


class IntelligenceSourceIn(BaseModel):
    type: str = Field(pattern="^(rss|web)$")
    name: str = ""
    url: str
    domain: str = "business"
    enabled: bool = True
    meta: dict = Field(default_factory=dict)


class EnabledPatch(BaseModel):
    enabled: bool


class IntelligenceScanRequest(BaseModel):
    include_rss: bool = True
    include_web: bool = True
    include_github: bool = True


@router.get("/intelligence/overview")
def intelligence_overview() -> dict:
    from ..intelligence.scanner import overview
    return overview()


@router.post("/intelligence/scan")
async def intelligence_scan(req: IntelligenceScanRequest) -> dict:
    from ..intelligence.scanner import run_intelligence_scan
    return await run_intelligence_scan(
        include_rss=req.include_rss,
        include_web=req.include_web,
        include_github=req.include_github,
    )


@router.get("/intelligence/targets")
def intelligence_targets() -> list[dict]:
    from ..intelligence.scanner import list_targets
    return list_targets()


@router.post("/intelligence/targets")
def intelligence_target_add(req: IntelligenceTargetIn) -> dict:
    from ..intelligence.scanner import upsert_target
    return upsert_target(label=req.label, query=req.query, kind=req.kind, enabled=req.enabled)


@router.patch("/intelligence/targets/{target_id}")
def intelligence_target_patch(target_id: str, req: EnabledPatch) -> dict:
    from ..intelligence.scanner import set_target_enabled
    return set_target_enabled(target_id, req.enabled)


@router.get("/intelligence/sources")
def intelligence_sources() -> list[dict]:
    from ..intelligence.scanner import list_sources
    return list_sources()


@router.post("/intelligence/sources")
def intelligence_source_add(req: IntelligenceSourceIn) -> dict:
    from ..intelligence.scanner import upsert_source
    return upsert_source(
        source_type=req.type,
        name=req.name,
        url=req.url,
        domain=req.domain,
        enabled=req.enabled,
        meta=req.meta,
    )


@router.patch("/intelligence/sources/{source_id}")
def intelligence_source_patch(source_id: str, req: EnabledPatch) -> dict:
    from ..intelligence.scanner import set_source_enabled
    return set_source_enabled(source_id, req.enabled)


@router.get("/intelligence/github")
def intelligence_github(limit: int = 24) -> list[dict]:
    from ..intelligence.scanner import github_radar
    return github_radar(limit=limit)


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
        memory_id = db.insert_memory(
            statement,
            subject=row["title"],
            confidence=0.85,
            salience=0.9 if fb.signal == "important" else 0.25,
            source_events=[fb.event_id],
        )
        return {"ok": True, "memory_candidate_id": memory_id, "memory_status": "pending"}
    return {"ok": True, "memory_candidate_id": None}


@router.get("/events")
def events(hours: int = 24) -> list[dict]:
    since = int((time.time() - hours * 3600) * 1000)
    return [dict(r) for r in db.query_events(since)]


@router.get("/memories")
def memories(limit: int = 100) -> list[dict]:
    return [dict(r) for r in db.list_memories(limit)]


@router.get("/memories/pending")
def pending_memories(limit: int = 100) -> list[dict]:
    return [dict(r) for r in db.list_pending_memories(limit)]


class MemoryDecision(BaseModel):
    decision: str = Field(pattern="^(accept|reject|later)$")


@router.post("/memories/{memory_id}/decision")
def memory_decision(memory_id: str, req: MemoryDecision) -> dict:
    status = {"accept": "active", "reject": "rejected", "later": "later"}[req.decision]
    return {"ok": db.update_memory_status(memory_id, status), "status": status}


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
