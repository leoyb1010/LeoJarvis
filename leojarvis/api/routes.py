from __future__ import annotations

from copy import deepcopy
import time
import uuid

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import db, user_settings
from ..agent.loop import approve_action, run_agent, run_agent_stream
from ..agent.tools import TOOLBUS
from ..auth import bearer_token, is_authorized, is_trusted_local
from urllib.parse import urlsplit
from ..briefing.builder import build_item_detail, build_today
from ..notify.hub import hub
from ..scheduler import run_ingest_cycle

router = APIRouter()


def _ws_origin_ok(ws: WebSocket) -> bool:
    """浏览器发起的 WebSocket 握手会带 Origin 头；只放行回环来源，挡掉恶意站点的
    跨站驱动（尤其是 /ws/term 这种 PTY）。非浏览器客户端不带 Origin，直接放行交给 token 鉴权。"""
    origin = ws.headers.get("origin")
    if not origin:
        return True
    host = (urlsplit(origin).hostname or "").lower()
    if host.startswith("::ffff:"):
        host = host[len("::ffff:"):]
    return host in {"localhost", "127.0.0.1", "::1"}


async def _authorize_websocket(ws: WebSocket) -> bool:
    if not _ws_origin_ok(ws):
        await ws.close(code=1008)
        return False
    client_host = ws.client.host if ws.client else None
    if is_trusted_local(client_host, ws.headers):
        return True
    supplied = bearer_token(ws.headers.get("authorization"))
    if not supplied:
        supplied = ws.headers.get("x-leojarvis-token", "")
    if not supplied:
        supplied = ws.query_params.get("token", "")
    if is_authorized(supplied):
        return True
    await ws.close(code=1008)
    return False


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


class LocalizeBatchIn(BaseModel):
    texts: list[str]
    context: str = "移动端情报"
    max_chars: int = 420
    allow_llm: bool = True


class MCPSettingsIn(BaseModel):
    settings: dict = Field(default_factory=dict)


class MCPSearchIn(BaseModel):
    query: str
    limit: int = 8
    include_answer: bool = False
    purpose: str = "manual"


class SpeechTranscribeIn(BaseModel):
    data_base64: str
    mime_type: str = "audio/wav"
    file_name: str = "recording.wav"
    model: str = "base"
    language: str = "auto"
    prompt: str = ""


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


def _remote_public_device_summaries(current_device_id: str) -> list[dict]:
    import json
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from urllib.parse import urlparse

    targets = [
        target for target in (user_settings.load().get("remote_public_endpoints") or [])
        if isinstance(target, dict) and target.get("enabled", True) and str(target.get("endpoint") or "").strip()
    ]
    if not targets:
        return []

    def fetch(target: dict) -> dict | None:
        endpoint = str(target.get("endpoint") or "").strip().rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            endpoint = "https://" + endpoint
        try:
            started = time.perf_counter()
            with urllib.request.urlopen(endpoint + "/api/device/summary", timeout=2.8) as resp:
                summary = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not isinstance(summary, dict):
                return None
            if str(summary.get("device_id") or "") == current_device_id:
                return None
            summary["role"] = "remote-leojarvis"
            summary["remote_target_id"] = str(target.get("id") or "")
            summary["remote_target_name"] = str(target.get("name") or summary.get("device_name") or "")
            summary["public_endpoint"] = endpoint
            summary["network_latency_ms"] = int((time.perf_counter() - started) * 1000)
            summary["last_seen_ts"] = int(time.time())
            summary["generated_at"] = int(time.time())
            if not summary.get("host_name"):
                summary["host_name"] = urlparse(endpoint).hostname or endpoint
            return summary
        except Exception as exc:  # noqa: BLE001
            return {
                "device_id": f"remote-public-{target.get('id') or endpoint}",
                "device_name": str(target.get("name") or target.get("id") or "远端 Mac"),
                "host_name": urlparse(endpoint).hostname or endpoint,
                "role": "remote-leojarvis",
                "status": "离线",
                "health": 0,
                "public_endpoint": endpoint,
                "last_seen_ts": 0,
                "generated_at": 0,
                "error": str(exc)[:180],
            }

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        futures = [pool.submit(fetch, target) for target in targets]
        for future in as_completed(futures, timeout=4):
            item = future.result()
            if item:
                rows.append(item)
    return rows


