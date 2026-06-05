from __future__ import annotations

import re
import time
from collections import Counter

from . import db, personal_notes
from .agent import services, sysinfo
from .briefing.builder import build_today
from .intelligence.scanner import github_radar, recent_intelligence_events
from .localize import chinese_tags as _chinese_tags, to_chinese as _to_chinese


# 驾驶舱每 8 秒被前端轮询，展示路径禁止实时 LLM；本地化只做无网络回退。
def to_chinese(text, *, context="通用内容", max_chars=360, allow_llm=False):
    return _to_chinese(text, context=context, max_chars=max_chars, allow_llm=allow_llm)


def chinese_tags(raw, *, allow_llm=False):
    return _chinese_tags(raw, allow_llm=allow_llm)


def _parse_system(raw: str) -> dict:
    disk = re.search(r"\((\d+)%\)", raw)
    load = re.search(r"负载\(1/5/15min\):\s*([\d.]+)", raw)
    disk_pct = int(disk.group(1)) if disk else None
    load_value = float(load.group(1)) if load else None
    return {"raw": raw, "disk_pct": disk_pct, "load": load_value}


def _events(hours: int = 24, limit: int = 200) -> list[dict]:
    since = int((time.time() - hours * 3600) * 1000)
    return [dict(r) for r in db.query_events(since, limit=limit)]


def _judgment_distribution(hours: int = 24) -> dict:
    since = int((time.time() - hours * 3600) * 1000)
    with db.conn() as c:
        rows = c.execute(
            "SELECT triage, COUNT(*) AS count FROM judgments WHERE ts>=? GROUP BY triage",
            (since,),
        ).fetchall()
    base = {"notify": 0, "digest": 0, "ignore": 0}
    for r in rows:
        base[r["triage"]] = r["count"]
    return base


def _source_distribution(events: list[dict]) -> list[dict]:
    def label(source: str | None) -> str:
        raw = str(source or "未知").split(":")[0]
        return {
            "intel": "情报中心",
            "rss": "RSS 资讯",
            "personal_note": "个人记事",
            "journal": "旧记录",
            "agent": "中枢对话",
            "reflection": "记忆反思",
            "test": "测试数据",
        }.get(raw, raw)

    counts = Counter(label(e.get("source")) for e in events)
    return [{"source": k, "count": v} for k, v in counts.most_common(8)]


def _source_label(source: str | None) -> str:
    raw = str(source or "本地").split(":")[0]
    return {
        "intel": "情报中心",
        "rss": "RSS 资讯",
        "personal_note": "个人记事",
        "journal": "旧记录",
        "agent": "中枢对话",
        "reflection": "记忆反思",
        "test": "测试数据",
    }.get(raw, raw)


def _kind_label(kind: str | None) -> str:
    return {
        "note": "记事",
        "journal": "旧记录",
        "action": "动作",
        "insight": "洞察",
        "github_repo": "GitHub 项目",
        "rss": "RSS 条目",
        "news": "资讯",
        "web_change": "网页变化",
        "market": "市场信息",
    }.get(str(kind or "事件"), str(kind or "事件"))


def _memory_stats() -> dict:
    with db.conn() as c:
        rows = c.execute("SELECT status, COUNT(*) AS count FROM memories GROUP BY status").fetchall()
    result = {"active": 0, "pending": 0, "later": 0, "rejected": 0}
    for r in rows:
        result[r["status"] or "active"] = r["count"]
    return result


def _repo_speed(repo: dict) -> float:
    return float(repo.get("stars_per_day") or repo.get("cold_stars_per_day") or 0)


