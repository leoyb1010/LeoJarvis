from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus

import feedparser
import httpx
import trafilatura

from .. import db
from ..config import settings, sources
from ..ingest.base import RawItem
from ..ingest.rss import x_monitor_feeds
from ..judge.engine import Judgment, judge_and_store
from ..localize import has_noisy_english, to_chinese
from ..memory.profile import profile_terms
from ..memory.store import remember_event
from ..notify.hub import hub

USER_AGENT = "LeoJarvis-Intelligence/0.1 (+https://github.com/leoyb1010/LeoJarvis)"
_SCAN_LOCK = threading.Lock()

# GitHub 搜索 API 未认证只有 10 次/分钟；雷达每轮最多 10 条查询，容易顶到限额。
# 本机有 token 就带上（env 或 `gh auth token`），认证后升到 30 次/分钟。缓存避免每次扫描都 fork gh。
_GITHUB_TOKEN_CACHE: dict[str, Any] = {"ts": 0.0, "token": None}
_GITHUB_TOKEN_TTL = 600.0


def _github_token() -> str:
    import os
    import subprocess

    now = time.time()
    if now - float(_GITHUB_TOKEN_CACHE.get("ts", 0)) < _GITHUB_TOKEN_TTL:
        return str(_GITHUB_TOKEN_CACHE.get("token") or "")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        try:
            out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=4)
            token = out.stdout.strip() if out.returncode == 0 else ""
        except Exception:
            token = ""
    _GITHUB_TOKEN_CACHE["ts"] = now
    _GITHUB_TOKEN_CACHE["token"] = token
    return token


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rowdict(row: Any) -> dict:
    return dict(row) if row is not None else {}


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _clean_text(text: str, limit: int = 6000) -> str:
    compact = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    compact = " ".join(compact.split())
    return compact[:limit]


_TOPIC_LABELS = {
    "ai": "AI",
    "ai-agent": "AI 智能体",
    "ai-agents": "AI 智能体",
    "agent": "智能体",
    "agents": "智能体",
    "agentic": "智能体",
    "agentic-ai": "智能体 AI",
    "agentic-skills": "智能体技能",
    "ai-skills": "AI 技能",
    "ai-coding": "AI 编程",
    "coding-agent": "编程智能体",
    "coding-agents": "编程智能体",
    "personal-assistant": "个人助理",
    "desktop-assistant": "桌面助理",
    "local-first": "本地优先",
    "local-ai": "本地 AI",
    "llm": "大语言模型",
    "llms": "大语言模型",
    "mcp": "MCP",
    "mcp-server": "MCP 服务",
    "mcp-servers": "MCP 服务",
    "workflow": "工作流",
    "workflow-automation": "工作流自动化",
    "automation": "自动化",
    "browser-automation": "浏览器自动化",
    "developer-tools": "开发者工具",
    "devtools": "开发者工具",
    "claude-code": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
    "ollama": "Ollama",
    "rag": "RAG",
    "memory": "记忆",
    "skills": "技能",
    "tools": "工具",
    "workflows": "工作流",
    "assistant": "个人助理",
    "personal": "个人",
    "desktop": "桌面",
    "infra": "基础设施",
    "knowledge-base": "知识库",
    "open-source": "开源",
    "multimodal": "多模态",
    "research": "研究",
    "benchmark": "基准测试",
}


def _clean_topic_label(topic: str) -> str:
    raw = str(topic or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"^英文来源摘要[:：]\s*", "", raw)
    raw = raw.replace("_", "-").replace(" ", "-")
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    lower = raw.lower()
    if lower in _TOPIC_LABELS:
        return _TOPIC_LABELS[lower]
    parts = [p for p in re.split(r"[-/]+", lower) if p]
    labels = [_TOPIC_LABELS[p] for p in parts if p in _TOPIC_LABELS]
    if labels:
        uniq = list(dict.fromkeys(labels))
        if "智能体" in uniq and "技能" in uniq:
            return "智能体技能"
        if "智能体" in uniq and "工具" in uniq:
            return "智能体工具"
        if "AI" in uniq and "编程" in uniq:
            return "AI 编程"
        if "AI" in uniq and "智能体" in uniq:
            return "AI 智能体"
        if "工作流" in uniq and "自动化" in uniq:
            return "工作流自动化"
        return uniq[0]
    if re.search(r"[\u3400-\u9fff]", raw) and len(raw) <= 18:
        return raw
    # 仓库 topic 通常是英文 slug。不能稳定中文化时直接丢弃，避免“英文来源摘要”污染驾驶舱。
    return ""


def _repo_topic_tags(topics: list[str] | str | None, language: str | None = None, limit: int = 6) -> list[str]:
    if isinstance(topics, str):
        topics = _json_loads(topics, [])
    if not isinstance(topics, list):
        topics = []
    tags: list[str] = []
    composite_parts = {
        "AI 智能体": {"AI", "智能体"},
        "智能体技能": {"智能体", "技能"},
        "智能体工具": {"智能体", "工具"},
        "AI 编程": {"AI", "编程"},
        "工作流自动化": {"工作流", "自动化"},
    }
    for topic in topics:
        label = _clean_topic_label(str(topic))
        if not label:
            continue
        if any(label in parts for existing, parts in composite_parts.items() if existing in tags):
            continue
        if label in composite_parts:
            tags = [tag for tag in tags if tag not in composite_parts[label]]
        if label not in tags:
            tags.append(label)
        if len(tags) >= limit:
            break
    if language and language not in tags and len(tags) < limit:
        tags.append(str(language))
    return tags[:limit]


