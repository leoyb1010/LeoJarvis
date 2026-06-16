from __future__ import annotations

from copy import deepcopy
import time
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import db, user_settings
from ..agent.loop import approve_action, run_agent
from ..agent.tools import TOOLBUS
from ..briefing.builder import build_item_detail, build_today
from ..notify.hub import hub
from ..scheduler import run_ingest_cycle

router = APIRouter()


def _public_settings(payload: dict) -> dict:
    data = deepcopy(payload)
    try:
        from .. import mcp_gateway

        data["mcp"] = mcp_gateway.public_settings(data.get("mcp", {}) or {})
    except Exception:
        pass
    return data


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "ts": int(time.time()), "service": "leojarvis"}


class SettingsIn(BaseModel):
    settings: dict = Field(default_factory=dict)


class DeviceOpsPreviewIn(BaseModel):
    action: str
    target_id: str = "local"
    path: str = ""


class ReachReadURLIn(BaseModel):
    url: str
    limit: int = 12000


class ReachRepoIn(BaseModel):
    repo: str


class ReachSearchIn(BaseModel):
    query: str
    limit: int = 10


class MCPSettingsIn(BaseModel):
    settings: dict = Field(default_factory=dict)


class MCPSearchIn(BaseModel):
    query: str
    limit: int = 8
    include_answer: bool = False


@router.get("/settings")
def get_settings() -> dict:
    return _public_settings(user_settings.load())


@router.patch("/settings")
def patch_settings(req: SettingsIn) -> dict:
    return _public_settings(user_settings.patch(req.settings))


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


@router.get("/device/summary")
def device_summary() -> dict:
    from ..agent import sysinfo
    return sysinfo.device_summary()


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


@router.get("/device-ops/status")
def device_ops_status(refresh: bool = False) -> dict:
    import inspect
    from .. import device_ops
    if "refresh" in inspect.signature(device_ops.fleet_status).parameters:
        return device_ops.fleet_status(refresh=refresh)
    return device_ops.fleet_status()


@router.post("/device-ops/preview")
def device_ops_preview(req: DeviceOpsPreviewIn) -> dict:
    from .. import device_ops
    try:
        return device_ops.preview(req.action, target_id=req.target_id, path=req.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reach/status")
def reach_status() -> dict:
    from .. import reach
    return reach.channel_status()


@router.post("/reach/read-url")
def reach_read_url(req: ReachReadURLIn) -> dict:
    from .. import reach
    try:
        return reach.read_url(req.url, limit=req.limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reach/github/repo")
def reach_github_repo(req: ReachRepoIn) -> dict:
    from .. import reach
    try:
        return reach.github_repo(req.repo)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reach/github/search")
def reach_github_search(req: ReachSearchIn) -> dict:
    from .. import reach
    try:
        return reach.github_search(req.query, limit=req.limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mcp/status")
def mcp_status() -> dict:
    from .. import mcp_gateway
    return mcp_gateway.status()


@router.patch("/mcp/settings")
def mcp_settings(req: MCPSettingsIn) -> dict:
    from .. import mcp_gateway
    saved = mcp_gateway.patch_settings(req.settings)
    return {"ok": True, "mcp": mcp_gateway.public_settings(saved), "status": mcp_gateway.status()}


@router.post("/mcp/search")
def mcp_search(req: MCPSearchIn) -> dict:
    from .. import mcp_gateway
    try:
        return mcp_gateway.search_web(req.query, limit=req.limit, include_answer=req.include_answer)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/services")
def services_status() -> list[dict]:
    from ..agent import services
    return services.status_all()


@router.get("/services/discover")
def services_discover() -> list[dict]:
    """本机服务自动发现（三路发现 + 健康探测 + 暴露标注），不依赖手写清单。"""
    from ..agent import services
    return services.discover_services()


@router.get("/agents/cli")
def agents_cli() -> dict:
    """本机 AI agent CLI 花名册：claude/codex/cursor/grok/gemini/opencode 的安装/版本/认证态。
    驱动(run)不走裸 REST，必须经 /agent/chat 的 run_cli_agent 工具 + 行动闸门确认。"""
    from ..agent import cli_agents
    return {"agents": cli_agents.list_agents()}


@router.get("/agents/cli/{name}")
def agents_cli_detail(name: str) -> dict:
    from ..agent import cli_agents
    return cli_agents.agent_detail(name)


@router.get("/horoscope/{sign}")
def horoscope_get(sign: str, date: str | None = None) -> dict:
    """某星座当天运势（离线确定性，只读）。date 可选 YYYY-MM-DD。"""
    from ..agent import horoscope
    return horoscope.horoscope(sign, date)


@router.get("/apps/running")
def apps_running() -> dict:
    """当前运行的 GUI 应用列表（只读）。
    open/quit/focus 不开裸 REST 写口，必须经 /agent/chat 的工具 + 行动闸门确认。"""
    from ..agent import app_manager
    return {"apps": app_manager.list_running_apps()}


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


# ---------- Jarvis 个人记事 ----------

class PersonalNoteIn(BaseModel):
    title: str = ""
    content: str = ""
    excerpt: str = ""
    tags: list[str] = Field(default_factory=list)
    project_name: str = ""
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


class NoteTransformIn(BaseModel):
    template: str = "summary"


@router.get("/personal-notes")
def personal_note_list(q: str = "", tag: str = "", status: str = "active", project: str = "", compact: bool = False) -> dict:
    from .. import personal_notes
    return {
        "ok": True,
        "notes": personal_notes.list_notes(q=q, tag=tag, status=status, project=project, compact=compact),
        "stats": personal_notes.note_stats(),
    }


@router.get("/personal-notes/notebooks")
def personal_note_notebooks() -> dict:
    from .. import personal_notes
    return {"ok": True, **personal_notes.notebook_overview()}


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


@router.post("/personal-notes/{note_id}/transform")
def personal_note_transform(note_id: str, req: NoteTransformIn) -> dict:
    from .. import personal_notes
    return {"ok": True, **personal_notes.transform_note(note_id, req.template)}


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


@router.get("/personal-notes/attachments/{attachment_id}")
def personal_note_attachment_file(attachment_id: str):
    from .. import personal_notes
    attachment = personal_notes.get_attachment(attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="attachment not found")
    path = personal_notes.attachment_path(attachment)
    if not path:
        raise HTTPException(status_code=404, detail="attachment file not found")
    return FileResponse(
        path,
        media_type=attachment.get("mime_type") or "application/octet-stream",
        filename=attachment.get("file_name") or "attachment",
    )


@router.post("/ingest/run")
async def ingest_run() -> dict:
    result = await run_ingest_cycle()
    try:
        from ..briefing.builder import invalidate_today_cache
        invalidate_today_cache()
    except Exception:
        pass
    return result


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
    result = await run_intelligence_scan(
        include_rss=req.include_rss,
        include_web=req.include_web,
        include_github=req.include_github,
    )
    try:
        from ..briefing.builder import invalidate_today_cache
        invalidate_today_cache()
    except Exception:
        pass
    return result


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
def briefing_today(compact: bool = False, limit: int = 0, refresh: bool = False) -> dict:
    return build_today(compact=compact, limit=limit, force=refresh)


@router.get("/briefing/items/{event_id}")
def briefing_item_detail(event_id: str) -> dict:
    item = build_item_detail(event_id)
    if not item:
        raise HTTPException(status_code=404, detail="briefing item not found")
    return {"ok": True, "item": item}


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
