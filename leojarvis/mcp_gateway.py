from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from . import user_settings


@dataclass(frozen=True)
class MCPServerDef:
    id: str
    name: str
    provider: str
    tier: int
    default_enabled: bool
    optional: bool
    capabilities: tuple[str, ...]
    description: str
    docs_url: str
    auth_env: tuple[str, ...]
    requires_key: bool
    install_hint: str
    read_examples: tuple[str, ...] = ()
    search_examples: tuple[str, ...] = ()


SERVERS: tuple[MCPServerDef, ...] = (
    MCPServerDef(
        id="tavily",
        name="Tavily 搜索/抓取",
        provider="Tavily API / MCP",
        tier=0,
        default_enabled=True,
        optional=False,
        capabilities=("search", "extract", "crawl", "research"),
        description="AI Agent 专用实时搜索、网页抽取、站点爬取和研究任务。Jarvis 只在主信源覆盖不到、用户手动搜索或原文抽取失败时把它当付费兜底。",
        docs_url="https://docs.tavily.com/documentation/mcp",
        auth_env=("TAVILY_API_KEY",),
        requires_key=True,
        install_hint="在环境变量 TAVILY_API_KEY 或 Web 设置页补 Tavily API Key。",
        read_examples=("Tavily Extract: https://api.tavily.com/extract",),
        search_examples=("手动兜底搜索: AI agent latest news",),
    ),
    MCPServerDef(
        id="github_mcp",
        name="GitHub MCP",
        provider="GitHub API / MCP",
        tier=1,
        default_enabled=True,
        optional=True,
        capabilities=("repo_read", "issue_pr", "code_search", "release_summary"),
        description="仓库、Issue、PR、CI 和发布管理。默认只建议内部研发/运维角色使用，OAuth scope 要最小化。",
        docs_url="https://modelscope.cn/mcp/servers/@modelcontextprotocol/github",
        auth_env=("GITHUB_TOKEN", "GH_TOKEN"),
        requires_key=True,
        install_hint="补 GITHUB_TOKEN/GH_TOKEN，或在本机完成 gh auth login。",
        read_examples=("repo(owner/name)", "issues(owner/name)", "pull_requests(owner/name)"),
        search_examples=("code search / repo search",),
    ),
    MCPServerDef(
        id="amap_maps",
        name="高德地图",
        provider="高德 Web 服务",
        tier=2,
        default_enabled=False,
        optional=True,
        capabilities=("place_search", "route_plan", "geo"),
        description="位置、路线、本地生活和到店场景。Jarvis 需要地图能力时再开启。",
        docs_url="https://modelscope.cn/mcp/servers/@amap/amap-maps",
        auth_env=("AMAP_MAPS_API_KEY", "AMAP_API_KEY", "GAODE_API_KEY"),
        requires_key=True,
        install_hint="补 AMAP_MAPS_API_KEY/AMAP_API_KEY 后开启；默认不参与情报扫描。",
        search_examples=("地点搜索: 上海 虹桥 充电站",),
    ),
)


def _settings() -> dict[str, Any]:
    raw = user_settings.load().get("mcp", {})
    return raw if isinstance(raw, dict) else {}


def _server_overrides(server_id: str) -> dict[str, Any]:
    raw = (_settings().get("servers", {}) or {}).get(server_id, {})
    return raw if isinstance(raw, dict) else {}


