from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _which(binary: str) -> str | None:
    path = shutil.which(binary)
    if path:
        return path
    for folder in (
        Path.home() / ".local/bin",
        Path.home() / ".cargo/bin",
        Path.home() / ".npm-global/bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ):
        candidate = folder / binary
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _run(cmd: list[str], timeout: float = 12) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.time() - started) * 1000),
            "command": " ".join(cmd),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": int((time.time() - started) * 1000),
            "command": " ".join(cmd),
        }


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    tier: int
    backends: tuple[str, ...]
    description: str
    optional: bool = False


CHANNELS = [
    Channel("web", "任意网页", 0, ("Jina Reader",), "把 URL 转成 Markdown 全文，适合 Jarvis 保存证据和摘要。"),
    Channel("github", "GitHub 仓库和代码", 0, ("gh CLI",), "读取仓库介绍、topic、release、issue、PR 和搜索结果。"),
    Channel("rss", "RSS/Atom", 0, ("feedparser",), "稳定订阅源采集。"),
    Channel("youtube", "视频字幕", 0, ("yt-dlp",), "YouTube/B站等视频元信息和字幕提取。", optional=True),
    Channel("exa_search", "全网语义搜索", 0, ("mcporter + Exa MCP",), "用于比普通 RSS 更主动的主题搜索。", optional=True),
    Channel("twitter", "Twitter/X", 1, ("twitter-cli",), "搜索/读取推文、长文和时间线，需要登录凭据。", optional=True),
    Channel("reddit", "Reddit", 1, ("rdt-cli",), "搜索/阅读帖子和评论，需要 Cookie。", optional=True),
    Channel("xiaohongshu", "小红书", 1, ("xhs-cli",), "搜索/阅读笔记，建议专用小号。", optional=True),
    Channel("douyin", "抖音", 2, ("mcporter MCP",), "视频解析与脚本提取。", optional=True),
    Channel("wechat", "微信公众号", 0, ("Exa + Camoufox",), "搜索和阅读公众号文章。", optional=True),
]


def _check_binary(binary: str, args: list[str] | None = None, timeout: float = 6) -> tuple[str, str, str]:
    path = _which(binary)
    if not path:
        return "off", f"未安装 {binary}", ""
    if not args:
        return "ok", f"{binary} 可用", path
    actual_args = [path, *args[1:]] if args and args[0] == binary else args
    res = _run(actual_args, timeout=timeout)
    text = (res["stdout"] or res["stderr"]).strip()
    if res["ok"]:
        return "ok", text.splitlines()[0][:160] if text else f"{binary} 可用", path
    return "warn", text[:180] or f"{binary} 状态异常", path


def channel_status() -> dict[str, Any]:
    rows = []
    for channel in CHANNELS:
        if channel.id == "web":
            status, message, path = "ok", "通过 https://r.jina.ai 读取网页，无需本地安装。", ""
        elif channel.id == "github":
            status, message, path = _check_binary("gh", ["gh", "auth", "status"], timeout=8)
            if status == "warn" and _which("gh"):
                message = "gh 已安装但未认证；公开仓库仍可读取，完整能力需 gh auth login。"
        elif channel.id == "rss":
            try:
                import feedparser  # noqa: F401
                status, message, path = "ok", "feedparser 可用", "python"
            except Exception:
                status, message, path = "off", "feedparser 未安装：pip install feedparser", ""
        elif channel.id == "youtube":
            status, message, path = _check_binary("yt-dlp", ["yt-dlp", "--version"], timeout=8)
        elif channel.id == "exa_search":
            mcporter = _which("mcporter")
            if not mcporter:
                status, message, path = "off", "mcporter 未安装；需要 npm install -g mcporter 并配置 Exa。", ""
            else:
                res = _run([mcporter, "config", "list"], timeout=8)
                status = "ok" if "exa" in (res["stdout"] or "").lower() else "warn"
                message = "Exa MCP 已配置" if status == "ok" else "mcporter 已安装但未看到 Exa 配置"
                path = mcporter
        elif channel.id == "twitter":
            status, message, path = _check_binary("twitter", ["twitter", "status"], timeout=10)
        elif channel.id == "reddit":
            status, message, path = _check_binary("rdt", ["rdt", "--version"], timeout=8)
        elif channel.id == "xiaohongshu":
            status, message, path = _check_binary("xhs", ["xhs", "status"], timeout=10)
        elif channel.id == "douyin":
            status, message, path = _check_binary("mcporter", ["mcporter", "config", "list"], timeout=8)
            if status == "ok" and "douyin" not in message.lower():
                status, message = "warn", "mcporter 可用，但需要配置 douyin MCP alias。"
        elif channel.id == "wechat":
            status, message, path = _check_binary("mcporter", ["mcporter", "config", "list"], timeout=8)
            if status == "ok" and "exa" not in message.lower():
                status, message = "warn", "需要 Exa MCP；可选安装 Camoufox 增强公众号阅读。"
        else:
            status, message, path = "off", "未配置", ""

        rows.append({
            "id": channel.id,
            "name": channel.name,
            "tier": channel.tier,
            "optional": channel.optional,
            "status": status,
            "message": message,
            "path": path,
            "backends": list(channel.backends),
            "description": channel.description,
        })

    ready = sum(1 for row in rows if row["status"] == "ok")
    return {
        "ok": True,
        "generated_at": int(time.time()),
        "summary": {
            "ready": ready,
            "total": len(rows),
            "core_ready": sum(1 for row in rows if row["tier"] == 0 and row["status"] == "ok"),
            "core_total": sum(1 for row in rows if row["tier"] == 0),
        },
        "channels": rows,
    }


