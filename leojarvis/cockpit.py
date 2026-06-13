from __future__ import annotations

import re
import time
from collections import Counter

from . import db, personal_notes
from .agent import services, sysinfo
from .briefing.builder import _github_source_detail, _translate_source_detail, build_today
from .intelligence.scanner import github_radar, recent_intelligence_events
from .localize import chinese_tags as _chinese_tags, has_noisy_english, to_chinese as _to_chinese


# 驾驶舱每 8 秒被前端轮询，展示路径禁止实时 LLM；本地化只做无网络回退。
def to_chinese(text, *, context="通用内容", max_chars=360, allow_llm=False):
    return _to_chinese(text, context=context, max_chars=max_chars, allow_llm=allow_llm)


def chinese_tags(raw, *, allow_llm=False):
    return _chinese_tags(raw, allow_llm=allow_llm)


def _parse_system(raw: str) -> dict:
    disk = re.search(r"\((\d+)%\)", raw)
    load = re.search(r"负载\(1/5/15min\):\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+).*CPU 核数 (\d+)", raw)
    mem = re.search(r"内存:.*?(\d+)%", raw)
    disk_pct = int(disk.group(1)) if disk else None
    load_value = float(load.group(1)) if load else None
    cores = int(load.group(4)) if load else None
    mem_free = int(mem.group(1)) if mem else None
    return {"raw": raw, "disk_pct": disk_pct, "load": load_value, "load_5": float(load.group(2)) if load else None,
            "load_15": float(load.group(3)) if load else None, "cores": cores,
            "load_pct": round(load_value / max(1, cores) * 100, 1) if load_value is not None and cores else None,
            "memory_free_pct": mem_free, "memory_used_pct": 100 - mem_free if mem_free is not None else None}


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
            "email": "邮件",
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
        "email": "邮件",
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


