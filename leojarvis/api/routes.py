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


@router.get("/devices")
def devices_list() -> dict:
    """舰队：列出已登记的设备（含本机），标注在线/离线 + 是否当前设备。

    数据源是 device_heartbeats（每台 Mac 定时登记自己的只读健康摘要）。当前为单机，
    列表只有本机；多设备同步（F1）上线后，这张表随同步面汇总，这里就会列出你所有 Mac。
    顺手清掉旧 remote_cortex 留下的 `rc-` 幽灵行（修历史「显示好几台、实际两台」的 bug）。
    """
    from ..agent import sysinfo
    me = sysinfo.device_summary()
    db.upsert_device_heartbeat(me)  # 确保本机始终在册、且是最新
    cur = str(me.get("device_id") or "")
    now = int(time.time())
    out: list[dict] = []
    for r in db.list_device_heartbeats(limit=100):
        did = str(r.get("device_id") or "")
        if did.startswith("rc-"):           # 旧远端连接幽灵 → 直接清理
            db.delete_device_heartbeat(did)
            continue
        last = int(r.get("last_seen_ts") or 0)
        r["online"] = (now - last) <= 120     # 2 分钟内有心跳算在线
        r["is_current"] = did == cur
        r["seen_ago_s"] = max(0, now - last)
        out.append(r)
    out.sort(key=lambda d: (not d.get("is_current"), not d.get("online"), -(d.get("last_seen_ts") or 0)))
    return {"ok": True, "current": cur, "devices": out, "count": len(out)}


@router.delete("/devices/{device_id}")
def devices_delete(device_id: str) -> dict:
    """从舰队移除一台设备（清它的心跳行）。本机会在下次心跳重新登记。"""
    db.delete_device_heartbeat(device_id)
    return {"ok": True}


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
    """本机 AI agent CLI 花名册：claude/codex/cursor/grok/gemini/opencode 的安装/版本/认证态。"""
    from ..agent import cli_agents
    return {"agents": cli_agents.list_agents()}


class CliRunIn(BaseModel):
    name: str
    prompt: str
    cwd: str | None = None
    model: str | None = None


@router.post("/agents/cli/run")
def agents_cli_run(req: CliRunIn) -> dict:
    """真实后台运行一个本机 CLI agent（用户在智能体页主动发起即确认），输出流式写日志。
    model：可选，/model 快捷菜单选的模型，注入到 CLI。"""
    from ..agent import cli_agents
    return cli_agents.spawn_cli_agent(req.name, req.prompt, cwd=req.cwd, model=req.model)


@router.get("/agents/cli/sessions")
def agents_cli_sessions() -> dict:
    """所有真实 CLI agent 会话及实时状态/输出（智能体页轮询此端点做真实流式观察）。
    external：本机已常驻运行的 agent 网关（Hermes/OpenClaw），用户视角的"运行中 agent"。"""
    from ..agent import cli_agents
    return {"sessions": cli_agents.cli_sessions(), "external": cli_agents.external_running()}


@router.post("/agents/cli/sessions/{sid}/stop")
def agents_cli_session_stop(sid: str) -> dict:
    from ..agent import cli_agents
    return cli_agents.stop_cli_session(sid)


@router.post("/agents/cli/clear-finished")
def agents_cli_clear_finished() -> dict:
    """清理已结束的 CLI agent 会话（运行中保留）。"""
    from ..agent import cli_agents
    return cli_agents.clear_finished_sessions()


@router.get("/agents/cli/{name}/commands")
def agents_cli_commands(name: str) -> dict:
    """某 agent 真实可用的斜杠命令（内建 + 自定义）+ 模型清单，供前端 / 快捷菜单。"""
    from ..agent import cli_agents
    return cli_agents.agent_commands(name)


@router.get("/agents/cli/{name}")
def agents_cli_detail(name: str) -> dict:
    from ..agent import cli_agents
    return cli_agents.agent_detail(name)


@router.get("/capsules")
def capsules() -> dict:
    """能力胶囊花名册：我有哪些超能力、各自注册了哪些工具。"""
    from .. import capsules as caps
    return {"capsules": caps.capsule_manifest()}


@router.get("/horoscope/{sign}")
def horoscope_get(sign: str, date: str | None = None) -> dict:
    """某星座当天运势（离线确定性，只读）。date 可选 YYYY-MM-DD。"""
    from ..agent import horoscope
    return horoscope.horoscope(sign, date)


@router.get("/amap/config")
def amap_config() -> dict:
    """前端小地图初始化配置：JS key + 默认中心城市坐标（只读）。"""
    from ..agent import amap
    from ..config import settings
    home_city = (settings().get("amap", {}) or {}).get("home_city", "北京")
    center = None
    if amap.configured():
        g = amap.geocode(home_city)
        if g.get("ok"):
            center = g.get("location")
    return {"configured": amap.configured(), "js_key": amap.js_key(),
            "home_city": home_city, "center": center}


@router.get("/amap/weather")
def amap_weather(city: str = "北京") -> dict:
    """城市天气（实况 + 预报，只读）。"""
    from ..agent import amap
    return amap.weather(city)


@router.get("/amap/poi")
def amap_poi(keywords: str, city: str | None = None, limit: int = 8) -> dict:
    """POI 搜索（只读）。"""
    from ..agent import amap
    return amap.poi_search(keywords, city, limit)