def _repo_summary_zh(name: str, description: str | None, topics: list[str] | None, language: str | None) -> str:
    raw = _clean_text(description or "", limit=500)
    translated = to_chinese(raw, context="GitHub 项目中文介绍", max_chars=220, allow_llm=False) if raw else ""
    if translated and "英文来源摘要" not in translated and not translated.startswith("中文摘要：") and not has_noisy_english(translated):
        return translated
    if raw:
        topic_tags = _repo_topic_tags(topics, language, limit=3)
        prefix = f"{name}：{raw[:260]}"
        if topic_tags:
            prefix += f"。主题：{'、'.join(topic_tags)}"
        return prefix
    tags = _repo_topic_tags(topics, language, limit=4)
    focus = "、".join(tags[:4])
    if not focus:
        focus = f"{language} 生态" if language else "AI 与开发工具生态"
    return f"{name}：仓库暂未提供 description。已按语言、主题和增长信号归入 {focus} 方向，需打开 README 判断实际用途。"


def _repo_reason_zh(repo: dict, velocity: dict, score: float, reasons: list[str]) -> str:
    stars = int(repo.get("stargazers_count") or repo.get("stars") or 0)
    speed = velocity.get("stars_per_day") or velocity.get("cold_stars_per_day")
    pushed = repo.get("pushed_at") or repo.get("updated_at") or ""
    speed_text = f"实测约 {speed}/天" if speed is not None else "首次观察，按 star 基数、创建时间和最近活跃度估算"
    reason_text = "；".join(to_chinese(str(r), context="GitHub 推荐理由", max_chars=80, allow_llm=False) for r in reasons[:3])
    return f"星标 {stars:,}，增长动量{speed_text}，综合评分 {score:.2f}。{reason_text or '项目活跃度和相关性达到雷达阈值。'} 最近更新时间：{pushed[:10] or '未知'}。"


def _repo_relation_zh(repo: dict, query: str) -> str:
    language = repo.get("language") or "未知语言"
    return f"它与 LeoJarvis 的个人助理、本地 AI、Agent 工作流或开发工具链方向相关；雷达命中的关注词是“{to_chinese(query, context='GitHub 搜索词', max_chars=80, allow_llm=False)}”，主要技术栈为 {language}。"


def _repo_next_step_zh(repo: dict) -> str:
    name = repo.get("full_name") or repo.get("repo_full_name") or "这个项目"
    return f"打开 {name} 的 README、示例和最近提交，重点判断三点：是否能本地部署、是否有可复用架构、是否值得加入持续监控或个人记事。"


def _github_analysis(repo: dict, query: str, velocity: dict, score: float, reasons: list[str]) -> dict:
    name = repo.get("full_name") or repo.get("repo_full_name") or "GitHub 项目"
    topics = repo.get("topics") or []
    if isinstance(topics, str):
        topics = _json_loads(topics, [])
    summary = _repo_summary_zh(name, repo.get("description") or "", topics, repo.get("language"))
    stars = int(repo.get("stargazers_count") or repo.get("stars") or 0)
    forks = int(repo.get("forks_count") or repo.get("forks") or 0)
    speed = velocity.get("stars_per_day") or velocity.get("cold_stars_per_day")
    metric = f"星标 {stars:,}；Fork {forks:,}；语言 {repo.get('language') or '未知'}"
    if speed is not None:
        metric += f"；动量约 {speed}/天"
    return {
        "title_zh": f"{name} · GitHub 高增速项目",
        "summary": summary,
        "take": f"{summary}\n{metric}",
        "detail": f"仓库介绍：{summary}\n项目指标：{metric}\n雷达查询：{to_chinese(query, context='GitHub 搜索词', max_chars=80, allow_llm=False)}",
        "why": _repo_reason_zh(repo, velocity, score, reasons),
        "relation": _repo_relation_zh(repo, query),
        "next_step": _repo_next_step_zh(repo),
    }


def _event_day() -> str:
    return datetime.now().strftime("%Y-%m-%d")


_X_HIGH_SIGNAL_TERMS = (
    "model", "release", "launch", "api", "agent", "benchmark", "research", "paper",
    "open source", "weights", "coding", "developer", "deep research", "multimodal",
    "模型", "发布", "上线", "开源", "权重", "基准", "研究", "智能体", "开发者", "多模态",
)

_NEWS_HIGH_SIGNAL_TERMS = (
    "AI", "Agent", "LLM", "OpenAI", "Claude", "Gemini", "DeepSeek", "NVIDIA", "NVDA",
    "MCP", "本地", "模型", "智能体", "开源", "开发者", "自动化", "芯片", "算力", "监管", "美股",
)


def _x_score(title: str, content: str) -> tuple[float, list[str]]:
    text = f"{title}\n{content}".lower()
    hits = [term for term in _X_HIGH_SIGNAL_TERMS if term.lower() in text]
    score = min(0.9, 0.48 + 0.09 * len(hits))
    reasons = [f"命中 X 科技信号：{term}" for term in hits[:4]]
    if not reasons:
        reasons = ["来自 X AI/科技监控源"]
    return round(score, 3), reasons


def _store_x_item_sync(item: RawItem) -> tuple[str | None, Judgment | None, dict | None]:
    score, reasons = _x_score(item.title, item.content)
    triage = "notify" if score >= 0.76 else "digest" if score >= 0.42 else "ignore"
    source_name = str(item.meta.get("feed_name") or item.source).replace("X · ", "")
    summary = to_chinese(item.content or item.title, context="X 监控中文摘要", max_chars=220, allow_llm=False)
    analysis = {
        "title_zh": to_chinese(item.title, context="X 监控标题", max_chars=120, allow_llm=False),
        "summary": summary,
        "take": f"{source_name} 的动态进入 X 监控：{summary}",
        "why": "这类官方或核心开发者动态适合捕捉模型发布、产品更新、研究方向和开发工具变化。",
        "relation": "与 LeoJarvis 关注的 AI Agent、本地助理、模型生态和开发工具链相关。",
        "next_step": "打开原帖确认上下文；如果涉及模型发布、工具升级或重要观点，再加入个人记事或持续关注项。",
    }
    event_id = db.insert_event(
        source=item.source,
        domain=item.domain,
        kind=item.kind,
        title=item.title,
        content=item.content,
        url=item.url,
        meta=item.meta,
        dedup_key=item.dedup_key,
    )
    if event_id is None:
        return None, None, None
    db.insert_judgment(event_id=event_id, score=score, take=analysis["take"], triage=triage, reasons=reasons, analysis=analysis)
    judgment = Judgment(score=score, take=analysis["take"], triage=triage, reasons=reasons, analysis=analysis)
    if triage == "notify":
        return event_id, judgment, {
            "type": "notify",
            "source": "X Monitor",
            "event_id": event_id,
            "title": item.title,
            "take": analysis["take"],
            "url": item.url,
            "score": score,
        }
    return event_id, judgment, None


