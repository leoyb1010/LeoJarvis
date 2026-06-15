from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
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
    install_hint: str = ""
    read_examples: tuple[str, ...] = ()
    search_examples: tuple[str, ...] = ()
    optional: bool = False


CHANNELS = [
    Channel(
        "github", "GitHub 仓库和代码", 0, ("gh CLI",),
        "读取仓库介绍、topic、release、issue、PR 和搜索结果。",
        "brew install gh && gh auth login",
        ("gh repo view owner/repo --json description,repositoryTopics,latestRelease",),
        ("gh search repos \"AI agent\" --sort stars",),
    ),
    Channel(
        "twitter", "Twitter/X", 1, ("twitter-cli", "bird 备用"),
        "搜索/读取推文、长文、profile 和时间线，需要 Cookie 或浏览器登录。",
        "uv tool install twitter-cli && twitter login",
        ("twitter tweet URL", "twitter user openai"),
        ("twitter search \"AI agent\" -n 10",),
        optional=True,
    ),
    Channel(
        "youtube", "YouTube / 视频字幕", 0, ("yt-dlp",),
        "提取 YouTube、B站等 1800+ 站点的视频元信息和字幕。",
        "brew install yt-dlp",
        ("yt-dlp --dump-json URL", "yt-dlp --write-sub --skip-download URL"),
        ("yt-dlp \"ytsearch10:AI agent tutorial\" --dump-json",),
        optional=True,
    ),
    Channel(
        "reddit", "Reddit", 1, ("rdt-cli",),
        "搜索、阅读帖子全文和评论；Reddit 需要 Cookie 登录。",
        "uv tool install rdt-cli && rdt login",
        ("rdt read POST_ID",),
        ("rdt search \"local llm\" -n 10",),
        optional=True,
    ),
    Channel(
        "bilibili", "B站", 1, ("yt-dlp", "bili-cli", "B站搜索 API"),
        "本地读取视频、字幕、搜索、热门和排行；服务器环境可能需要代理。",
        "brew install yt-dlp && uv tool install bilibili-cli",
        ("yt-dlp --dump-json https://www.bilibili.com/video/BV...",),
        ("bili search \"AI\" --limit 10",),
        optional=True,
    ),
    Channel(
        "xiaohongshu", "小红书", 2, ("xhs-cli",),
        "搜索/阅读笔记、评论、发帖和点赞；建议专用小号 Cookie。",
        "uv tool install xiaohongshu-cli && xhs login",
        ("xhs read NOTE_ID", "xhs comments NOTE_ID"),
        ("xhs search \"AI 效率工具\" -n 10",),
        optional=True,
    ),
    Channel(
        "douyin", "抖音", 2, ("mcporter", "douyin MCP"),
        "解析分享链接、视频信息、无水印下载链接和脚本提取。",
        "mcporter config add douyin --command 'douyin-mcp-server'",
        ("mcporter call 'douyin.parse_douyin_video_info(share_link: \"URL\")'",),
        (),
        optional=True,
    ),
    Channel(
        "linkedin", "LinkedIn", 2, ("Jina Reader", "linkedin MCP"),
        "公开页面可读；profile、公司页和职位搜索需要 LinkedIn MCP。",
        "mcporter config add linkedin --command 'linkedin-mcp-server'",
        ("curl https://r.jina.ai/https://www.linkedin.com/company/...",),
        ("mcporter call 'linkedin.search_jobs(query: \"AI\")'",),
        optional=True,
    ),
    Channel(
        "wechat", "微信公众号", 0, ("Exa MCP", "Camoufox 可选"),
        "搜索并阅读公众号文章全文；优先通过 Exa/Jina 输出 Markdown 证据。",
        "npm install -g mcporter && mcporter config add exa https://mcp.exa.ai/mcp",
        ("curl https://r.jina.ai/URL",),
        ("mcporter call 'exa.search(query: \"微信公众号 AI Agent\")'",),
        optional=True,
    ),
    Channel(
        "weibo", "微博", 1, ("mcporter", "mcp-server-weibo"),
        "热搜、内容/用户/话题搜索、用户动态和评论。",
        "pip install git+https://github.com/Panniantong/mcp-server-weibo.git && mcporter config add weibo --command 'mcp-server-weibo'",
        ("mcporter call 'weibo.get_trendings(limit: 10)'",),
        ("mcporter call 'weibo.search_content(keyword: \"AI\")'",),
        optional=True,
    ),
    Channel(
        "xiaoyuzhou", "小宇宙播客", 1, ("ffmpeg", "Groq Whisper", "transcribe.sh"),
        "下载播客音频并转文字，适合长播客进入个人知识库。",
        "brew install ffmpeg && agent-reach configure groq-key gsk_xxxxx",
        ("bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh URL",),
        (),
        optional=True,
    ),
    Channel(
        "v2ex", "V2EX", 0, ("V2EX public API",),
        "热门帖子、节点帖子、帖子详情、回复和用户信息。",
        "",
        ("curl https://www.v2ex.com/api/topics/hot.json",),
        (),
        optional=True,
    ),
    Channel(
        "xueqiu", "雪球", 1, ("雪球 API", "浏览器 Cookie 可选"),
        "股票行情、搜索股票、热门帖子和热门股票排行。",
        "登录雪球后可用 agent-reach configure --from-browser chrome 导入 Cookie",
        ("https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SH000001",),
        ("搜索股票/主题热帖",),
        optional=True,
    ),
    Channel(
        "rss", "RSS/Atom", 0, ("feedparser",),
        "稳定订阅源采集，适合低噪长期来源。",
        "pip install feedparser",
        ("feedparser.parse(url)",),
        (),
    ),
    Channel(
        "exa_search", "全网语义搜索", 0, ("mcporter", "Exa MCP"),
        "用于比普通 RSS 更主动的主题搜索，无需把结果先写进固定订阅源。",
        "npm install -g mcporter && mcporter config add exa https://mcp.exa.ai/mcp",
        (),
        ("mcporter call 'exa.search(query: \"local AI agent\")'",),
        optional=True,
    ),
    Channel(
        "web", "任意网页", 0, ("Jina Reader",),
        "把 URL 转成 Markdown 全文，适合 Jarvis 保存证据和摘要。",
        "",
        ("curl https://r.jina.ai/https://example.com",),
        (),
    ),
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


def _check_any_binary(candidates: tuple[tuple[str, list[str] | None], ...], timeout: float = 8) -> tuple[str, str, str]:
    missing = []
    for binary, args in candidates:
        status, message, path = _check_binary(binary, args, timeout=timeout)
        if status == "off":
            missing.append(binary)
            continue
        return status, message, path
    return "off", f"未安装 {' / '.join(missing)}", ""


def _mcporter_path() -> str | None:
    return _which("mcporter")


@lru_cache(maxsize=1)
def _mcporter_config_text(timeout: float = 8) -> tuple[str, str, str]:
    mcporter = _mcporter_path()
    if not mcporter:
        return "off", "", ""
    res = _run([mcporter, "config", "list"], timeout=timeout)
    text = (res["stdout"] or res["stderr"]).strip()
    if not res["ok"]:
        return "warn", text[:180] or "mcporter 状态异常", mcporter
    return "ok", text, mcporter


def _check_mcporter_alias(alias: str, *, fallback_aliases: tuple[str, ...] = ()) -> tuple[str, str, str]:
    status, text, path = _mcporter_config_text()
    if status == "off":
        return "off", "mcporter 未安装。需要先 npm install -g mcporter。", ""
    if status == "warn":
        return "warn", text or "mcporter 状态异常", path
    lowered = text.lower()
    aliases = (alias, *fallback_aliases)
    if any(item.lower() in lowered for item in aliases):
        return "ok", f"{alias} MCP 已配置", path
    return "warn", f"mcporter 已安装，但未看到 {alias} MCP alias。", path


def _http_probe(url: str, *, timeout: float = 4) -> tuple[str, str, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LeoJarvis-Reach/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
        if 200 <= int(code) < 400:
            return "ok", "公开 API 可用", "http"
        return "warn", f"公开 API 返回 {code}", "http"
    except Exception as exc:  # noqa: BLE001
        return "warn", f"公开 API 暂不可达：{str(exc)[:120]}", "http"


def _agent_reach_config_value(name: str) -> str:
    config_path = Path.home() / ".agent-reach" / "config.yaml"
    if not config_path.exists():
        return ""
    try:
        text = config_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    for line in text.splitlines():
        if line.strip().startswith(f"{name}:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def _channel_status(channel: Channel) -> tuple[str, str, str]:
    if channel.id == "web":
        return "ok", "通过 https://r.jina.ai 读取网页，无需本地安装。", ""
    if channel.id == "github":
        status, message, path = _check_binary("gh", ["gh", "auth", "status"], timeout=8)
        if status == "warn" and _which("gh"):
            message = "gh 已安装；公开仓库可读，私有仓库/Issue/PR 完整能力需 gh auth login。"
        return status, message, path
    if channel.id == "rss":
        try:
            import feedparser  # noqa: F401
            return "ok", "feedparser 可用", "python"
        except Exception:
            return "off", "feedparser 未安装：pip install feedparser", ""
    if channel.id == "youtube":
        return _check_binary("yt-dlp", ["yt-dlp", "--version"], timeout=8)
    if channel.id == "bilibili":
        status, message, path = _check_binary("yt-dlp", ["yt-dlp", "--version"], timeout=8)
        if status == "off":
            return status, message, path
        bili = _which("bili")
        if bili:
            return "ok", f"yt-dlp 可用；bili-cli 可用：{Path(bili).name}", path
        probe_status, probe_message, _ = _http_probe("https://api.bilibili.com/x/web-interface/search/all/v2?keyword=test&page=1")
        if probe_status == "ok":
            return "ok", "yt-dlp 可用；B站搜索 API 可达；安装 bili-cli 可解锁热门/排行/动态。", path
        return "warn", f"yt-dlp 可用；{probe_message}；安装 bili-cli 可增强搜索。", path
    if channel.id == "exa_search":
        status, text, path = _mcporter_config_text()
        if status == "off":
            return "off", "mcporter 未安装；需要 npm install -g mcporter 并配置 Exa。", ""
        if status == "warn":
            return "warn", text or "mcporter 状态异常", path
        return ("ok", "Exa MCP 已配置", path) if "exa" in text.lower() else ("warn", "mcporter 已安装但未看到 Exa 配置", path)
    if channel.id == "twitter":
        status, message, path = _check_any_binary((
            ("twitter", ["twitter", "status"]),
            ("bird", ["bird", "check"]),
        ), timeout=10)
        if status == "warn":
            return "warn", f"CLI 已安装但需要登录/Cookie：{message}", path
        return status, message, path
    if channel.id == "reddit":
        status, message, path = _check_binary("rdt", ["rdt", "--version"], timeout=8)
        if status == "ok":
            return "ok", f"rdt-cli 已安装：{message}；搜索/全文通常还需 rdt login。", path
        return status, message, path
    if channel.id == "xiaohongshu":
        status, message, path = _check_binary("xhs", ["xhs", "status"], timeout=10)
        if status == "warn":
            return "warn", f"xhs-cli 已安装但需要登录/Cookie：{message}", path
        return status, message, path
    if channel.id == "douyin":
        return _check_mcporter_alias("douyin")
    if channel.id == "linkedin":
        return _check_mcporter_alias("linkedin", fallback_aliases=("linkedin-mcp",))
    if channel.id == "wechat":
        status, message, path = _check_mcporter_alias("exa")
        if status == "ok":
            camoufox = _which("camoufox")
            extra = "；Camoufox 已安装，可增强公众号阅读。" if camoufox else "；Camoufox 可选。"
            return "ok", message + extra, path
        return status, message, path
    if channel.id == "weibo":
        return _check_mcporter_alias("weibo")
    if channel.id == "xiaoyuzhou":
        ffmpeg = _which("ffmpeg")
        if not ffmpeg:
            return "off", "需要 ffmpeg：brew install ffmpeg", ""
        script = Path.home() / ".agent-reach/tools/xiaoyuzhou/transcribe.sh"
        if not script.is_file():
            return "off", "小宇宙转录脚本未安装；运行 agent-reach install 或复制 transcribe.sh。", ffmpeg
        if not os.environ.get("GROQ_API_KEY") and not _agent_reach_config_value("groq_api_key"):
            return "warn", "ffmpeg 和脚本可用；还需要 Groq API Key 才能转录。", ffmpeg
        return "ok", "播客下载 + Whisper 转录可用", ffmpeg
    if channel.id == "v2ex":
        return _http_probe("https://www.v2ex.com/api/topics/hot.json")
    if channel.id == "xueqiu":
        status, message, path = _http_probe("https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SH000001")
        if status == "ok":
            return "ok", "雪球公开行情 API 可用；社区内容需要浏览器 Cookie。", path
        return "warn", message + "；登录雪球并导入 Cookie 后更稳定。", path
    return "off", "未配置", ""


def _setup_level(channel: Channel) -> str:
    if channel.tier == 0:
        return "装好即用"
    if channel.tier == 1:
        return "需登录/免费配置"
    return "需 MCP/Cookie"


def source_matrix() -> list[dict[str, Any]]:
    """Agent-Reach-style source catalog used by the intelligence UI."""
    return [
        {
            "group": "MCP / Agent 工具",
            "channels": ["tavily", "github_mcp", "amap_maps", "exa_search"],
            "use": "实时搜索、网页抓取、GitHub 研发上下文、地图位置和 Agent 工具调用，统一由 Jarvis MCP Gateway 控制。",
        },
        {
            "group": "核心低噪",
            "channels": ["web", "github", "rss", "youtube", "tavily", "exa_search", "wechat", "v2ex"],
            "use": "技术趋势、开源项目、长文、官方发布和可留证据的资料。",
        },
        {
            "group": "社媒口碑",
            "channels": ["twitter", "reddit", "xiaohongshu", "weibo"],
            "use": "真实讨论、开发者反馈、产品口碑和中文社媒信号，通常需要账号/Cookie。",
        },
        {
            "group": "视频/播客",
            "channels": ["youtube", "bilibili", "douyin", "xiaoyuzhou"],
            "use": "视频教程、发布会、播客访谈和短视频脚本，适合转写后进个人记事。",
        },
        {
            "group": "职业/财经",
            "channels": ["linkedin", "xueqiu", "github"],
            "use": "职业机会、公司动态、股票讨论和项目基本面。",
        },
    ]


def channel_status() -> dict[str, Any]:
    rows = []
    with ThreadPoolExecutor(max_workers=min(10, len(CHANNELS))) as pool:
        statuses = list(pool.map(_channel_status, CHANNELS))
    for channel, (status, message, path) in zip(CHANNELS, statuses):

        rows.append({
            "id": channel.id,
            "name": channel.name,
            "tier": channel.tier,
            "optional": channel.optional,
            "setup_level": _setup_level(channel),
            "status": status,
            "message": message,
            "path": path,
            "backends": list(channel.backends),
            "description": channel.description,
            "install_hint": channel.install_hint,
            "read_examples": list(channel.read_examples),
            "search_examples": list(channel.search_examples),
        })
    try:
        from . import mcp_gateway

        existing_ids = {row["id"] for row in rows}
        for channel in mcp_gateway.reach_channels():
            if channel["id"] not in existing_ids:
                rows.append(channel)
                existing_ids.add(channel["id"])
    except Exception as exc:  # noqa: BLE001
        rows.append({
            "id": "mcp_gateway",
            "name": "MCP Gateway",
            "tier": 0,
            "optional": False,
            "setup_level": "状态异常",
            "status": "warn",
            "message": f"MCP Gateway 状态读取失败：{str(exc)[:140]}",
            "path": "",
            "backends": ["Jarvis MCP Gateway"],
            "description": "统一管理 Tavily、GitHub、高德等 MCP/API 能力。",
            "install_hint": "",
            "read_examples": [],
            "search_examples": [],
        })

    ready = sum(1 for row in rows if row["status"] == "ok")
    partial = sum(1 for row in rows if row["status"] == "warn")
    return {
        "ok": True,
        "generated_at": int(time.time()),
        "summary": {
            "ready": ready,
            "total": len(rows),
            "partial": partial,
            "core_ready": sum(1 for row in rows if row["tier"] == 0 and row["status"] == "ok"),
            "core_total": sum(1 for row in rows if row["tier"] == 0),
        },
        "channels": rows,
        "source_matrix": source_matrix(),
    }


def read_url(url: str, limit: int = 12000) -> dict[str, Any]:
    clean = (url or "").strip()
    if not clean:
        raise ValueError("url required")
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    try:
        from . import mcp_gateway

        return mcp_gateway.extract_url(clean, limit=limit)
    except Exception:
        pass
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