@router.get("/apps/running")
def apps_running() -> dict:
    """当前运行的 GUI 应用列表（只读）。
    quit/focus 仍走 /agent/chat 工具 + 行动闸门；open 是用户在界面上主动点击的最温和动作，开直接口。"""
    from ..agent import app_manager
    return {"apps": app_manager.list_running_apps()}


class AppOpenIn(BaseModel):
    name: str


@router.post("/apps/open")
def apps_open(req: AppOpenIn) -> dict:
    """打开一个本机应用 / 网页（按 id 真实路由）。用户在「应用与邮件」主动点击触发，仅 open。"""
    from ..agent import app_manager
    try:
        return {"ok": True, "result": app_manager.open_routed(req.name)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


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
    notebook: str = ""


class AttachmentImportIn(BaseModel):
    file_name: str
    mime_type: str = ""
    data_base64: str = ""
    text_content: str = ""
    note_id: str | None = None
    notebook: str = ""


class NoteTransformIn(BaseModel):
    template: str = "summary"


# ── open-notebook 能力（笔记本 / 来源 / RAG 对话 / 工作室）──
class NotebookChatIn(BaseModel):
    notebook: str = ""
    question: str
    source_ids: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)


class NotebookStudioIn(BaseModel):
    notebook: str = ""
    kind: str = "overview"
    source_ids: list[str] = Field(default_factory=list)


class NotebookTextSourceIn(BaseModel):
    notebook: str = ""
    title: str = ""
    text: str


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
    return {"ok": True, "note": personal_notes.import_url(req.url, notebook=req.notebook)}


@router.post("/personal-notes/import-attachment")
def personal_note_import_attachment(req: AttachmentImportIn) -> dict:
    from .. import personal_notes
    return {"ok": True, **personal_notes.attach_file(
        file_name=req.file_name,
        mime_type=req.mime_type,
        data_base64=req.data_base64,
        text_content=req.text_content,
        note_id=req.note_id,
        notebook=req.notebook,
    )}


# ── open-notebook：工作区 / 来源 / RAG 对话 / 工作室 ──
@router.get("/notebook/workspace")
def notebook_workspace(notebook: str = "") -> dict:
    from .. import notebook as nb
    return {"ok": True, **nb.list_workspace(notebook), "studio_templates": nb.studio_templates()}


@router.post("/notebook/source-text")
def notebook_source_text(req: NotebookTextSourceIn) -> dict:
    from .. import notebook as nb
    try:
        return {"ok": True, "note": nb.add_text_source(req.notebook, req.title, req.text)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/notebook/chat")
def notebook_chat(req: NotebookChatIn) -> dict:
    from .. import notebook as nb
    try:
        return {"ok": True, **nb.notebook_chat(req.notebook, req.question, req.source_ids or None, req.history)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/notebook/studio")
def notebook_studio(req: NotebookStudioIn) -> dict:
    from .. import notebook as nb
    try:
        return {"ok": True, **nb.notebook_studio(req.notebook, req.kind, req.source_ids or None)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@router.websocket("/ws/term")
async def ws_term(ws: WebSocket):
    """真实交互终端桥：浏览器 xterm.js ←→ PTY 里以交互模式运行的 agent。

    首帧 {type:"start", agent, cwd, cols, rows} 起一个 PTY；之后：
      - 浏览器键盘  → {type:"input", data} / 原始文本 / 二进制 → 写进 PTY
      - {type:"resize", cols, rows}                         → 同步窗口大小
      - PTY 输出（含 ANSI）                                   → 二进制帧回浏览器
    这样 claude 的 /model、codex 的斜杠命令等**原生 TUI** 在这里完整执行。
    """
    import asyncio
    import json as _json

    from ..agent import pty_term

    await ws.accept()
    pid = None
    fd = None
    reader_task = None
    try:
        init = await ws.receive_json()
        agent = str(init.get("agent", "claude"))
        cols = int(init.get("cols", 120) or 120)
        rows = int(init.get("rows", 32) or 32)
        spawned = pty_term.spawn(agent, cwd=init.get("cwd") or "~", cols=cols, rows=rows)
        if not spawned:
            await ws.send_json({"type": "error", "msg": f"未知或不支持交互的 agent: {agent}"})
            await ws.close()
            return
        pid, fd = spawned
        loop = asyncio.get_event_loop()

        async def pump() -> None:
            # 在线程池里非阻塞 select PTY，把输出二进制帧回推浏览器
            while True:
                data = await loop.run_in_executor(None, pty_term.read_available, fd, 0.05)
                if data is None:
                    try:
                        await ws.send_json({"type": "exit"})
                    except Exception:
                        pass
                    return
                if data:
                    try:
                        await ws.send_bytes(data)
                    except Exception:
                        return
                else:
                    await asyncio.sleep(0.01)

        reader_task = asyncio.create_task(pump())

        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                pty_term.write(fd, msg["bytes"])
                continue
            txt = msg.get("text")
            if txt is None:
                continue
            obj = None
            if txt[:1] == "{":
                try:
                    obj = _json.loads(txt)
                except Exception:
                    obj = None
            if obj and obj.get("type") == "resize":
                pty_term.set_winsize(fd, int(obj.get("rows", rows) or rows), int(obj.get("cols", cols) or cols))
            elif obj and obj.get("type") == "input":
                pty_term.write(fd, str(obj.get("data", "")).encode("utf-8", "ignore"))
            else:
                pty_term.write(fd, txt.encode("utf-8", "ignore"))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if reader_task is not None:
            reader_task.cancel()
        if pid is not None and fd is not None:
            pty_term.kill(pid, fd)