async def _store_x_item(item: RawItem) -> tuple[str | None, Judgment | None]:
    event_id, judgment, payload = await asyncio.to_thread(_store_x_item_sync, item)
    if payload:
        await hub.push(payload)
    return event_id, judgment


def _news_score(title: str, content: str) -> tuple[float, list[str]]:
    text = f"{title}\n{content}"
    lowered = text.lower()
    profile_hits = [term for term in sorted(profile_terms()) if term and len(term) >= 2 and term.lower() in lowered][:5]
    keyword_hits = [term for term in _NEWS_HIGH_SIGNAL_TERMS if term.lower() in lowered][:5]
    hits = list(dict.fromkeys(profile_hits + keyword_hits))
    score = min(0.92, 0.38 + 0.08 * len(hits))
    reasons = [f"命中关注信号：{term}" for term in hits[:4]]
    if not reasons:
        reasons = ["来自已配置资讯源"]
    return round(score, 3), reasons


def _store_news_item_sync(item: RawItem) -> tuple[str | None, Judgment | None, dict | None]:
    score, reasons = _news_score(item.title, item.content)
    triage = "notify" if score >= 0.76 else "digest" if score >= 0.42 else "ignore"
    summary = to_chinese(item.content or item.title, context="资讯简报摘要", max_chars=240, allow_llm=False)
    source_name = str(item.meta.get("feed_name") or item.source).replace("RSS · ", "")
    analysis = {
        "title_zh": to_chinese(item.title, context="资讯简报标题", max_chars=120, allow_llm=False),
        "summary": summary,
        "take": f"{source_name} 的资讯进入简报：{summary}",
        "why": "该条资讯命中你的 AI、开发工具、市场或个人助理相关关注信号，适合进入今日判断。",
        "relation": "与 LeoJarvis 的 AI 助理建设、技术趋势观察或当前投资关注有关。",
        "next_step": "打开详情确认原文上下文；如果对项目设计、投资判断或个人工作有用，再写入个人记事或加入持续关注。",
        "detail": item.content[:1200],
    }
    event_id = db.insert_event(
        source=item.source,
        domain=item.domain,
        kind=item.kind,
        title=item.title,
        content=item.content,
        url=item.url,
        meta=item.meta,
        dedup_key=item.dedup_key,
    )
    if event_id is None:
        return None, None, None
    db.insert_judgment(event_id=event_id, score=score, take=analysis["take"], triage=triage, reasons=reasons, analysis=analysis)
    judgment = Judgment(score=score, take=analysis["take"], triage=triage, reasons=reasons, analysis=analysis)
    if triage == "notify":
        return event_id, judgment, {
            "type": "notify",
            "source": "RSS Intelligence",
            "event_id": event_id,
            "title": item.title,
            "take": analysis["take"],
            "url": item.url,
            "score": score,
        }
    return event_id, judgment, None


async def _store_news_item(item: RawItem) -> tuple[str | None, Judgment | None]:
    event_id, judgment, payload = await asyncio.to_thread(_store_news_item_sync, item)
    if payload:
        await hub.push(payload)
    return event_id, judgment


def seed_defaults() -> dict:
    """Create user-friendly intelligence defaults from existing config/profile."""
    db.init_db()
    created = {"targets": 0, "sources": 0}
    ts = db.now_ms()
    terms = sorted(profile_terms())
    base_targets = [t for t in terms if len(t) >= 2][:18]
    if not base_targets:
        base_targets = ["AI Agent", "本地大模型", "个人生产力", "Mac 自动化"]

    cfg = sources()
    radar_cfg = cfg.get("github_radar", {})
    for q in radar_cfg.get("queries", []):
        if str(q).strip():
            base_targets.append(str(q).strip())

    with db.conn() as c:
        for target in dict.fromkeys(base_targets):
            try:
                c.execute(
                    """INSERT INTO intelligence_targets(id,label,kind,query,enabled,created_ts,updated_ts)
                       VALUES(?,?,?,?,1,?,?)""",
                    (uuid.uuid4().hex, target, "topic", target, ts, ts),
                )
                created["targets"] += 1
            except Exception:
                created["skipped"] = created.get("skipped", 0) + 1

        for feed in cfg.get("rss", []):
            url = str(feed.get("url", "")).strip()
            if not url:
                continue
            meta = {
                "fulltext": bool(feed.get("fulltext", False)),
                "limit": int(feed.get("limit", 10)),
            }
            try:
                c.execute(
                    """INSERT INTO intelligence_sources(id,type,name,url,domain,enabled,meta,created_ts,updated_ts)
                       VALUES(?,?,?,?,?,1,?,?,?)""",
                    (
                        uuid.uuid4().hex,
                        "rss",
                        str(feed.get("name") or url),
                        url,
                        str(feed.get("domain", "business")),
                        json.dumps(meta, ensure_ascii=False),
                        ts,
                        ts,
                    ),
                )
                created["sources"] += 1
            except Exception:
                created["skipped"] = created.get("skipped", 0) + 1

        starter_web = [
            ("GitHub Trending", "https://github.com/trending", "business"),
        ]
        for name, url, domain in starter_web:
            try:
                c.execute(
                    """INSERT INTO intelligence_sources(id,type,name,url,domain,enabled,meta,created_ts,updated_ts)
                       VALUES(?,?,?,?,?,1,?,?,?)""",
                    (uuid.uuid4().hex, "web", name, url, domain, "{}", ts, ts),
                )
                created["sources"] += 1
            except Exception:
                created["skipped"] = created.get("skipped", 0) + 1
    return created