def _which(binary: str) -> str | None:
    path = shutil.which(binary)
    if path:
        return path
    for folder in (
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.cargo/bin"),
        os.path.expanduser("~/.npm-global/bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ):
        candidate = os.path.join(folder, binary)
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _run(cmd: list[str], timeout: float = 8) -> tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        text = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode == 0, text
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _mcporter_has_alias(alias: str) -> tuple[bool, str, str]:
    mcporter = _which("mcporter")
    if not mcporter:
        return False, "mcporter 未安装", ""
    ok, text = _run([mcporter, "config", "list"], timeout=8)
    if not ok:
        return False, text[:180] or "mcporter 状态异常", mcporter
    if alias.lower() in text.lower():
        return True, f"{alias} MCP alias 已配置", mcporter
    return False, f"mcporter 已安装，但未看到 {alias} alias", mcporter


def _github_key() -> tuple[str, str]:
    for env_name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value, env_name
    gh = _which("gh")
    if gh:
        ok, text = _run([gh, "auth", "token"], timeout=4)
        if ok and text.strip():
            return text.strip(), "gh auth"
    value = str(_server_overrides("github_mcp").get("api_key") or "").strip()
    if value:
        return value, "local settings"
    return "", ""


def _api_key(server: MCPServerDef) -> tuple[str, str]:
    if server.id == "github_mcp":
        return _github_key()
    for env_name in server.auth_env:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value, env_name
    override = _server_overrides(server.id)
    value = str(override.get("api_key") or "").strip()
    if value:
        return value, "local settings"
    return "", ""


def _server_enabled(server: MCPServerDef) -> bool:
    override = _server_overrides(server.id)
    if "enabled" in override:
        return bool(override.get("enabled"))
    return server.default_enabled


def _server_status(server: MCPServerDef) -> dict[str, Any]:
    enabled = _server_enabled(server)
    key, key_source = _api_key(server)
    status = "off"
    message = "已关闭"
    path = server.docs_url

    if enabled:
        if server.id == "tavily":
            status = "ok" if key else "warn"
            message = "Tavily API Key 已配置，可用于搜索和网页抽取。" if key else "待补 TAVILY_API_KEY。当前网页读取会回退到 Jina Reader。"
        elif server.id == "amap_maps":
            status = "ok" if key else "warn"
            message = f"{server.name} key 已配置。" if key else f"待补 {' / '.join(server.auth_env)}。"
        elif server.id == "github_mcp":
            status = "ok" if key else "warn"
            message = "GitHub token/gh auth 已配置。" if key else "待补 GITHUB_TOKEN/GH_TOKEN 或执行 gh auth login。"
        else:
            ok, text, detected = _mcporter_has_alias(server.id)
            status = "ok" if ok else "warn"
            message = text
            path = detected or path

    return {
        "id": server.id,
        "name": server.name,
        "provider": server.provider,
        "tier": server.tier,
        "optional": server.optional,
        "enabled": enabled,
        "status": status,
        "message": message,
        "path": path,
        "key_configured": bool(key),
        "key_source": key_source,
        "auth_env": list(server.auth_env),
        "capabilities": list(server.capabilities),
        "description": server.description,
        "install_hint": server.install_hint,
        "docs_url": server.docs_url,
        "read_examples": list(server.read_examples),
        "search_examples": list(server.search_examples),
    }


def status() -> dict[str, Any]:
    rows = [_server_status(server) for server in SERVERS]
    return {
        "ok": True,
        "generated_at": int(time.time()),
        "summary": {
            "ready": sum(1 for row in rows if row["status"] == "ok"),
            "total": len(rows),
            "needs_key": sum(1 for row in rows if row["status"] == "warn" and row["enabled"]),
            "disabled": sum(1 for row in rows if row["status"] == "off"),
        },
        "servers": rows,
        "policy": {
            "secrets": "优先读取环境变量；Web 设置页保存到本机 data/user_settings.json，不进入 Git。",
            "network": "统一限制超时、内容长度和失败回退；iOS/macOS 不直接嵌入第三方 key。",
            "security": "GitHub MCP 仅用于内部研发/运维角色，OAuth scope 最小化。",
        },
    }


def reach_channels() -> list[dict[str, Any]]:
    rows = []
    for row in status()["servers"]:
        rows.append({
            "id": row["id"],
            "name": row["name"],
            "tier": row["tier"],
            "optional": row["optional"],
            "setup_level": "需要 Key" if row["key_configured"] is False else "可用",
            "status": row["status"],
            "message": row["message"],
            "path": row["path"],
            "backends": [row["provider"]],
            "description": row["description"],
            "install_hint": row["install_hint"],
            "read_examples": row["read_examples"],
            "search_examples": row["search_examples"],
        })
    return rows


def patch_settings(partial: dict[str, Any]) -> dict[str, Any]:
    """Persist non-secret and optional local secret MCP settings.

    The caller decides whether to send an api_key. Empty api_key values are ignored
    so an accidental blank save does not erase an existing local key.
    """
    current = _settings()
    servers = dict(current.get("servers") or {})
    incoming_servers = (partial or {}).get("servers", {}) or {}
    for server_id, patch in incoming_servers.items():
        if not isinstance(patch, dict):
            continue
        existing = dict(servers.get(server_id) or {})
        for key, value in patch.items():
            if key == "api_key" and not str(value or "").strip():
                continue
            existing[key] = value
        servers[server_id] = existing
    next_cfg = {**current, **{k: v for k, v in (partial or {}).items() if k != "servers"}, "servers": servers}
    saved = user_settings.patch({"mcp": next_cfg})
    return saved.get("mcp", next_cfg)


def public_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or _settings())
    servers = {}
    configured = cfg.get("servers", {}) or {}
    for server_def in SERVERS:
        server_id = server_def.id
        server_cfg = configured.get(server_id, {})
        if not isinstance(server_cfg, dict):
            server_cfg = {}
        key = str(server_cfg.get("api_key") or "").strip()
        servers[server_id] = {
            **server_cfg,
            "api_key": "",
            "key_configured": bool(key) or bool(_api_key(server_def)[0]),
        }
    cfg["servers"] = servers
    return cfg


def _post_json(url: str, payload: dict[str, Any], *, api_key: str, timeout: float = 18) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "LeoJarvis-MCPGateway/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def tavily_available() -> tuple[bool, str]:
    server = next(s for s in SERVERS if s.id == "tavily")
    key, _source = _api_key(server)
    return _server_enabled(server) and bool(key), key


def extract_url(url: str, *, limit: int = 12000) -> dict[str, Any]:
    clean = (url or "").strip()
    if not clean:
        raise ValueError("url required")
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    ok, key = tavily_available()
    if not ok:
        raise RuntimeError("Tavily key not configured")
    started = time.time()
    payload = {
        "urls": [clean],
        "extract_depth": "basic",
        "include_images": False,
        "include_favicon": False,
    }
    data = _post_json("https://api.tavily.com/extract", payload, api_key=key, timeout=22)
    results = data.get("results") or []
    if not results:
        failed = data.get("failed_results") or []
        raise RuntimeError(failed[0].get("error") if failed and isinstance(failed[0], dict) else "Tavily extract returned no result")
    first = results[0] if isinstance(results[0], dict) else {}
    text = str(first.get("raw_content") or first.get("content") or "").strip()
    if not text:
        raise RuntimeError("Tavily extract returned empty content")
    return {
        "ok": True,
        "backend": "tavily_extract",
        "url": clean,
        "reader_url": "https://api.tavily.com/extract",
        "duration_ms": int((time.time() - started) * 1000),
        "content": text[:limit],
        "truncated": len(text) > limit,
        "length": len(text),
        "title": first.get("title") or "",
    }


def search_web(query: str, *, limit: int = 8, include_answer: bool = False) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    ok, key = tavily_available()
    if not ok:
        raise RuntimeError("Tavily key not configured")
    started = time.time()
    payload = {
        "query": q,
        "max_results": max(1, min(int(limit or 8), 20)),
        "search_depth": "basic",
        "include_answer": bool(include_answer),
        "include_raw_content": False,
    }
    data = _post_json("https://api.tavily.com/search", payload, api_key=key, timeout=18)
    items = []
    for row in data.get("results") or []:
        if not isinstance(row, dict):
            continue
        items.append({
            "title": row.get("title") or row.get("url") or "",
            "url": row.get("url") or "",
            "content": row.get("content") or "",
            "score": row.get("score"),
        })
    return {
        "ok": True,
        "backend": "tavily_search",
        "query": q,
        "answer": data.get("answer") or "",
        "items": items,
        "duration_ms": int((time.time() - started) * 1000),
    }
