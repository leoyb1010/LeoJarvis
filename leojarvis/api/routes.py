from __future__ import annotations

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


@router.get("/health")
async def health() -> dict:
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
    proxy_command: str = ""
    ssh_options: list[str] = Field(default_factory=list)


class RemoteLeoJarvisIn(BaseModel):
    name: str = ""
    host: str
    user: str = ""
    ssh_port: int = 22
    remote_port: int = 8787
    local_port: int | None = None
    enabled: bool = True
    proxy_command: str = ""
    ssh_options: list[str] = Field(default_factory=list)


class SettingsIn(BaseModel):
    settings: dict = Field(default_factory=dict)


class TerminalSessionIn(BaseModel):
    tool_id: str
    cwd: str = ""


class TerminalWriteIn(BaseModel):
    text: str = ""


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
    return {"ok": True, "device": remote_status.add_host(host=req.host, name=req.name, user=req.user, port=req.port, enabled=req.enabled, proxy_command=req.proxy_command, ssh_options=req.ssh_options)}


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
    rows = remote_cortex.list_connections(auto_connect=False)
    remote_cortex.ensure_enabled_connections_async(rows)
    return rows


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
    res = remote_cortex.fetch(connection_id, "/cockpit/overview", auto_connect=False, timeout=5, reconnect=False)
    if not res.get("ok"):
        remote_cortex.connect_async(connection_id)
    return res


@router.get("/remote-cortex/{connection_id}/system")
def remote_cortex_system(connection_id: str) -> dict:
    from .. import remote_cortex
    res = remote_cortex.fetch(connection_id, "/system/overview", auto_connect=False, timeout=5, reconnect=False)
    if not res.get("ok"):
        remote_cortex.connect_async(connection_id)
    return res


@router.get("/remote-cortex/{connection_id}/health")
def remote_cortex_health(connection_id: str) -> dict:
    from .. import remote_cortex
    res = remote_cortex.fetch(connection_id, "/health", auto_connect=False, timeout=3, reconnect=False)
    if not res.get("ok"):
        remote_cortex.connect_async(connection_id)
    return res


@router.post("/remote-cortex/{connection_id}/terminal/sessions")
def remote_terminal_create(connection_id: str, req: TerminalSessionIn) -> dict:
    from .. import remote_cortex
    return remote_cortex.request(connection_id, "POST", "/terminal/sessions", json_data=req.model_dump())