def list_targets() -> list[dict]:
    seed_defaults()
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM intelligence_targets ORDER BY enabled DESC, updated_ts DESC, label COLLATE NOCASE"
        ).fetchall()
    return [_rowdict(r) for r in rows]


def upsert_target(*, label: str, query: str, kind: str = "topic", enabled: bool = True) -> dict:
    db.init_db()
    ts = db.now_ms()
    label = label.strip() or query.strip()
    query = query.strip() or label
    kind = kind.strip() or "topic"
    with db.conn() as c:
        row = c.execute(
            "SELECT id FROM intelligence_targets WHERE kind=? AND query=?",
            (kind, query),
        ).fetchone()
        if row:
            c.execute(
                """UPDATE intelligence_targets
                   SET label=?, enabled=?, updated_ts=? WHERE id=?""",
                (label, 1 if enabled else 0, ts, row["id"]),
            )
            target_id = row["id"]
        else:
            target_id = uuid.uuid4().hex
            c.execute(
                """INSERT INTO intelligence_targets(id,label,kind,query,enabled,created_ts,updated_ts)
                   VALUES(?,?,?,?,?,?,?)""",
                (target_id, label, kind, query, 1 if enabled else 0, ts, ts),
            )
        target = c.execute("SELECT * FROM intelligence_targets WHERE id=?", (target_id,)).fetchone()
    return _rowdict(target)


def set_target_enabled(target_id: str, enabled: bool) -> dict:
    with db.conn() as c:
        c.execute(
            "UPDATE intelligence_targets SET enabled=?, updated_ts=? WHERE id=?",
            (1 if enabled else 0, db.now_ms(), target_id),
        )
        row = c.execute("SELECT * FROM intelligence_targets WHERE id=?", (target_id,)).fetchone()
    return _rowdict(row)


def list_sources() -> list[dict]:
    seed_defaults()
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM intelligence_sources ORDER BY enabled DESC, type, updated_ts DESC"
        ).fetchall()
    result = []
    seen_urls: set[str] = set()
    for row in rows:
        item = _rowdict(row)
        item["meta"] = _json_loads(item.get("meta"), {})
        name = str(item.get("name") or "")
        url = str(item.get("url") or "")
        if name.startswith("X ·") and "rsshub.app/twitter/user/" in url:
            # 历史版本曾把公共 RSSHub X 路由写入来源表；该路由现在通常 404。
            # 展示和扫描都交给 x_monitor_feeds() 生成的可替换源。
            continue
        if "reutersagency.com/feed/" in url:
            # Reuters agency 旧 RSS 已返回 404，默认源已替换为 OpenAI 官方 RSS。
            continue
        if name == "OpenAI Blog" and url.rstrip("/") == "https://openai.com/news":
            # 网页变化监控会被 Cloudflare 拦截；OpenAI 官方 RSS 在 config/sources.toml 中提供。
            continue
        if name == "machine-learning" and url.rstrip("/") == "https://hnrss.org/frontpage":
            # 历史重复源，默认配置已有 Hacker News · Frontpage。
            continue
        seen_urls.add(str(item.get("url") or ""))
        result.append(item)
    for feed in x_monitor_feeds():
        url = str(feed.get("url") or "")
        if not url or url in seen_urls:
            continue
        meta = {
            "channel": "x_monitor",
            "category": feed.get("category", "X社媒"),
            "managed": True,
            "handle": (feed.get("meta") or {}).get("handle"),
            "limit": int(feed.get("limit") or 6),
        }
        result.append({
            "id": f"x:{_hash_text(url)[:16]}",
            "type": "rss",
            "name": str(feed.get("name") or "X 监控"),
            "url": url,
            "domain": str(feed.get("domain") or "business"),
            "enabled": 1,
            "last_scan_ts": None,
            "last_hash": None,
            "meta": meta,
            "created_ts": None,
            "updated_ts": None,
        })
    return result