def read_url(url: str, limit: int = 12000) -> dict[str, Any]:
    clean = (url or "").strip()
    if not clean:
        raise ValueError("url required")
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    reader_url = "https://r.jina.ai/" + clean
    req = urllib.request.Request(
        reader_url,
        headers={
            "User-Agent": "LeoJarvis-Reach/0.1",
            "Accept": "text/plain",
        },
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=24) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return {
        "ok": True,
        "url": clean,
        "reader_url": reader_url,
        "duration_ms": int((time.time() - started) * 1000),
        "content": text[:limit],
        "truncated": len(text) > limit,
        "length": len(text),
    }


def github_repo(owner_repo: str) -> dict[str, Any]:
    repo = (owner_repo or "").strip()
    if repo.startswith("https://github.com/"):
        parts = urllib.parse.urlparse(repo).path.strip("/").split("/")
        if len(parts) >= 2:
            repo = f"{parts[0]}/{parts[1]}"
    if "/" not in repo:
        raise ValueError("repo must be owner/name")
    fields = (
        "nameWithOwner,description,stargazerCount,forkCount,licenseInfo,isArchived,"
        "pushedAt,updatedAt,latestRelease,url,repositoryTopics,primaryLanguage,openGraphImageUrl"
    )
    res = _run(["gh", "repo", "view", repo, "--json", fields], timeout=18)
    if not res["ok"]:
        return {"ok": False, "repo": repo, "error": (res["stderr"] or res["stdout"])[:800]}
    data = json.loads(res["stdout"])
    topics = [item.get("name", "") for item in data.get("repositoryTopics", []) if item.get("name")]
    release = data.get("latestRelease") or {}
    language = data.get("primaryLanguage") or {}
    return {
        "ok": True,
        "repo": repo,
        "summary": {
            "name": data.get("nameWithOwner") or repo,
            "description": data.get("description") or "",
            "stars": data.get("stargazerCount") or 0,
            "forks": data.get("forkCount") or 0,
            "language": language.get("name") if isinstance(language, dict) else "",
            "topics": topics,
            "license": (data.get("licenseInfo") or {}).get("name") if isinstance(data.get("licenseInfo"), dict) else "",
            "latest_release": release.get("tagName") if isinstance(release, dict) else "",
            "latest_release_name": release.get("name") if isinstance(release, dict) else "",
            "pushed_at": data.get("pushedAt") or "",
            "updated_at": data.get("updatedAt") or "",
            "url": data.get("url") or f"https://github.com/{repo}",
        },
    }


def github_search(query: str, limit: int = 10) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    res = _run(["gh", "search", "repos", q, "--sort", "stars", "--limit", str(max(1, min(limit, 30))), "--json", "fullName,description,language,stargazersCount,url,updatedAt"], timeout=24)
    if not res["ok"]:
        return {"ok": False, "query": q, "error": (res["stderr"] or res["stdout"])[:800], "items": []}
    return {"ok": True, "query": q, "items": json.loads(res["stdout"])}