def _repo_summary_zh(repo: dict, name: str, *, fallback: str = "") -> str:
    summary = str(repo.get("summary_zh") or "").strip()
    if summary and "英文来源摘要" not in summary and not has_noisy_english(summary):
        return summary[:240]
    raw = str(repo.get("display_description") or repo.get("description") or fallback or "").strip()
    if raw:
        zh = to_chinese(raw, context="驾驶舱 GitHub 项目介绍", max_chars=180, allow_llm=False)
        if zh and "英文来源摘要" not in zh and not has_noisy_english(zh):
            return f"{name}：{zh}"[:240]
    topics = chinese_tags(repo.get("display_topics") or repo.get("topics") or [], allow_llm=False)
    language = str(repo.get("language") or "").strip()
    signals = []
    if topics:
        signals.append("主题：" + "、".join(topics[:4]))
    if language:
        signals.append(f"主要语言：{language}")
    if _repo_speed(repo):
        signals.append(f"增长约 {_repo_speed(repo):.1f}/天")
    suffix = "；".join(signals) if signals else "需打开 README 确认具体用途"
    return f"{name} 已进入 GitHub 雷达，{suffix}。"


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
        summary = _repo_summary_zh(repo, name, fallback=item.get("take") or "已通过情报评分筛选，值得进入驾驶舱观察。")
        seen.add(name)
        source_detail = item.get("source_detail")
        if not source_detail:
            source_detail, _ = _translate_source_detail(_github_source_detail(name, {}, repo))
        cards.append({
            "name": name,
            "title": item.get("title"),
            "url": item.get("url"),
            "score": score,
            "summary": summary,
            "source_detail": source_detail,
            "source_detail_raw": item.get("source_detail_raw") or _github_source_detail(name, {}, repo),
            "source_detail_translated": item.get("source_detail_translated"),
            "why": repo.get("why_zh") or item.get("why_important") or "增长和活跃度达到驾驶舱展示阈值。",
            "relation": repo.get("relation_zh") or item.get("relation") or "与你的 AI、开发工具或本地助理关注项相关。",
            "next_step": repo.get("next_step_zh") or item.get("next_step") or "打开 README、示例和最近提交，判断是否值得持续监控。",
            "priority": item.get("priority") or "高优先",
            "tags": repo.get("display_topics") or item.get("tags") or ["GitHub 项目"],
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
        description = _repo_summary_zh(repo, name, fallback=f"{name} 暂未提供仓库介绍，需打开 README 判断实际用途。")
        source_detail_raw = _github_source_detail(name, {}, repo)
        source_detail, translated = _translate_source_detail(source_detail_raw)
        cards.append({
            "name": name,
            "title": f"{name} · GitHub 项目雷达",
            "url": repo.get("url"),
            "score": min(0.98, 0.72 + min(speed / 500, 0.2)),
            "summary": description,
            "source_detail": source_detail,
            "source_detail_raw": source_detail_raw,
            "source_detail_translated": translated,
            "why": f"项目有 {stars:,} 个星标，当前动量约 {speed}/天，满足驾驶舱高价值阈值。",
            "relation": "与你关注的 AI 工具、本地助理、自动化或开发工作流可能相关。",
            "next_step": "打开项目页看 README 和最近提交，决定是否加入情报关注项或写入个人记事。",
            "priority": "高优先" if speed >= 25 else "中优先",
            "tags": repo.get("display_topics") or chinese_tags(repo.get("topics") or []) or ["GitHub 项目"],
            "stars": stars,
            "speed": speed,
            "star_history": repo.get("star_history") or [],
            "language": repo.get("language"),
        })
        if len(cards) >= limit:
            break
    return cards


import threading as _threading

_OVERVIEW_CACHE: dict = {"ts": 0.0, "data": None}
_OVERVIEW_TTL = 6.0
_OVERVIEW_STALE_TTL = 180.0
_OVERVIEW_LOCK = _threading.Lock()
_OVERVIEW_REFRESHING = _threading.Event()


def _placeholder_overview() -> dict:
    return {
        "generated_at": int(time.time()),
        "refreshing": True,
        "health": {
            "score": 100,
            "system": {
                "raw": "系统状态正在刷新",
                "disk_pct": None,
                "load": None,
                "load_5": None,
                "load_15": None,
                "cores": None,
                "load_pct": None,
                "memory_free_pct": None,
                "memory_used_pct": None,
            },
            "services_online": 0,
            "services_total": 0,
            "attention_items": [{"label": "状态刷新中", "level": "信息", "detail": "LeoJarvis 正在后台更新驾驶舱数据。"}],
        },
        "services": [],
        "notifications": {"items": [], "count": 0},
        "weather": {},
        "runtime": {
            "services_online": 0,
            "services_total": 0,
            "tools_ready": 0,
            "tools_total": 0,
            "tools_running": 0,
            "agents_running": 0,
            "agents_total": 0,
            "ai_tools": [],
            "agents": [],
        },
        "briefing": {"business": 0, "life": 0, "top": []},
        "intelligence": {"events": 0, "github_repos": 0, "top_repos": []},
        "notes": personal_notes.note_stats(),
        "memory": _memory_stats(),
        "signals": {"triage": {"notify": 0, "digest": 0, "ignore": 0}, "sources": []},
        "timeline": [],
    }


def _refresh_overview_background() -> None:
    if _OVERVIEW_REFRESHING.is_set():
        return
    _OVERVIEW_REFRESHING.set()

    def run() -> None:
        try:
            data = _build_overview()
            with _OVERVIEW_LOCK:
                _OVERVIEW_CACHE["data"] = data
                _OVERVIEW_CACHE["ts"] = time.time()
        finally:
            _OVERVIEW_REFRESHING.clear()

    _threading.Thread(target=run, name="cockpit-overview-refresh", daemon=True).start()


def overview(force: bool = False) -> dict:
    # 驾驶舱总览很重（系统探测 + 简报 + GitHub 雷达 + 多张表）。顶部状态条(每页)和驾驶舱
    # 同时高频轮询它，没缓存就是每页都卡。缓存过期时先返回旧快照并后台刷新，避免首屏尾延迟。
    now = time.time()
    cached = _OVERVIEW_CACHE.get("data")
    if force:
        _OVERVIEW_REFRESHING.set()
        try:
            with _OVERVIEW_LOCK:
                data = _build_overview()
                _OVERVIEW_CACHE["data"] = data
                _OVERVIEW_CACHE["ts"] = time.time()
                return data
        finally:
            _OVERVIEW_REFRESHING.clear()
    if cached is not None and not force and (now - _OVERVIEW_CACHE["ts"]) < _OVERVIEW_TTL:
        return cached
    if cached is not None and not force and (now - _OVERVIEW_CACHE["ts"]) < _OVERVIEW_STALE_TTL:
        _refresh_overview_background()
        return cached
    if cached is None and not force and _OVERVIEW_REFRESHING.is_set():
        return _placeholder_overview()
    with _OVERVIEW_LOCK:
        if _OVERVIEW_CACHE.get("data") is not None and not force and (time.time() - _OVERVIEW_CACHE["ts"]) < _OVERVIEW_TTL:
            return _OVERVIEW_CACHE["data"]
        if _OVERVIEW_CACHE.get("data") is not None and not force and (time.time() - _OVERVIEW_CACHE["ts"]) < _OVERVIEW_STALE_TTL:
            _refresh_overview_background()
            return _OVERVIEW_CACHE["data"]
        _refresh_overview_background()
        return _placeholder_overview()


def _build_overview() -> dict:
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
    attention_items = []
    if system["disk_pct"] and system["disk_pct"] >= 90:
        health_score -= 22
        attention_items.append({"label": "SSD 空间紧张", "level": "异常", "detail": f"系统盘已使用 {system['disk_pct']}%，建议清理缓存、下载和大型项目。"})
    elif system["disk_pct"] and system["disk_pct"] >= 82:
        health_score -= 10
        attention_items.append({"label": "SSD 接近高水位", "level": "注意", "detail": f"系统盘已使用 {system['disk_pct']}%，低于 80% 会更稳。"})
    if system["load_pct"] and system["load_pct"] >= 120:
        health_score -= 14
        attention_items.append({"label": "CPU 负载偏高", "level": "异常", "detail": f"1 分钟负载 {system['load']}，约为核心数的 {system['load_pct']}%。"})
    elif system["load_pct"] and system["load_pct"] >= 80:
        health_score -= 7
        attention_items.append({"label": "CPU 负载需观察", "level": "注意", "detail": f"1 分钟负载 {system['load']}，如持续偏高请看资源占用排行。"})
    if system.get("memory_used_pct") and system["memory_used_pct"] >= 90:
        health_score -= 10
        attention_items.append({"label": "RAM 压力偏高", "level": "注意", "detail": f"内存使用约 {system['memory_used_pct']}%，建议关闭高占用应用。"})
    if service_rows:
        offline = [s for s in service_rows if not s["online"]]
        health_score -= int(len(offline) / len(service_rows) * 18)
        for svc in offline[:4]:
            attention_items.append({"label": f"{svc['name']} 离线", "level": "注意", "detail": f"127.0.0.1:{svc['port']} 未监听。"})
    if memory["pending"] > 10:
        health_score -= 8
        attention_items.append({"label": "待确认记忆过多", "level": "注意", "detail": f"有 {memory['pending']} 条长期记忆候选需要人工确认。"})
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
            "attention_items": attention_items,
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
            # 驾驶舱「资讯情报」只放真正的资讯：排除 GitHub 项目（它有独立雷达栏）
            # 和邮件，按评分顺序给足条目，避免前端过滤后只剩两三条。
            "top": [
                it for it in (briefing.get("business", []) + briefing.get("life", []))
                if it.get("kind") != "github_repo"
            ][:12],
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