def upsert_source(*, source_type: str, name: str, url: str, domain: str = "business",
                  enabled: bool = True, meta: dict | None = None) -> dict:
    db.init_db()
    ts = db.now_ms()
    source_type = source_type.strip().lower()
    if source_type not in {"rss", "web"}:
        raise ValueError("source_type must be rss or web")
    name = name.strip() or url.strip()
    url = url.strip()
    if not url:
        raise ValueError("url is required")
    with db.conn() as c:
        row = c.execute(
            "SELECT id FROM intelligence_sources WHERE type=? AND url=?",
            (source_type, url),
        ).fetchone()
        if row:
            c.execute(
                """UPDATE intelligence_sources
                   SET name=?, domain=?, enabled=?, meta=?, updated_ts=? WHERE id=?""",
                (name, domain, 1 if enabled else 0,
                 json.dumps(meta or {}, ensure_ascii=False), ts, row["id"]),
            )
            source_id = row["id"]
        else:
            source_id = uuid.uuid4().hex
            c.execute(
                """INSERT INTO intelligence_sources(id,type,name,url,domain,enabled,meta,created_ts,updated_ts)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    source_id,
                    source_type,
                    name,
                    url,
                    domain,
                    1 if enabled else 0,
                    json.dumps(meta or {}, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
        source = c.execute("SELECT * FROM intelligence_sources WHERE id=?", (source_id,)).fetchone()
    item = _rowdict(source)
    item["meta"] = _json_loads(item.get("meta"), {})
    return item


def set_source_enabled(source_id: str, enabled: bool) -> dict:
    if source_id.startswith("x:"):
        return {"id": source_id, "enabled": 1 if enabled else 0, "managed": "x_monitor"}
    with db.conn() as c:
        c.execute(
            "UPDATE intelligence_sources SET enabled=?, updated_ts=? WHERE id=?",
            (1 if enabled else 0, db.now_ms(), source_id),
        )
        row = c.execute("SELECT * FROM intelligence_sources WHERE id=?", (source_id,)).fetchone()
    item = _rowdict(row)
    item["meta"] = _json_loads(item.get("meta"), {})
    return item


def _store_raw_item_sync(item: RawItem, *, dedup_key: str | None = None) -> tuple[str | None, Judgment | None, dict | None]:
    event_id = db.insert_event(
        source=item.source,
        domain=item.domain,
        kind=item.kind,
        title=item.title,
        content=item.content,
        url=item.url,
        meta=item.meta,
        dedup_key=dedup_key or item.dedup_key,
    )
    if event_id is None:
        return None, None, None
    remember_event(event_id, f"{item.title}\n{item.content[:900]}")
    judgment = judge_and_store(event_id, item)
    if judgment.triage == "notify":
        return event_id, judgment, {
            "type": "notify",
            "source": "Intelligence",
            "event_id": event_id,
            "title": item.title,
            "take": judgment.take,
            "url": item.url,
            "score": judgment.score,
        }
    return event_id, judgment, None


async def _store_raw_item(item: RawItem, *, dedup_key: str | None = None) -> tuple[str | None, Judgment | None]:
    event_id, judgment, payload = await asyncio.to_thread(_store_raw_item_sync, item, dedup_key=dedup_key)
    if payload:
        await hub.push(payload)
    return event_id, judgment


async def _scan_rss_sources(client: httpx.AsyncClient) -> dict:
    stats = {"seen": 0, "inserted": 0, "notify": 0, "errors": []}
    srcs = [s for s in list_sources() if s["enabled"] and s["type"] == "rss"]
    sem = asyncio.Semaphore(10)

    async def scan_source(src: dict) -> dict:
        local = {"seen": 0, "inserted": 0, "notify": 0, "errors": []}
        try:
            meta = src.get("meta") or {}
            is_x_source = (meta.get("channel") == "x_monitor") or str(src.get("name", "")).startswith("X ·")
            async with sem:
                res = await client.get(src["url"], timeout=4)
                res.raise_for_status()
            parsed = feedparser.parse(res.content)
            limit = int(meta.get("limit", 12))
            if is_x_source:
                limit = min(limit, 4)
            for entry in parsed.entries[:limit]:
                local["seen"] += 1
                original_title = getattr(entry, "title", "") or "（无标题）"
                link = getattr(entry, "link", "") or ""
                content = getattr(entry, "summary", "") or original_title
                if meta.get("fulltext") and link and not is_x_source:
                    try:
                        html = (await client.get(link)).text
                        content = trafilatura.extract(html) or content
                    except Exception:
                        content = content or "正文抓取失败，保留摘要。"
                title = to_chinese(original_title, context="X 监控动态标题" if is_x_source else "RSS 资讯标题", max_chars=120, allow_llm=False)
                chinese_content = to_chinese(_clean_text(content), context="X 监控动态摘要" if is_x_source else "RSS 资讯摘要", max_chars=1500, allow_llm=False)
                published = getattr(entry, "published", "") or getattr(entry, "updated", "")
                item = RawItem(
                    source=f"intel:x:{src['name']}" if is_x_source else f"intel:rss:{src['name']}",
                    domain=src.get("domain") or "business",
                    kind="x_post" if is_x_source else "news",
                    title=title,
                    content=_clean_text(chinese_content),
                    url=link,
                    meta={
                        "source_id": src["id"],
                        "published": published,
                        "original_title": original_title,
                        "category": meta.get("category") or ("X社媒" if is_x_source else "综合资讯"),
                        "channel": "x_monitor" if is_x_source else meta.get("channel"),
                        "handle": meta.get("handle"),
                        "feed_name": src.get("name"),
                        "route": meta.get("route"),
                    },
                )
                event_id, judgment = await _store_x_item(item) if is_x_source else await _store_news_item(item)
                if event_id:
                    local["inserted"] += 1
                    if judgment and judgment.triage == "notify":
                        local["notify"] += 1
            with db.conn() as c:
                c.execute("UPDATE intelligence_sources SET last_scan_ts=? WHERE id=?", (db.now_ms(), src["id"]))
        except Exception as exc:
            local["errors"].append({"source": src["name"], "error": str(exc)})
        return local

    results = await asyncio.gather(*(scan_source(src) for src in srcs))
    for item in results:
        stats["seen"] += item["seen"]
        stats["inserted"] += item["inserted"]
        stats["notify"] += item["notify"]
        stats["errors"].extend(item["errors"])
    return stats


async def _scan_web_sources(client: httpx.AsyncClient) -> dict:
    stats = {"seen": 0, "changed": 0, "inserted": 0, "notify": 0, "errors": []}
    for src in [s for s in list_sources() if s["enabled"] and s["type"] == "web"]:
        try:
            stats["seen"] += 1
            res = await client.get(src["url"])
            res.raise_for_status()
            extracted = trafilatura.extract(res.text, include_comments=False, include_tables=False)
            text = _clean_text(extracted or res.text, limit=10000)
            if not text:
                continue
            digest = _hash_text(text)
            changed = digest != src.get("last_hash")
            first_seen = not src.get("last_hash")
            with db.conn() as c:
                c.execute(
                    "UPDATE intelligence_sources SET last_scan_ts=?, last_hash=?, updated_ts=? WHERE id=?",
                    (db.now_ms(), digest, db.now_ms(), src["id"]),
                )
            if not changed:
                continue
            stats["changed"] += 1
            title = f"{src['name']} {'首次纳入监控' if first_seen else '出现内容变化'}"
            chinese_text = to_chinese(text[:3500], context="网页变化摘要", max_chars=1600, allow_llm=False)
            item = RawItem(
                source=f"intel:web:{src['name']}",
                domain=src.get("domain") or "business",
                kind="web_change",
                title=title,
                content=chinese_text,
                url=src["url"],
                meta={"source_id": src["id"], "first_seen": first_seen, "hash": digest},
            )
            event_id, judgment = await _store_raw_item(item, dedup_key=f"web:{src['id']}:{digest}")
            if event_id:
                stats["inserted"] += 1
                if judgment and judgment.triage == "notify":
                    stats["notify"] += 1
        except Exception as exc:
            stats["errors"].append({"source": src["name"], "error": str(exc)})
    return stats


def _github_queries() -> list[str]:
    seed_defaults()
    cfg = sources().get("github_radar", {})
    configured = [str(q).strip() for q in cfg.get("queries", []) if str(q).strip()]
    target_queries = [
        str(t["query"]).strip()
        for t in list_targets()
        if t.get("enabled") and str(t.get("query", "")).strip()
    ]
    queries = list(dict.fromkeys(configured + target_queries))
    return queries[: int(cfg.get("max_queries", 10))]


def _parse_github_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except Exception:
            return None


def _snapshot_velocity(repo_full_name: str, stars: int, observed_ts: int) -> dict:
    since_24h = observed_ts - 24 * 3600 * 1000
    since_7d = observed_ts - 7 * 24 * 3600 * 1000
    with db.conn() as c:
        prev_any = c.execute(
            """SELECT stars, observed_ts FROM github_repo_snapshots
               WHERE repo_full_name=? AND observed_ts<?
               ORDER BY observed_ts DESC LIMIT 1""",
            (repo_full_name, observed_ts),
        ).fetchone()
        prev_24 = c.execute(
            """SELECT stars, observed_ts FROM github_repo_snapshots
               WHERE repo_full_name=? AND observed_ts<=?
               ORDER BY observed_ts DESC LIMIT 1""",
            (repo_full_name, since_24h),
        ).fetchone()
        prev_7d = c.execute(
            """SELECT stars, observed_ts FROM github_repo_snapshots
               WHERE repo_full_name=? AND observed_ts<=?
               ORDER BY observed_ts DESC LIMIT 1""",
            (repo_full_name, since_7d),
        ).fetchone()
    delta_24h = stars - int(prev_24["stars"]) if prev_24 else None
    delta_7d = stars - int(prev_7d["stars"]) if prev_7d else None
    per_day = None
    delta_since_last = None
    last_interval_hours = None
    if prev_any:
        delta_since_last = stars - int(prev_any["stars"])
        elapsed_ms = max(observed_ts - int(prev_any["observed_ts"]), 1)
        days = max(elapsed_ms / 86_400_000, 1 / 24)
        last_interval_hours = round(elapsed_ms / 3_600_000, 2)
        per_day = round(delta_since_last / days, 2)
    return {
        "delta_since_last": delta_since_last,
        "last_interval_hours": last_interval_hours,
        "delta_24h": delta_24h,
        "delta_7d": delta_7d,
        "stars_per_day": per_day,
    }


def _github_score(repo: dict, velocity: dict) -> tuple[float, list[str]]:
    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    created = _parse_github_dt(repo.get("created_at"))
    pushed = _parse_github_dt(repo.get("pushed_at"))
    now = datetime.now(timezone.utc)
    age_days = max((now - created).days, 1) if created else 365
    pushed_days = max((now - pushed).days, 0) if pushed else 365
    cold_momentum = stars / max(age_days, 1)
    growth = velocity.get("stars_per_day")
    reasons: list[str] = []

    score = 0.25
    if stars >= 1000:
        score += 0.12
        reasons.append("star 基数已过 1k")
    if stars >= 10000:
        score += 0.08
        reasons.append("高 star 项目")
    if forks >= max(stars * 0.08, 50):
        score += 0.06
        reasons.append("fork 活跃")
    if pushed_days <= 7:
        score += 0.12
        reasons.append("最近一周仍活跃")
    if age_days <= 180 and cold_momentum >= 15:
        score += 0.2
        reasons.append(f"冷启动动量强：约 {cold_momentum:.1f} star/天")
    elif cold_momentum >= 8:
        score += 0.12
        reasons.append(f"长期增速不错：约 {cold_momentum:.1f} star/天")
    if growth is not None:
        if growth >= 100:
            score += 0.28
            reasons.append(f"实测 star 增速很快：约 {growth:.0f}/天")
        elif growth >= 25:
            score += 0.18
            reasons.append(f"实测 star 增速明显：约 {growth:.0f}/天")
        elif growth > 0:
            score += 0.08
            reasons.append(f"实测 star 仍在增长：约 {growth:.1f}/天")
    return min(score, 0.98), reasons or ["GitHub radar"]


def _repo_age_days(repo: dict) -> int | None:
    created = _parse_github_dt(repo.get("created_at"))
    if not created:
        return None
    return max((datetime.now(timezone.utc) - created).days, 1)


def _repo_cold_momentum(repo: dict) -> float | None:
    stars = int(repo.get("stargazers_count") or repo.get("stars") or 0)
    age_days = _repo_age_days(repo)
    if not age_days:
        return None
    return round(stars / max(age_days, 1), 2)


def _is_recent_repo_signal(repo: dict, velocity: dict, cfg: dict) -> bool:
    stars = int(repo.get("stargazers_count") or repo.get("stars") or 0)
    age_days = _repo_age_days(repo)
    if not age_days:
        return False
    max_age = int(cfg.get("max_repo_age_days", int(cfg.get("created_days", 180)) + 30))
    min_cold = float(cfg.get("min_cold_stars_per_day", 5))
    min_measured = float(cfg.get("min_measured_stars_per_day", 3))
    popular_ceiling = int(cfg.get("popular_star_ceiling", 100000))
    measured = velocity.get("stars_per_day")
    cold = _repo_cold_momentum(repo) or 0

    # 产品目标是发现近期项目，不是把长期头部项目重复挂到雷达。
    if stars >= popular_ceiling:
        return False
    if age_days <= max_age and (cold >= min_cold or (measured or 0) >= min_measured):
        return True
    # 少量老项目如果最近实测突然加速，仍保留观察；但必须不是“常青巨无霸”。
    if (measured or 0) >= max(min_measured * 8, 25) and age_days <= 730:
        return True
    return False


def _repo_momentum_value(repo: dict, velocity: dict) -> float:
    measured = float(velocity.get("stars_per_day") or 0)
    cold = _repo_cold_momentum(repo) or 0
    return max(measured, min(cold, 300))


def _insert_repo_snapshot(repo: dict, query: str, velocity: dict) -> None:
    with db.conn() as c:
        c.execute(
            """INSERT INTO github_repo_snapshots(
                 id, repo_full_name, query, stars, forks, open_issues, description, url,
                 language, topics, license, created_at, pushed_at, updated_at, observed_ts
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uuid.uuid4().hex,
                repo["full_name"],
                query,
                int(repo.get("stargazers_count") or 0),
                int(repo.get("forks_count") or 0),
                int(repo.get("open_issues_count") or 0),
                repo.get("description") or "",
                repo.get("html_url") or "",
                repo.get("language") or "",
                json.dumps(repo.get("topics") or [], ensure_ascii=False),
                (repo.get("license") or {}).get("spdx_id") or "",
                repo.get("created_at") or "",
                repo.get("pushed_at") or "",
                repo.get("updated_at") or "",
                db.now_ms(),
            ),
        )