def _processed_github_cards(briefing: dict, repos: list[dict], limit: int = 5) -> list[dict]:
    cards: list[dict] = []
    seen: set[str] = set()
    repo_index = {r.get("repo_full_name"): r for r in repos if r.get("repo_full_name")}
    for item in briefing.get("items", []):
        if item.get("kind") != "github_repo":
            continue
        score = float(item.get("score") or 0)
        if score < 0.72:
            continue
        name = (item.get("original_title") or item.get("title") or "").replace(" · GitHub 项目雷达", "")
        if "英文来源摘要" in name:
            name = (item.get("title") or "").replace(" · GitHub 项目雷达", "")
        if name in seen:
            continue
        repo = repo_index.get(name, {})
        stars = int(item.get("repo_stars") or repo.get("stars") or 0) if (item.get("repo_stars") or repo) else None
        speed = float(item.get("repo_speed") or _repo_speed(repo) or 0) if (item.get("repo_speed") or repo) else None
        seen.add(name)
        cards.append({
            "name": name,
            "title": item.get("title"),
            "url": item.get("url"),
            "score": score,
            "summary": item.get("take") or "已通过情报评分筛选，值得进入驾驶舱观察。",
            "why": item.get("why_important") or "增长和活跃度达到驾驶舱展示阈值。",
            "relation": item.get("relation") or "与你的 AI、开发工具或本地助理关注项相关。",
            "next_step": item.get("next_step") or "打开项目页，判断是否需要加入关注或写入个人记事。",
            "priority": item.get("priority") or "高优先",
            "tags": item.get("tags") or ["GitHub 项目"],
            "stars": stars,
            "speed": speed,
            "star_history": repo.get("star_history") or [],
            "language": repo.get("language"),
        })
        if len(cards) >= limit:
            return cards

    for repo in sorted(repos, key=_repo_speed, reverse=True):
        stars = int(repo.get("stars") or 0)
        speed = _repo_speed(repo)
        if stars < 1000 or speed < 8:
            continue
        name = repo.get("repo_full_name")
        if not name or name in seen:
            continue
        seen.add(name)
        description = to_chinese(repo.get("description") or name, context="驾驶舱 GitHub 项目介绍", max_chars=180)
        cards.append({
            "name": name,
            "title": f"{name} · GitHub 项目雷达",
            "url": repo.get("url"),
            "score": min(0.98, 0.72 + min(speed / 500, 0.2)),
            "summary": description,
            "why": f"项目有 {stars:,} 个星标，当前动量约 {speed}/天，满足驾驶舱高价值阈值。",
            "relation": "与你关注的 AI 工具、本地助理、自动化或开发工作流可能相关。",
            "next_step": "打开项目页看 README 和最近提交，决定是否加入情报关注项或写入个人记事。",
            "priority": "高优先" if speed >= 25 else "中优先",
            "tags": chinese_tags(repo.get("topics") or []) or ["GitHub 项目"],
            "stars": stars,
            "speed": speed,
            "star_history": repo.get("star_history") or [],
            "language": repo.get("language"),
        })
        if len(cards) >= limit:
            break
    return cards


def overview() -> dict:
    system = _parse_system(sysinfo.system_status())
    service_rows = services.status_all()
    notifications = sysinfo.local_notifications()
    weather = sysinfo.weather()
    ai_tools = sysinfo.ai_tool_status()
    try:
        from .agent import agents_ctrl
        agent_rows = agents_ctrl.list_agents()
    except Exception:  # noqa: BLE001
        agent_rows = []
    events = _events()
    briefing = build_today()
    intel_events = recent_intelligence_events(hours=72, limit=40)
    repos = github_radar(limit=80)
    github_cards = _processed_github_cards(briefing, repos)
    notes = personal_notes.note_stats()
    memory = _memory_stats()

    online = sum(1 for s in service_rows if s["online"])
    tools_ready = sum(1 for t in ai_tools if t.get("installed"))
    tools_running = sum(1 for t in ai_tools if t.get("running"))
    agents_running = sum(1 for a in agent_rows if a.get("status") == "running")
    health_score = 100
    if system["disk_pct"] and system["disk_pct"] >= 90:
        health_score -= 22
    if system["load"] and system["load"] >= 8:
        health_score -= 14
    if service_rows:
        health_score -= int((len(service_rows) - online) / len(service_rows) * 18)
    if memory["pending"] > 10:
        health_score -= 8
    health_score = max(0, min(100, health_score))

    # 最近动态时间轴：跨来源（资讯 / X / 洞察 / 反思 等），刻意排除 GitHub 项目，
    # 避免与上方「GitHub 高价值项目」板块重复。
    recent_alerts = []
    seen_titles: set[str] = set()
    for item in (briefing.get("items") or []):
        if item.get("kind") in {"github_repo"}:
            continue
        title = item.get("title") or ""
        key = re.sub(r"\s+", "", title.lower())[:40]
        if key and key in seen_titles:
            continue
        seen_titles.add(key)
        recent_alerts.append({
            "id": item.get("event_id"),
            "title": title,
            "source": item.get("source"),
            "kind": _kind_label(item.get("kind")),
            "ts": item.get("ts"),
            "url": item.get("url"),
            "summary": item.get("take"),
            "why": item.get("why_important"),
            "next_step": item.get("next_step"),
        })
        if len(recent_alerts) >= 8:
            break

    return {
        "generated_at": int(time.time()),
        "health": {
            "score": health_score,
            "system": system,
            "services_online": online,
            "services_total": len(service_rows),
        },
        "services": service_rows,
        "notifications": notifications,
        "weather": weather,
        "runtime": {
            "services_online": online,
            "services_total": len(service_rows),
            "tools_ready": tools_ready,
            "tools_total": len(ai_tools),
            "tools_running": tools_running,
            "agents_running": agents_running,
            "agents_total": len(agent_rows),
            "ai_tools": ai_tools,
            "agents": agent_rows,
        },
        "briefing": {
            "business": len(briefing.get("business", [])),
            "life": len(briefing.get("life", [])),
            "top": (briefing.get("business", []) + briefing.get("life", []))[:5],
        },
        "intelligence": {
            "events": len(intel_events),
            "github_repos": len(github_cards),
            "top_repos": github_cards,
        },
        "notes": notes,
        "memory": memory,
        "signals": {
            "triage": _judgment_distribution(),
            "sources": _source_distribution(events),
        },
        "timeline": recent_alerts,
    }