@router.get("/devices")
def devices_list() -> dict:
    """舰队：列出已登记的设备（含本机），标注在线/离线 + 是否当前设备。

    数据源是 device_heartbeats（每台 Mac 定时登记自己的只读健康摘要）。当前为单机，
    列表只有本机；多设备同步（F1）上线后，这张表随同步面汇总，这里就会列出你所有 Mac。
    顺手清掉旧 remote_cortex 留下的 `rc-` 幽灵行（修历史「显示好几台、实际两台」的 bug）。
    """
    from ..agent import sysinfo
    me = sysinfo.device_summary()
    # 本机心跳由调度器的 run_heartbeat 每 60s 维护，这里不再写库（避免 GET 产生副作用、
    # 防止跨站预取 /devices 触发数据写入/删除）。读取时仍兜底取一次本机摘要用于标注 current。
    cur = str(me.get("device_id") or "")
    live_public_names: set[str] = set()
    for summary in _remote_public_device_summaries(cur):
        if int(summary.get("last_seen_ts") or 0) > 0:
            db.upsert_device_heartbeat(summary)
            live_public_names.add(str(summary.get("remote_target_name") or summary.get("device_name") or "").lower())
    now = int(time.time())
    out: list[dict] = []
    for r in db.list_device_heartbeats(limit=100):
        did = str(r.get("device_id") or "")
        if did.startswith("rc-"):           # 旧远端连接幽灵 → 调度器会清理，这里仅从列表过滤
            continue
        last = int(r.get("last_seen_ts") or 0)
        r["online"] = (now - last) <= 120     # 2 分钟内有心跳算在线
        r["is_current"] = did == cur
        r["seen_ago_s"] = max(0, now - last)
        name_key = str(r.get("device_name") or r.get("host_name") or did).lower()
        is_stale_ssh_shadow = (
            r.get("role") == "ssh"
            and not r["online"]
            and (
                did in {"ssh-macbook-pro", "ssh-mac-studio", "ssh-mac-mini", "macbook-pro", "mac-studio", "mac-mini"}
                or any(part in name_key for part in ("macbook pro", "mac studio", "mac mini"))
            )
            and (live_public_names or did == "ssh-macbook-pro")
        )
        if is_stale_ssh_shadow:        # 陈旧 SSH 影子行 → 仅从列表隐藏，不在 GET 里删库
            continue
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


@router.post("/agent/chat/stream")
async def agent_chat_stream(req: ChatRequest) -> StreamingResponse:
    """流式对话（SSE）：逐步把思考/工具/最终答复事件推给前端，首字亚秒可见。

    run_agent_stream 是同步生成器且内部有阻塞 LLM 调用，这里放到线程里跑、用 asyncio.Queue
    把事件桥到异步流，避免阻塞事件循环。每个事件序列化为一行 `data: {json}\\n\\n`。
    """
    import asyncio
    import json as _json

    messages = [m.model_dump() for m in req.messages]
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    _SENTINEL = object()

    def _produce() -> None:
        try:
            for event in run_agent_stream(messages):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    async def _event_source():
        fut = loop.run_in_executor(None, _produce)
        try:
            while True:
                event = await queue.get()
                if event is _SENTINEL:
                    break
                yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            await fut

    return StreamingResponse(
        _event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ApproveRequest(BaseModel):
    id: str
    decision: str = Field(pattern="^(approve|reject)$")


@router.post("/agent/approve")
def agent_approve(req: ApproveRequest) -> dict:
    return approve_action(req.id, req.decision)


class PreviewRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


@router.post("/agent/preview")
def agent_preview(req: PreviewRequest) -> dict:
    """V4 行动预演沙箱：高危 shell 命令真跑前，看清将执行什么/预期影响/能否撤销。
    破坏级直接阻断、不预演。纯预演无副作用。"""
    from ..agent.sandbox import preview_shell
    return {"ok": True, **preview_shell(req.command)}


@router.get("/agent/tools")
def agent_tools() -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in TOOLBUS.all()]