async def _scan_github(client: httpx.AsyncClient) -> dict:
    cfg = sources().get("github_radar", {})
    if cfg.get("enabled", True) is False:
        return {"seen": 0, "inserted": 0, "notify": 0, "errors": [], "disabled": True}
    min_stars = int(cfg.get("min_stars", 300))
    max_results = int(cfg.get("max_results_per_query", 8))
    pushed_days = int(cfg.get("pushed_days", 45))
    created_days = int(cfg.get("created_days", 730))
    pushed_after = (datetime.now(timezone.utc) - timedelta(days=pushed_days)).date().isoformat()
    created_after = (datetime.now(timezone.utc) - timedelta(days=created_days)).date().isoformat()
    stats = {"seen": 0, "inserted": 0, "notify": 0, "errors": [], "queries": []}
    seen_repos: set[str] = set()
    sem = asyncio.Semaphore(5)

    async def scan_query(query: str) -> dict:
        local = {"seen": 0, "inserted": 0, "notify": 0, "errors": [], "queries": []}
        search_q = f"{query} stars:>={min_stars} pushed:>={pushed_after} created:>={created_after}"
        url = (
            "https://api.github.com/search/repositories"
            f"?q={quote_plus(search_q)}&sort=stars&order=desc&per_page={max_results}"
        )
        local["queries"].append(search_q)
        try:
            async with sem:
                res = await client.get(url, headers=_github_headers(), timeout=5)
                res.raise_for_status()
            data = res.json()
            for repo in data.get("items", []):
                full_name = repo.get("full_name")
                if not full_name or full_name in seen_repos:
                    continue
                seen_repos.add(full_name)
                local["seen"] += 1
                observed_ts = db.now_ms()
                velocity = _snapshot_velocity(full_name, int(repo.get("stargazers_count") or 0), observed_ts)
                score, reasons = _github_score(repo, velocity)
                _insert_repo_snapshot(repo, query, velocity)
                if not _is_recent_repo_signal(repo, velocity, cfg):
                    continue
                stars = int(repo.get("stargazers_count") or 0)
                forks = int(repo.get("forks_count") or 0)
                topics = repo.get("topics") or []
                original_description = repo.get("description") or "无描述"
                description = to_chinese(original_description, context="GitHub 项目描述", max_chars=180, allow_llm=False)
                analysis = _github_analysis(repo, query, velocity, score, reasons)
                per_day = velocity.get("stars_per_day")
                delta_24h = velocity.get("delta_24h")
                delta_7d = velocity.get("delta_7d")
                trend_line = (
                    f"实测增速：{per_day} star/天；24h 增量：{delta_24h}；7d 增量：{delta_7d}。"
                    if per_day is not None else "首次观察，先用项目年龄、star 基数和最近活跃度估算动量。"
                )
                content = (
                    f"仓库介绍：{analysis['summary']}\n\n"
                    f"项目指标：Stars {stars}；Forks {forks}；主要语言 {repo.get('language') or '未知'}。\n"
                    f"{trend_line}\n"
                    f"主题：{'、'.join(_repo_topic_tags(topics[:10], repo.get('language'))) or '暂无'}。\n"
                    f"雷达查询：{to_chinese(query, context='GitHub 搜索词', max_chars=80, allow_llm=False)}。\n"
                    f"入选原因：{'；'.join(reasons)}。"
                )
                triage = "notify" if score >= 0.76 else "digest" if score >= 0.46 else "ignore"
                item = RawItem(
                    source="intel:github",
                    domain="business",
                    kind="github_repo",
                    title=f"{full_name} · GitHub 项目雷达",
                    content=content,
                    url=repo.get("html_url") or "",
                    meta={
                        "repo": full_name,
                        "query": query,
                        "stars": stars,
                        "forks": forks,
                        "language": repo.get("language"),
                        "topics": topics,
                        "display_topics": _repo_topic_tags(topics, repo.get("language")),
                        "original_description": original_description,
                        "summary_zh": analysis["summary"],
                        "display_description": analysis["summary"] or description,
                        "why_zh": analysis["why"],
                        "relation_zh": analysis["relation"],
                        "next_step_zh": analysis["next_step"],
                        "momentum_score": round(score, 3),
                        "velocity": velocity,
                        "reasons": reasons,
                        "created_at": repo.get("created_at"),
                        "pushed_at": repo.get("pushed_at"),
                    },
                )
                event_id = db.insert_event(
                    source=item.source,
                    domain=item.domain,
                    kind=item.kind,
                    title=item.title,
                    content=item.content,
                    url=item.url,
                    meta=item.meta,
                    dedup_key=f"github:{full_name}:{_event_day()}",
                )
                if event_id is None:
                    continue
                local["inserted"] += 1
                db.insert_judgment(
                    event_id=event_id,
                    score=round(score, 3),
                    take=analysis["take"],
                    triage=triage,
                    reasons=reasons,
                    analysis=analysis,
                )
                if triage == "notify":
                    local["notify"] += 1
                    await hub.push({
                        "type": "notify",
                        "source": "GitHub Radar",
                        "event_id": event_id,
                        "title": item.title,
                        "take": "；".join(reasons[:3]),
                        "url": item.url,
                        "score": round(score, 3),
                    })
        except Exception as exc:
            local["errors"].append({"query": query, "error": str(exc)})
        return local

    results = await asyncio.gather(*(scan_query(q) for q in _github_queries()))
    for item in results:
        stats["seen"] += item["seen"]
        stats["inserted"] += item["inserted"]
        stats["notify"] += item["notify"]
        stats["errors"].extend(item["errors"])
        stats["queries"].extend(item["queries"])
    return stats