@router.get("/remote-cortex/{connection_id}/terminal/sessions/{session_id}/read")
def remote_terminal_read(connection_id: str, session_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.request(connection_id, "GET", f"/terminal/sessions/{session_id}/read")


@router.post("/remote-cortex/{connection_id}/terminal/sessions/{session_id}/write")
def remote_terminal_write(connection_id: str, session_id: str, req: TerminalWriteIn) -> dict:
    from .. import remote_cortex
    return remote_cortex.request(connection_id, "POST", f"/terminal/sessions/{session_id}/write", json_data=req.model_dump())


@router.delete("/remote-cortex/{connection_id}/terminal/sessions/{session_id}")
def remote_terminal_close(connection_id: str, session_id: str) -> dict:
    from .. import remote_cortex
    return remote_cortex.request(connection_id, "DELETE", f"/terminal/sessions/{session_id}")


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


import threading as _threading

_DEVICE_REFRESH_LOCK = _threading.Lock()
_device_refreshing = False


def _refresh_remote_device_summaries() -> None:
    """后台抓取已连接远端的 /device/summary 并写入心跳，不阻塞 /devices 响应。"""
    global _device_refreshing
    try:
        from concurrent.futures import ThreadPoolExecutor
        from .. import remote_cortex
        connections = remote_cortex.list_connections(auto_connect=False)
        connected = [c for c in connections if c.get("enabled", True) and c.get("connected")]
        if not connected:
            return

        def _one(conn: dict) -> None:
            conn_id = str(conn.get("id") or "")
            try:
                res = remote_cortex.fetch(conn_id, "/device/summary", auto_connect=True, timeout=12.0, reconnect=True)
                if res.get("ok") and res.get("data"):
                    s = dict(res["data"])
                    s["device_id"] = conn_id
                    s["device_name"] = conn.get("name") or s.get("device_name") or conn.get("host")
                    s["host_name"] = s.get("host_name") or conn.get("host")
                    s["role"] = "remote-leojarvis"
                    db.upsert_device_heartbeat(s)
                elif res.get("error"):
                    print(f"[devices] remote summary failed: {conn.get('name') or conn_id}: {res.get('error')}")
            except Exception as exc:
                print(f"[devices] remote summary error: {conn.get('name') or conn_id}: {exc}")

        with ThreadPoolExecutor(max_workers=min(4, len(connected))) as pool:
            list(pool.map(_one, connected))
    finally:
        with _DEVICE_REFRESH_LOCK:
            globals()["_device_refreshing"] = False


def _remote_device_placeholder(conn: dict, *, now: int, online: bool, error: str = "") -> dict:
    status = "连接中" if online else "离线"
    level = "注意" if online else "异常"
    advice = "远端 LeoJarvis 已连接，正在刷新设备摘要。" if online else (error or "远端 LeoJarvis 暂未响应。")
    return {
        "device_id": str(conn.get("id") or ""),
        "device_name": str(conn.get("name") or conn.get("host") or "远程 LeoJarvis"),
        "host_name": str(conn.get("host") or ""),
        "model": "远程 Mac",
        "role": "remote-leojarvis",
        "generated_at": now,
        "last_seen_ts": now if online else 0,
        "health": 72 if online else 0,
        "status": status,
        "metrics": {},
        "modules": {},
        "services": {"online": 0, "total": 0},
        "risks": [{"title": status, "advice": advice[:180], "level": level}],
        "privacy": "远端设备只显示连接态和健康摘要，不读取个人内容。",
        "age_seconds": 0 if online else now,
        "online": online,
    }


def _apply_remote_device_states(rows: list[dict], connections: list[dict], *, now: int) -> list[dict]:
    by_id = {str(row.get("device_id") or ""): row for row in rows}
    remote_by_id = {str(conn.get("id") or ""): conn for conn in connections if conn.get("enabled", True)}
    for row in rows:
        # last_seen_ts=0 表示「从未成功采集」（如 SSH 探测失败），不能回退到
        # generated_at，否则失败心跳会被当成刚刚在线。
        last_seen = int(row.get("last_seen_ts") or 0)
        age = max(0, now - last_seen) if last_seen else now
        row["age_seconds"] = age
        device_id = str(row.get("device_id") or "")
        remote_conn = remote_by_id.get(device_id)
        if remote_conn:
            is_connected = bool(remote_conn.get("connected")) and not bool(remote_conn.get("last_error"))
            row["online"] = is_connected
            if not is_connected:
                row["status"] = "离线"
                row["health"] = min(float(row.get("health") or 0), 40)
                risks = list(row.get("risks") or [])
                risks.insert(0, {
                    "title": "远端 LeoJarvis 未响应",
                    "advice": str(remote_conn.get("last_error") or "正在后台重连。")[:180],
                    "level": "异常",
                })
                row["risks"] = risks[:4]
        else:
            row["online"] = age < 180
    for conn in connections:
        cid = str(conn.get("id") or "")
        if conn.get("enabled", True) and cid and cid not in by_id:
            online = bool(conn.get("connected")) and not bool(conn.get("last_error"))
            rows.append(_remote_device_placeholder(conn, now=now, online=online, error=str(conn.get("last_error") or "")))
    return rows


@router.get("/devices")
def devices(limit: int = 50) -> list[dict]:
    from ..agent import sysinfo
    from .. import remote_cortex
    global _device_refreshing
    local = sysinfo.device_summary()
    db.upsert_device_heartbeat(local)
    now = int(time.time())
    connections = remote_cortex.list_connections(auto_connect=False)
    refreshed_connections = list(connections)
    stale_checks: list[tuple[int, str, dict]] = []
    # 设备页需要真实 LeoJarvis HTTP 状态：只看 SSH 本地端口会产生“假在线、设备离线”。
    for idx, conn in enumerate(connections):
        cid = str(conn.get("id") or "")
        if not cid:
            continue
        if not conn.get("enabled", True):
            db.delete_device_heartbeat(cid)
            continue
        last_health_ts = int(conn.get("last_health_ts") or 0)
        if not (conn.get("connected") and last_health_ts and now - last_health_ts < 60):
            stale_checks.append((idx, cid, conn))
    if stale_checks:
        from concurrent.futures import ThreadPoolExecutor

        def _check(item: tuple[int, str, dict]) -> tuple[int, dict | None]:
            idx, cid, conn = item
            try:
                return idx, remote_cortex.validate_connection(cid, timeout=3.0, reconnect_async=True)
            except Exception as exc:
                print(f"[devices] remote health validation failed: {conn.get('name') or cid}: {exc}")
                return idx, None

        with ThreadPoolExecutor(max_workers=min(4, len(stale_checks))) as pool:
            for idx, checked in pool.map(_check, stale_checks):
                if checked:
                    refreshed_connections[idx] = checked
    connections = refreshed_connections
    # 远端摘要后台刷新（去重，单线程在跑就不再开），下一次轮询即更新——不阻塞首屏。
    with _DEVICE_REFRESH_LOCK:
        if not _device_refreshing:
            _device_refreshing = True
            _threading.Thread(target=_refresh_remote_device_summaries, daemon=True).start()
    rows = db.list_device_heartbeats(limit=limit)
    rows = _purge_ghost_devices(rows, local_id=str(local.get("device_id") or ""), connections=connections)
    rows = _apply_remote_device_states(rows, connections, now=now)
    rows = _merge_remote_control_channels(rows, connections)
    return sorted(rows, key=lambda r: (not r.get("online"), -(float(r.get("health") or 0)), -int(r.get("last_seen_ts") or 0)))


def _hostname_key(row: dict) -> str:
    raw = str(row.get("reported_hostname") or row.get("host_name") or "")
    return raw.split(".")[0].strip().lower()


def _merge_remote_control_channels(rows: list[dict], connections: list[dict]) -> list[dict]:
    """同一台物理机器的「SSH 健康卡」和「远控通道卡」合并成一张。

    Mac Studio 既被 SSH 健康监控（ssh-mac-studio）又是远控实例（rc-*），
    分开显示让用户以为有两台机器、其中一台永远连不上。按远端上报的
    hostname 配对（配对结果持久化到连接配置），远控状态变成设备卡上的
    一个通道徽标；直连 SSH 不可达但远控隧道在线时，设备显示在线并标注。
    """
    from .. import remote_cortex

    physical = [r for r in rows if r.get("role") != "remote-leojarvis"]
    channels = [r for r in rows if r.get("role") == "remote-leojarvis"]
    conn_by_id = {str(c.get("id") or ""): c for c in connections}
    out = list(physical)
    for ch in channels:
        ch_id = str(ch.get("device_id") or "")
        conn = conn_by_id.get(ch_id, {})
        linked_id = str(conn.get("linked_device_id") or "")
        target = next((p for p in physical if linked_id and str(p.get("device_id")) == linked_id), None)
        if target is None:
            key = _hostname_key(ch)
            target = next((p for p in physical if key and _hostname_key(p) == key), None)
            if target is not None and ch_id:
                try:
                    remote_cortex.set_link(ch_id, str(target.get("device_id") or ""))
                except Exception:
                    pass
        if target is None:
            out.append(ch)
            continue
        channel_online = bool(ch.get("online"))
        target["remote_control"] = {
            "id": ch_id,
            "name": ch.get("device_name"),
            "connected": channel_online,
            "error": "" if channel_online else str((conn.get("last_error") or "未连接"))[:160],
        }
        if not target.get("online") and channel_online:
            # 直连 SSH 不可达，但远控隧道活着：用通道遥测点亮设备卡。
            target["online"] = True
            target["status"] = ch.get("status") or "健康"
            target["health"] = max(float(target.get("health") or 0), float(ch.get("health") or 0))
            if ch.get("metrics"):
                target["metrics"] = ch["metrics"]
            if ch.get("services"):
                target["services"] = ch["services"]
            if ch.get("last_seen_ts"):
                target["last_seen_ts"] = ch["last_seen_ts"]
                target["age_seconds"] = max(0, int(time.time()) - int(ch["last_seen_ts"]))
            risks = [r for r in (target.get("risks") or []) if r.get("title") != "SSH 未连接"]
            risks.insert(0, {
                "title": "直连 SSH 不可达，已走远控通道",
                "advice": "Tailscale/直连路径当前不通；设备数据来自 SSH 隧道遥测。",
                "level": "注意",
            })
            target["risks"] = risks[:4]
    return out


def _purge_ghost_devices(rows: list[dict], *, local_id: str, connections: list[dict]) -> list[dict]:
    """只保留「本机 + 已配置 SSH 设备 + 已配置远程 LeoJarvis」的心跳。

    设备 ID 体系迁移（裸 id → ssh-{id}）和删除主机都会留下旧心跳行，它们的
    last_seen 永远不再更新，在设备页上变成一排「离线」幽灵卡。这里按当前配置
    过滤，并把数据库里的孤儿行直接删掉。
    """
    from .. import remote_status

    allowed: set[str] = {local_id}
    for host in remote_status.configured_hosts():
        allowed.add(remote_status.device_id_for(host))
    for conn in connections:
        cid = str(conn.get("id") or "")
        if cid:
            allowed.add(cid)
    kept: list[dict] = []
    for row in rows:
        device_id = str(row.get("device_id") or "")
        if device_id in allowed:
            kept.append(row)
            continue
        # 其它 LeoJarvis 实例主动上报的心跳（role=mac，POST /devices/heartbeat）
        # 不在本机配置里，按新鲜度保留：7 天内见过就显示，过期才清。
        role = str(row.get("role") or "")
        last_seen = int(row.get("last_seen_ts") or 0)
        if role not in {"ssh", "remote-leojarvis"} and last_seen and time.time() - last_seen < 7 * 86400:
            kept.append(row)
            continue
        try:
            db.delete_device_heartbeat(device_id)
        except Exception:
            pass
    return kept


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


@router.get("/terminal/sessions")
def terminal_sessions() -> list[dict]:
    from .. import terminal_sessions as terms
    return terms.list_sessions()


@router.post("/terminal/sessions")
def terminal_session_create(req: TerminalSessionIn) -> dict:
    from .. import terminal_sessions as terms
    return terms.create(req.tool_id, cwd=req.cwd)


@router.get("/terminal/sessions/{session_id}/read")
def terminal_session_read(session_id: str) -> dict:
    from .. import terminal_sessions as terms
    return terms.read(session_id)


@router.post("/terminal/sessions/{session_id}/write")
def terminal_session_write(session_id: str, req: TerminalWriteIn) -> dict:
    from .. import terminal_sessions as terms
    return terms.write(session_id, req.text)


@router.delete("/terminal/sessions/{session_id}")
def terminal_session_close(session_id: str) -> dict:
    from .. import terminal_sessions as terms
    return terms.close(session_id)


@router.get("/system/notifications")
def system_notifications() -> dict:
    from ..agent import sysinfo
    return sysinfo.local_notifications()


@router.get("/system/weather")
def system_weather(lat: float | None = None, lon: float | None = None, city: str | None = None) -> dict:
    from ..agent import sysinfo
    return sysinfo.weather(latitude=lat, longitude=lon, city=city)


@router.get("/device-ops/status")
def device_ops_status() -> dict:
    from .. import device_ops
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


@router.get("/personal-notes")
def personal_note_list(q: str = "", tag: str = "", status: str = "active", project: str = "") -> dict:
    from .. import personal_notes
    return {
        "ok": True,
        "notes": personal_notes.list_notes(q=q, tag=tag, status=status, project=project),
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