@router.get("/audit/logs")
def audit_logs(
    tool: str = Query("", description="按工具名过滤"),
    status: str = Query("", description="auto/approved/rejected/denied"),
    risk: str = Query("", description="auto/confirm/deny"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """V4 动作审计账本：分页 + 按工具/状态/风险筛选。本机只读、可回溯。"""
    rows = db.list_audit_logs(tool=tool, status=status, risk=risk, limit=limit, offset=offset)
    total = db.count_audit_logs(tool=tool, status=status, risk=risk)
    items = []
    for r in rows:
        d = dict(r)
        items.append({
            "id": d["id"], "ts": d["ts"], "tool": d["tool"],
            "args": d.get("args"), "output_summary": d.get("output_summary"),
            "risk": d.get("risk"), "status": d["status"],
            "approved_by": d.get("approved_by") or "",
            "reversible": bool(d.get("reversible")),
            "undo_ref": d.get("undo_ref"),
            "duration_ms": d.get("duration_ms") or 0,
        })
    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": items}


@router.post("/audit/{audit_id}/undo")
def audit_undo(audit_id: str) -> dict:
    """V4 一键回滚：撤销某条可逆动作（文档还原上一版 / 返回 shell 反向命令）。"""
    from ..agent.rollback import undo
    return undo(audit_id)


@router.get("/metrics")
def metrics() -> dict:
    """系统自身健康：LLM 调用数、批量 judge 规模、最近扫描耗时、DB 行数。本机只读。"""
    from .. import obs
    snap = obs.snapshot()
    rows: dict[str, int] = {}
    try:
        with db.conn() as c:
            for table in ("events", "judgments", "memories", "personal_notes",
                          "github_repo_snapshots", "device_heartbeats", "audit_logs"):
                try:
                    r = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    rows[table] = int(r[0] if not isinstance(r, dict) else list(r.values())[0])
                except Exception:
                    rows[table] = -1
    except Exception:
        pass
    snap["db_rows"] = rows
    # 超级 Jarvis：记忆分层计数 + embedding 后端（让驾驶舱能看「Jarvis 现在记得多少、是不是真向量」）。
    try:
        snap["memory_layers"] = db.memory_layer_counts()
    except Exception:
        snap["memory_layers"] = {}
    try:
        from .. import embeddings
        snap["embedding_neural"] = embeddings.is_neural()
    except Exception:
        snap["embedding_neural"] = False
    return snap


@router.post("/localize/chinese")
def localize_chinese(req: LocalizeBatchIn) -> dict:
    from ..localize import to_chinese

    max_chars = min(max(int(req.max_chars or 420), 40), 900)
    texts = [str(text or "").strip()[:1800] for text in (req.texts or [])[:80]]
    translations = [
        to_chinese(
            text,
            context=req.context or "移动端情报",
            max_chars=max_chars,
            allow_llm=bool(req.allow_llm),
        )
        for text in texts
    ]
    return {"ok": True, "translations": translations}


@router.get("/speech/status")
def speech_status() -> dict:
    from .. import speech
    return speech.status()


@router.post("/speech/transcribe")
def speech_transcribe(req: SpeechTranscribeIn) -> dict:
    from .. import speech
    try:
        return speech.transcribe_base64(
            data_base64=req.data_base64,
            mime_type=req.mime_type,
            file_name=req.file_name,
            model=req.model,
            language=req.language,
            prompt=req.prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
    from ..intelligence import scanner

    try:
        if req.purpose != "intel_fallback":
            raise HTTPException(
                status_code=400,
                detail={"error": "tavily_reserved_for_intel_fallback", "message": "Tavily paid search is only available as intelligence fallback."},
            )
        reserved, budget = scanner._reserve_tavily_query(f"mcp_search:{req.purpose or 'manual'}")
        if not reserved:
            raise HTTPException(status_code=429, detail={"error": "tavily_budget_exhausted", "budget": budget})
        return mcp_gateway.search_web(req.query, limit=req.limit, include_answer=req.include_answer)
    except HTTPException:
        raise
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
def personal_note_list(
    q: str = "",
    tag: str = "",
    status: str = "active",
    project: str = "",
    compact: bool = False,
    limit: int = 100,
) -> dict:
    from .. import personal_notes
    return {
        "ok": True,
        "notes": personal_notes.list_notes(q=q, tag=tag, status=status, project=project, compact=compact, limit=limit),
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


@router.get("/intelligence/browser-preferences")
def intelligence_browser_preferences(
    window_days: int = 45,
    limit_terms: int = 40,
    limit_domains: int = 18,
    refresh: bool = False,
) -> dict:
    from ..browser_history import browser_preferences

    safe_window = min(max(int(window_days or 45), 1), 120)
    safe_terms = min(max(int(limit_terms or 40), 1), 80)
    safe_domains = min(max(int(limit_domains or 18), 1), 40)
    return browser_preferences(
        window_days=safe_window,
        limit_terms=safe_terms,
        limit_domains=safe_domains,
        refresh=refresh,
    )


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
    # 秒开:命中翻译缓存直接给中文,否则先回原文 + pending_translation,前端再调下面的 translate 异步补译。
    item = build_item_detail(event_id, translate=False)
    if not item:
        raise HTTPException(status_code=404, detail="briefing item not found")
    return {"ok": True, "item": item}


@router.post("/briefing/items/{event_id}/translate")
def briefing_item_translate(event_id: str) -> dict:
    # 同步全译(写翻译缓存),供前端在抽屉打开后异步替换原文。
    item = build_item_detail(event_id, translate=True)
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


@router.post("/memory/distill")
def memory_distill(limit: int = 200) -> dict:
    """从投喂的情景记忆提炼 fact/pattern/entity（超级 Jarvis P3）。"""
    from ..memory.reflect import reflect_personal_data
    return reflect_personal_data(limit=limit)


# ---------- 超级 Jarvis：主动认知 出主意/决策/预判（P4） ----------

class AdviseIn(BaseModel):
    topic: str


@router.post("/cognition/advise")
def cognition_advise(req: AdviseIn) -> dict:
    from .. import cognition
    return cognition.advise(req.topic)


class DecideIn(BaseModel):
    question: str
    options: list[str]


@router.post("/cognition/decide")
def cognition_decide(req: DecideIn) -> dict:
    from .. import cognition
    return cognition.decide(req.question, req.options)


class AnticipateIn(BaseModel):
    context_hint: str = ""


@router.post("/cognition/anticipate")
def cognition_anticipate(req: AnticipateIn) -> dict:
    from .. import cognition
    return cognition.anticipate(req.context_hint)


# ---------- 超级 Jarvis：反馈进化闭环（P5） ----------

class MemoryFeedbackIn(BaseModel):
    memory_id: str
    verdict: str = Field(pattern="^(accept|ignore|correct)$")
    correction: str | None = None   # verdict=correct 时的更正内容


@router.post("/cognition/feedback")
def cognition_feedback(req: MemoryFeedbackIn) -> dict:
    """对一条记忆/建议的反馈回流，校准画像与记忆权重（越用越懂你）：
       accept  → 强化（salience/confidence 上调）
       ignore  → 衰减
       correct → 衰减原记忆 + 记一条更正后的新 fact"""
    if req.verdict == "accept":
        ok = db.adjust_memory(req.memory_id, salience_delta=0.15, confidence_delta=0.1)
        return {"ok": ok, "verdict": "accept"}
    if req.verdict == "ignore":
        ok = db.adjust_memory(req.memory_id, salience_delta=-0.15, confidence_delta=-0.05)
        return {"ok": ok, "verdict": "ignore"}
    # correct：弱化原记忆，并把更正写成新的待确认 fact
    db.adjust_memory(req.memory_id, salience_delta=-0.2, confidence_delta=-0.15)
    new_id = None
    if req.correction and req.correction.strip():
        new_id = db.insert_memory(req.correction.strip()[:2000], memory_type="correction",
                                  layer="fact", origin="feedback_correction",
                                  status="active", confidence=0.7, salience=0.6)
    return {"ok": True, "verdict": "correct", "new_memory_id": new_id}


@router.post("/memory/health-sweep")
def memory_health_sweep_route(min_confidence: float = 0.2, stale_days: int = 120) -> dict:
    """记忆体检：低置信/久未更新的活跃记忆归档，防「自信地记错」。"""
    return db.memory_health_sweep(min_confidence=min_confidence, stale_days=stale_days)


# ---------- 超级 Jarvis：个人数据投喂 + 隐私闸门（P2） ----------

@router.get("/personal-data/status")
def personal_data_status() -> dict:
    """同意分级开关 + 当前各记忆层条数（让你随时知道 Jarvis 记了什么、来自哪类同意）。"""
    from .. import user_settings
    return {
        "config": (user_settings.load() or {}).get("personal_data", {}),
        "memory_layers": db.memory_layer_counts(),
    }


class IngestTextIn(BaseModel):
    text: str
    kind: str = Field(default="work", pattern="^(work|chat|preference|behavior)$")
    layer: str = Field(default="episode", pattern="^(fact|episode|pattern|entity)$")
    source_ref: str = ""
    subject: str | None = None


@router.post("/personal-data/ingest/text")
def personal_data_ingest_text(req: IngestTextIn) -> dict:
    from .. import personal_data
    src = req.source_ref or f"personal_data:{req.kind}:adhoc"
    items = personal_data.from_text_document(
        req.text, source_ref=src, kind=req.kind, layer=req.layer, subject=req.subject
    )
    res = personal_data.ingest_items(items)
    return _ingest_result_dict(res)


class IngestChatIn(BaseModel):
    messages: list[dict]
    source_ref: str = ""


@router.post("/personal-data/ingest/chat")
def personal_data_ingest_chat(req: IngestChatIn) -> dict:
    from .. import personal_data
    src = req.source_ref or "personal_data:chat:import"
    items = personal_data.from_chat_export(req.messages, source_ref=src)
    res = personal_data.ingest_items(items)
    return _ingest_result_dict(res)


class IngestPrefsIn(BaseModel):
    preferences: dict
    source_ref: str = "personal_data:preference:form"


@router.post("/personal-data/ingest/preferences")
def personal_data_ingest_prefs(req: IngestPrefsIn) -> dict:
    from .. import personal_data
    items = personal_data.from_preferences(req.preferences, source_ref=req.source_ref)
    # 本人填写的喜好问卷，可信来源 → 直接 active（其余类型仍走 pending 确认）。
    res = personal_data.ingest_items(items, auto_confirm=True)
    return _ingest_result_dict(res)


class IngestBehaviorIn(BaseModel):
    events: list[dict]
    source_ref: str = "personal_data:behavior"


@router.post("/personal-data/ingest/behavior")
def personal_data_ingest_behavior(req: IngestBehaviorIn) -> dict:
    from .. import personal_data
    items = personal_data.from_behavior_log(req.events, source_ref=req.source_ref)
    res = personal_data.ingest_items(items)
    return _ingest_result_dict(res)


class ForgetIn(BaseModel):
    source_ref: str


@router.post("/personal-data/forget")
def personal_data_forget(req: ForgetIn) -> dict:
    """被遗忘权：删除某来源衍生的全部记忆（含向量库）。"""
    from .. import personal_data
    deleted = personal_data.forget_source(req.source_ref)
    return {"ok": True, "deleted": deleted, "source_ref": req.source_ref}


def _ingest_result_dict(res) -> dict:
    return {
        "ok": True,
        "accepted": res.accepted,
        "skipped_no_consent": res.skipped_no_consent,
        "skipped_redline": res.skipped_redline,
        "redacted": res.redacted,
        "errors": res.errors,
        "memory_ids": res.memory_ids,
    }


# ---------- WorkDock 合并 M2：信息转任务收件箱 ----------

@router.get("/inbox/list")
def inbox_list(states: str = "unconfirmed,confirmed", limit: int = 100) -> dict:
    """收件箱任务列表。states 逗号分隔(unconfirmed/confirmed/done/ignored)。"""
    from .. import inbox
    state_list = [s.strip() for s in states.split(",") if s.strip()] or None
    return inbox.list_inbox(states=state_list, limit=limit)


@router.post("/inbox/rebuild")
def inbox_rebuild(hours: int = 48, limit: int = 40) -> dict:
    """从近期已判定事件(judge notify/digest)自动抽成结构化待办,带来源+置信度。"""
    from .. import inbox
    return inbox.rebuild(hours=hours, limit=limit)


class InboxStateIn(BaseModel):
    state: str = Field(pattern="^(unconfirmed|confirmed|done|ignored)$")


@router.post("/inbox/{task_id}/state")
def inbox_set_state(task_id: str, req: InboxStateIn) -> dict:
    """确认/忽略/完成一条待办(确认队列)。"""
    from .. import inbox
    return inbox.set_state(task_id, req.state)


# ---------- P1：Email 腔理(摘要/标签/actionable/回复草稿) ----------

@router.post("/email/triage")
def email_triage_run(hours: int = 720, limit: int = 60, refresh: bool = False) -> dict:
    """腔理近 hours 小时的邮件:AI 摘要+标签+是否需处理+回复草稿。结果缓存。"""
    from .. import email_triage
    return email_triage.triage(hours=hours, limit=limit, refresh=refresh)


@router.get("/email/triage/{event_id}")
def email_triage_get(event_id: str) -> dict:
    """取某封邮件的腔理结果(摘要/标签/草稿)。"""
    from .. import email_triage
    d = email_triage.triage_dict(event_id)
    return {"ok": d is not None, "triage": d}


# ---------- A：主动助理 + 早中晚 check-in ----------

@router.get("/assistant/config")
def assistant_get_config() -> dict:
    from .. import assistant
    return {"ok": True, "config": assistant.get_config()}


class AssistantConfigIn(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    persona: str | None = None
    checkins: dict | None = None


@router.patch("/assistant/config")
def assistant_patch_config(req: AssistantConfigIn) -> dict:
    from .. import assistant
    partial = {k: v for k, v in req.model_dump().items() if v is not None}
    return {"ok": True, "config": assistant.update_config(partial)}


@router.post("/assistant/checkins/{slot}/run")
def assistant_run_checkin(slot: str) -> dict:
    """立即手动跑一次 check-in(morning/midday/evening)。"""
    from .. import assistant
    return assistant.run_checkin(slot)


# ---------- P3：定时/事件触发的 agent 任务 ----------

class ScheduledTaskIn(BaseModel):
    name: str
    prompt: str
    trigger: str = Field(pattern="^(interval|cron|event)$")
    interval_minutes: int | None = None
    cron_hour: int | None = None
    cron_minute: int | None = None
    trigger_event: str | None = None
    trigger_count: int = 1


@router.get("/tasks/scheduled")
def scheduled_list() -> dict:
    rows = db.list_scheduled_tasks()
    return {"ok": True, "tasks": [dict(r) for r in rows]}


@router.post("/tasks/scheduled")
def scheduled_create(req: ScheduledTaskIn) -> dict:
    tid = db.create_scheduled_task(
        name=req.name, prompt=req.prompt, trigger=req.trigger, interval_minutes=req.interval_minutes,
        cron_hour=req.cron_hour, cron_minute=req.cron_minute, trigger_event=req.trigger_event,
        trigger_count=req.trigger_count,
    )
    return {"ok": True, "id": tid}


class SchedStatusIn(BaseModel):
    status: str = Field(pattern="^(active|paused|deleted)$")


@router.post("/tasks/scheduled/{task_id}/status")
def scheduled_set_status(task_id: str, req: SchedStatusIn) -> dict:
    return {"ok": db.set_scheduled_task_status(task_id, req.status)}


@router.post("/tasks/scheduled/{task_id}/run")
def scheduled_run_now(task_id: str) -> dict:
    """立即手动跑一次该任务(agent 经行动闸门)。"""
    from .. import event_bus
    t = db.get_scheduled_task(task_id)
    if not t:
        return {"ok": False, "error": "not found"}
    return {"ok": True, "result": event_bus._run_task_row(t)}


# ---------- 问题1:日程(schedule) ----------

class ScheduleIn(BaseModel):
    title: str
    start_ts: int
    remind_ts: int | None = None
    note: str = ""
    repeat: str = "none"


class SchedulePatch(BaseModel):
    title: str | None = None
    start_ts: int | None = None
    remind_ts: int | None = None
    note: str | None = None
    repeat: str | None = None
    status: str | None = None


@router.get("/schedule")
def schedule_list(status: str = "", upcoming_hours: int = 0) -> dict:
    from .. import schedule as sch
    return {"ok": True, "items": sch.list_items(status=status, upcoming_hours=upcoming_hours), "stats": sch.stats()}


@router.post("/schedule")
def schedule_create(req: ScheduleIn) -> dict:
    from .. import schedule as sch
    sid = sch.create(title=req.title, start_ts=req.start_ts, remind_ts=req.remind_ts, note=req.note, repeat=req.repeat)
    return {"ok": sid is not None, "id": sid}


@router.patch("/schedule/{sid}")
def schedule_update(sid: str, req: SchedulePatch) -> dict:
    from .. import schedule as sch
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    return {"ok": sch.update(sid, **fields)}


@router.post("/schedule/{sid}/done")
def schedule_done(sid: str, done: bool = True) -> dict:
    from .. import schedule as sch
    return {"ok": sch.set_done(sid, done)}


@router.delete("/schedule/{sid}")
def schedule_delete(sid: str) -> dict:
    from .. import schedule as sch
    return {"ok": sch.delete(sid)}


# ---------- P2：Calendar / CalDAV ----------

class IcsImportIn(BaseModel):
    ics: str
    source: str = "calendar:ics"


@router.post("/calendar/import-ics")
def calendar_import_ics(req: IcsImportIn) -> dict:
    """导入 ics 文本(本地日历文件内容/订阅链接抓回的文本)→ 落为日历事件。"""
    from .. import calendar_sync
    return calendar_sync.import_ics(req.ics, source=req.source)


@router.post("/calendar/sync")
def calendar_sync_caldav() -> dict:
    """从配置的 CalDAV 拉取日历(需 [calendar].caldav_url + caldav 依赖)。"""
    from .. import calendar_sync
    return calendar_sync.sync_caldav()


@router.get("/calendar/upcoming")
def calendar_upcoming(hours: int = 168, limit: int = 50) -> dict:
    """未来 N 小时的日历事件(给首页/收尾用)。"""
    from .. import calendar_sync
    return {"ok": True, "events": calendar_sync.upcoming(hours=hours, limit=limit)}


@router.get("/calendar/caldav-status")
def calendar_caldav_status() -> dict:
    """CalDAV 写回状态(给待办 UI 看是否已开启同步)。不回传密码。"""
    from .. import caldav_writeback
    return caldav_writeback.config_status()


# ---------- P4：深入调研(goal-based 多步) ----------

class DeepResearchIn(BaseModel):
    goal: str
    max_sources: int = 5


@router.post("/research/deep")
def research_deep_run(req: DeepResearchIn) -> dict:
    """对一个目标做多步网络调研:搜索→读源→目标导向抽取→综合报告。"""
    from .. import research_deep
    return research_deep.research(req.goal, max_sources=max(1, min(req.max_sources, 8)))


@router.get("/search")
def search_multi(q: str, limit: int = 8) -> dict:
    """多源搜索(C2):免费源优先 + 相关/时效/权威排序。无源时优雅降级。"""
    from .. import search_providers
    return search_providers.search(q, limit=max(1, min(limit, 20)))


# ---------- D：调研可视化报告 ----------

@router.post("/research/report")
def research_report(req: DeepResearchIn) -> dict:
    """调研 + 渲染成自包含 HTML 报告(已消毒)。"""
    from .. import research_deep, visual_report
    result = research_deep.research(req.goal, max_sources=max(1, min(req.max_sources, 8)))
    return {"ok": True, "goal": result.get("goal"), "html": visual_report.render_report(result)}


# ---------- D：版本化文档 ----------

class DocumentIn(BaseModel):
    title: str
    content: str = ""
    kind: str = "doc"
    tags: list[str] = Field(default_factory=list)


class DocEditIn(BaseModel):
    find: str
    replace: str
    count: int = 0


@router.get("/documents")
def documents_list(limit: int = 100) -> dict:
    from .. import documents
    return {"ok": True, "documents": documents.list_docs(limit=limit)}


@router.post("/documents")
def documents_create(req: DocumentIn) -> dict:
    from .. import documents
    return {"ok": True, "document": documents.create(req.title, req.content, kind=req.kind, tags=req.tags)}


@router.get("/documents/{doc_id}")
def documents_get(doc_id: str) -> dict:
    from .. import documents
    d = documents.get(doc_id)
    return {"ok": d is not None, "document": d, "versions": documents.list_versions(doc_id) if d else []}


@router.post("/documents/{doc_id}/edit")
def documents_edit(doc_id: str, req: DocEditIn) -> dict:
    from .. import documents
    return documents.edit_replace(doc_id, req.find, req.replace, count=req.count)


# ---------- B：技能库 ----------

class SkillIn(BaseModel):
    name: str
    when_to_use: str
    body: str = ""
    category: str = "general"
    keywords: list[str] = Field(default_factory=list)
    procedure: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)


@router.get("/skills")
def skills_list(q: str = "", category: str = "") -> dict:
    from .. import skills
    return {"ok": True, "skills": skills.list_skills(q=q, category=category)}


@router.post("/skills")
def skills_create(req: SkillIn) -> dict:
    from .. import skills
    sid = skills.save_skill(req.model_dump(), source="manual")
    return {"ok": sid is not None, "id": sid}


class SkillImportIn(BaseModel):
    # 二选一:贴 SKILL.md 文本,或给 GitHub 仓库 + 路径。
    markdown: str = ""
    repo: str = ""
    path: str = "SKILL.md"
    ref: str = "main"


@router.post("/skills/import")
def skills_import(req: SkillImportIn) -> dict:
    from .. import skills
    if req.markdown.strip():
        return skills.import_markdown(req.markdown)
    if req.repo.strip():
        return skills.import_from_github(req.repo, req.path, req.ref)
    return {"ok": False, "error": "请提供 markdown 文本或 GitHub repo"}


@router.get("/skills/{sid}")
def skills_get(sid: str) -> dict:
    from .. import skills
    s = skills.get_skill(sid)
    return {"ok": s is not None, "skill": s}


class SkillStatusIn(BaseModel):
    status: str = Field(pattern="^(active|archived|deleted)$")


@router.post("/skills/{sid}/status")
def skills_set_status(sid: str, req: SkillStatusIn) -> dict:
    from .. import skills
    return {"ok": skills.set_status(sid, req.status)}


# ---------- WorkDock 合并 M3：下班收尾 / 日报周报 ----------

@router.get("/wrapup/{period}")
def wrapup_build(period: str = "today") -> dict:
    """生成收尾:把今天/本周完成与未完成汇总成日报/周报,每行带来源。"""
    if period not in {"today", "week"}:
        period = "today"
    from .. import wrapup
    return wrapup.build(period)


# ---------- WorkDock 合并 M4：受控执行台(只暴露真实执行数据) ----------

@router.get("/agent-runs")
def agent_runs_overview(hours: int = 48) -> dict:
    """执行台:当前待确认动作(内存)+ 历史执行审计(events kind=action)+ gate 风险判定。"""
    from .. import agent_runs
    return agent_runs.overview(hours=hours)


@router.websocket("/ws/notify")
async def ws_notify(ws: WebSocket):
    if not await _authorize_websocket(ws):
        return
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
    import os as _os

    from ..agent import pty_term

    if not await _authorize_websocket(ws):
        return
    # 纵深防御：/ws/term 会拉起裸登录 shell 与「免确认」agent，等于本机 RCE。
    # 默认只对真实回环直连开放；远程（即便持有合法 token）需运维显式 opt-in。
    client_host = ws.client.host if ws.client else None
    if not is_trusted_local(client_host, ws.headers) and _os.environ.get("LEOJARVIS_ALLOW_REMOTE_TERM", "").strip() not in {"1", "true", "yes"}:
        await ws.accept()
        await ws.send_json({"type": "error", "msg": "交互终端默认仅限本机访问；如需远程使用请在 Mac 端设置 LEOJARVIS_ALLOW_REMOTE_TERM=1。"})
        await ws.close(code=1008)
        return
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
            # 等 pump() 真正结束再关 fd，避免 os.read 与 close(fd) 竞争同一描述符
            try:
                await asyncio.gather(reader_task, return_exceptions=True)
            except Exception:
                pass
        if pid is not None and fd is not None:
            pty_term.kill(pid, fd)