async def run_intelligence_scan(*, include_rss: bool = True, include_web: bool = True,
                                include_github: bool = True) -> dict:
    if not _SCAN_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": "already_running", "started_at": _now_iso()}
    try:
        seed_defaults()
        started = _now_iso()
        stats: dict[str, Any] = {"started_at": started, "rss": None, "web": None, "github": None}
        async with httpx.AsyncClient(
            timeout=18,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            trust_env=False,
        ) as client:
            if include_rss:
                stats["rss"] = await _scan_rss_sources(client)
            if include_web:
                stats["web"] = await _scan_web_sources(client)
            if include_github:
                stats["github"] = await _scan_github(client)
        stats["finished_at"] = _now_iso()
        return stats
    finally:
        _SCAN_LOCK.release()


def github_radar(limit: int = 24) -> list[dict]:
    seed_defaults()
    cfg = sources().get("github_radar", {})
    fetch_limit = max(limit * 8, 120)
    with db.conn() as c:
        rows = c.execute(
            """
            WITH latest AS (
              SELECT repo_full_name, MAX(observed_ts) AS observed_ts
              FROM github_repo_snapshots
              GROUP BY repo_full_name
            )
            SELECT s.*
            FROM github_repo_snapshots s
            JOIN latest l ON l.repo_full_name=s.repo_full_name AND l.observed_ts=s.observed_ts
            ORDER BY s.observed_ts DESC, s.stars DESC
            LIMIT ?
            """,
            (fetch_limit,),
        ).fetchall()
    result = []
    with db.conn() as c:
        for row in rows:
            item = _rowdict(row)
            item["topics"] = _json_loads(item.get("topics"), [])
            velocity = _snapshot_velocity(item["repo_full_name"], int(item["stars"]), int(item["observed_ts"]))
            item.update(velocity)
            created = _parse_github_dt(item.get("created_at"))
            if created:
                age_days = max((datetime.now(timezone.utc) - created).days, 1)
                item["cold_stars_per_day"] = round(int(item["stars"]) / age_days, 2)
            else:
                item["cold_stars_per_day"] = None
            hist = c.execute(
                "SELECT stars, observed_ts FROM github_repo_snapshots WHERE repo_full_name=? ORDER BY observed_ts",
                (item["repo_full_name"],),
            ).fetchall()
            item["star_history"] = [{"ts": int(h["observed_ts"]), "stars": int(h["stars"])} for h in hist]
            score, reasons = _github_score({
                "stargazers_count": item.get("stars"),
                "forks_count": item.get("forks"),
                "created_at": item.get("created_at"),
                "pushed_at": item.get("pushed_at"),
            }, velocity)
            repo_like = {
                "full_name": item["repo_full_name"],
                "description": item.get("description"),
                "topics": item.get("topics") or [],
                "language": item.get("language"),
                "stars": item.get("stars"),
                "created_at": item.get("created_at"),
                "pushed_at": item.get("pushed_at"),
                "updated_at": item.get("updated_at"),
            }
            if not _is_recent_repo_signal(repo_like, velocity, cfg):
                continue
            analysis = _github_analysis(repo_like, item.get("query") or "GitHub radar", velocity, score, reasons)
            item["display_description"] = analysis["summary"]
            item["summary_zh"] = analysis["summary"]
            item["why_zh"] = analysis["why"]
            item["relation_zh"] = analysis["relation"]
            item["next_step_zh"] = analysis["next_step"]
            item["display_topics"] = _repo_topic_tags(item.get("topics") or [], item.get("language"))
            item["momentum_score"] = round(score, 3)
            item["age_days"] = _repo_age_days(repo_like)
            item["recent_momentum"] = _repo_momentum_value(repo_like, velocity)
            result.append(item)
    result.sort(
        key=lambda r: (
            float(r.get("recent_momentum") or 0),
            float(r.get("momentum_score") or 0),
            -(int(r.get("age_days") or 9999)),
        ),
        reverse=True,
    )
    return result[:limit]


def recent_intelligence_events(hours: int = 72, limit: int = 80) -> list[dict]:
    since = int((time.time() - hours * 3600) * 1000)
    with db.conn() as c:
        rows = c.execute(
            """
            SELECT e.id AS event_id, e.ts, e.source, e.domain, e.kind, e.title, e.url, e.meta,
                   j.score, j.take, j.triage, j.reasons, j.analysis
            FROM events e
            LEFT JOIN judgments j ON j.event_id=e.id
            WHERE e.ts>=? AND (
                e.source LIKE 'intel:%' OR e.source LIKE 'rss:%'
                OR e.kind IN ('github_repo','web_change','news','market')
            )
            ORDER BY e.ts DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = _rowdict(row)
        item["meta"] = _json_loads(item.get("meta"), {})
        item["reasons"] = _json_loads(item.get("reasons"), [])
        item["analysis"] = _json_loads(item.get("analysis"), {}) or {}
        result.append(item)
    return result


def overview() -> dict:
    seed_defaults()
    events = recent_intelligence_events(hours=72, limit=60)
    github = github_radar(limit=18)
    sources_list = list_sources()
    targets = list_targets()
    return {
        "generated_at": int(time.time()),
        "targets": targets,
        "sources": sources_list,
        "events": events,
        "github": github,
        "stats": {
            "enabled_targets": sum(1 for t in targets if t.get("enabled")),
            "enabled_sources": sum(1 for s in sources_list if s.get("enabled")),
            "notify_events": sum(1 for e in events if e.get("triage") == "notify"),
            "github_repos": len(github),
        },
    }
