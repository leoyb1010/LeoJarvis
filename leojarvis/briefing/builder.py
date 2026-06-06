from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from typing import Any

from .. import db
from ..localize import chinese_tags as _chinese_tags, to_chinese as _to_chinese


# 简报在每次请求时构建，严禁实时 LLM 调用（翻译/分析已在 judge 阶段落库）。
# 这里统一把展示路径的本地化降级为无网络回退，保证 /cockpit/overview 秒级返回。
def to_chinese(text, *, context="通用内容", max_chars=360, allow_llm=False):
    return _to_chinese(text, context=context, max_chars=max_chars, allow_llm=allow_llm)


def chinese_tags(raw, *, allow_llm=False):
    return _chinese_tags(raw, allow_llm=allow_llm)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _clean_key(title: str) -> str:
    text = re.sub(r"https?://\S+", "", title or "")
    text = re.sub(r"[^\w\u3400-\u9fff]+", "", text.lower())
    return text[:72]


def _priority(score: float, triage: str) -> str:
    if triage == "notify" or score >= 0.78:
        return "高优先"
    if score >= 0.55:
        return "中优先"
    return "观察"


def _domain_label(domain: str | None) -> str:
    return "生活" if domain == "life" else "业务"


def _is_github(row: dict) -> bool:
    return row.get("kind") == "github_repo" or row.get("source") in {"github_radar", "intel:github"}


def _source_label(source: str | None) -> str:
    if not source:
        return "未知来源"
    if source.startswith("email:"):
        return "Apple Mail" if "Apple Mail" in source else "邮箱"
    if source.startswith("rss:"):
        return "RSS 资讯"
    if source.startswith("intel:"):
        return {
            "intel:github": "GitHub 项目雷达",
            "intel:rss": "RSS 资讯",
            "intel:web": "网页变化",
        }.get(source, "情报中心")
    return {
        "intel": "情报中心",
        "intel:github": "GitHub 项目雷达",
        "intel:rss": "RSS 资讯",
        "intel:web": "网页变化",
        "rss": "RSS 资讯",
        "github_radar": "GitHub 项目雷达",
        "personal_note": "个人记事",
        "journal": "旧记录",
        "reflection": "记忆反思",
        "test": "测试数据",
    }.get(source, source)


def _next_step(row: dict, priority: str) -> str:
    if _is_github(row):
        return "打开项目页，判断是否需要加入情报关注项或记录到个人记事。"
    if str(row.get("source") or "").startswith("email:"):
        return "在 Apple Mail 里处理这封邮件；如不想展示已读邮件，可在设置里打开“只读未读”。"
    if priority == "高优先":
        return "优先阅读原文，并用“重要/没用”反馈更新判断偏好。"
    if priority == "中优先":
        return "保留在今日简报中观察，必要时补充成个人记事。"
    return "暂不打断，只在简报中留痕。"


def _relation(row: dict, reasons: list[str], memories: list[str]) -> str:
    material = "；".join(reasons[:2]) or row.get("take") or row.get("title") or ""
    if memories:
        return to_chinese(
            f"这条信息可能关联你的长期关注：{'; '.join(memories[:3])}。判断依据：{material}",
            context="简报个性化关联",
            max_chars=180,
        )
    if str(row.get("source") or "").startswith("email:"):
        return "来自你本机 Apple Mail 已授权邮箱，已进入 LeoJarvis 今日邮件摘要。"
    return to_chinese(
        f"它来自你配置的情报源或关注项，当前评分 {row.get('score', 0):.2f}，值得按优先级处理。",
        context="简报个性化关联",
        max_chars=160,
    )


def _why(row: dict, reasons: list[str]) -> str:
    if reasons:
        return to_chinese("；".join(reasons[:3]), context="简报重要性原因", max_chars=180)
    return to_chinese(row.get("take") or "该信息通过情报评分进入简报，可能影响今天的判断。", context="简报重要性原因", max_chars=180)


def _tags(row: dict, meta: dict, reasons: list[str]) -> list[str]:
    raw: list[str] = []
    for key in ("display_topics", "topics", "tags"):
        value = meta.get(key)
        if isinstance(value, list):
            raw.extend(str(v) for v in value)
    raw.extend(re.findall(r"[\u3400-\u9fffA-Za-z0-9.+-]{2,}", " ".join(reasons))[:4])
    if _is_github(row):
        raw.append("GitHub 项目")
    raw.append(_domain_label(row.get("domain")))
    return chinese_tags(raw)[:6]


def _detail_from(row: dict, analysis: dict, reasons: list[str], fallback: str) -> str:
    parts = []
    for key in ("detail", "impact", "evidence", "background"):
        value = analysis.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    content = str(row.get("content") or "").strip()
    if content and content not in " ".join(parts):
        parts.append(content[:900])
    if reasons:
        parts.append("判断依据：" + "；".join(str(r) for r in reasons[:4]))
    text = "\n\n".join(dict.fromkeys(parts)) or fallback
    return to_chinese(text, context="简报详情", max_chars=760)


def _briefing_item(row: dict, memories: list[str]) -> dict:
    meta = _loads(row.get("meta"), {})
    reasons = _loads(row.get("reasons"), [])
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    analysis = _loads(row.get("analysis"), {}) or {}

    if _is_github(row):
        repo_name = meta.get("repo") or (row.get("title") or "").replace(" · GitHub 项目雷达", "")
        title = f"{repo_name} · GitHub 项目雷达"
    elif str(row.get("source") or "").startswith("email:"):
        title = row.get("title") or "（无主题邮件）"
    else:
        # 优先用判断器产出的中文标题，没有再回退到翻译，避免英文标题外泄
        title = analysis.get("title_zh") or to_chinese(row.get("title") or "未命名信息", context="简报标题", max_chars=120)

    # take / why / relation / next_step 一律优先用 LLM 产出的真实分析，没有才回退模板
    take = analysis.get("summary") or analysis.get("take") \
        or to_chinese(row.get("take") or row.get("content") or "", context="简报摘要", max_chars=220)
    priority = _priority(float(row.get("score") or 0), row.get("triage") or "digest")
    why = analysis.get("why") or _why(row, reasons)
    relation = analysis.get("relation") or _relation(row, reasons, memories)
    next_step = analysis.get("next_step") or _next_step(row, priority)
    detail = _detail_from(row, analysis, reasons, take)
    item_tags = _tags(row, meta, reasons)
    velocity = meta.get("velocity") if isinstance(meta.get("velocity"), dict) else {}
    return {
        "event_id": row["event_id"],
        "title": title,
        "original_title": meta.get("original_title") or row.get("title"),
        "url": row.get("url"),
        "domain": row.get("domain") or "business",
        "domain_label": _domain_label(row.get("domain")),
        "source": _source_label(row.get("source")),
        "source_raw": row.get("source"),
        "kind": row.get("kind"),
        "score": round(float(row.get("score") or 0), 3),
        "take": take or "暂无摘要。",
        "detail": detail,
        "triage": row.get("triage") or "digest",
        "priority": priority,
        "reasons": [to_chinese(str(r), context="简报判断原因", max_chars=100) for r in reasons[:4]],
        "why_important": why,
        "relation": relation,
        "next_step": next_step,
        "tags": item_tags,
        "ts": row.get("ts"),
        "repo_stars": meta.get("stars") if _is_github(row) else None,
        "repo_speed": velocity.get("stars_per_day") if _is_github(row) else None,
    }


def _active_memory_snippets(limit: int = 6) -> list[str]:
    try:
        rows = db.list_memories(limit=limit * 3)
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        text = re.sub(r"rss:[A-Za-z0-9_.-]+", "RSS 资讯", str(r["statement"]))
        text = to_chinese(text, context="长期记忆片段", max_chars=90)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _group_items(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        key = item["tags"][0] if item.get("tags") else item["domain_label"]
        groups[key].append(item)
    out = []
    for name, rows in groups.items():
        out.append({
            "name": name,
            "count": len(rows),
            "top_score": max(r["score"] for r in rows),
            "items": rows[:4],
        })
    return sorted(out, key=lambda g: (-g["top_score"], -g["count"], g["name"]))[:8]


def _today_focus_text(items: list[dict]) -> str:
    if not items:
        return "今天还没有足够高价值的情报进入焦点。可以先运行采集或调整 RSS / X 监控源。"
    top = items[:3]
    return "今日重点：" + "；".join(f"{it.get('priority', '观察')}｜{it.get('title')}" for it in top)


def build_today() -> dict:
    since = int((time.time() - 24 * 3600) * 1000)
    with db.conn() as c:
        rows = c.execute(
            """
            SELECT e.id AS event_id, e.title, e.content, e.url, e.domain, e.source, e.kind, e.meta,
                   j.score, j.take, j.triage, j.reasons, j.analysis, j.ts
            FROM judgments j JOIN events e ON e.id=j.event_id
            WHERE j.ts>=? AND j.triage IN ('notify','digest')
            ORDER BY j.score DESC, j.ts DESC
            """,
            (since,),
        ).fetchall()

    memories = _active_memory_snippets()
    seen: set[str] = set()
    items: list[dict] = []
    duplicate_count = 0
    for raw in rows:
        row = dict(raw)
        key = _clean_key(row.get("title") or row.get("content") or row["event_id"])
        if key and key in seen:
            duplicate_count += 1
            continue
        if key:
            seen.add(key)
        items.append(_briefing_item(row, memories))

    business = [it for it in items if it["domain"] == "business"]
    life = [it for it in items if it["domain"] == "life"]
    sources = Counter(it["source"] for it in items)
    priorities = Counter(it["priority"] for it in items)
    tags = Counter(tag for it in items for tag in it.get("tags", []))

    return {
        "generated_at": int(time.time()),
        "business": business,
        "life": life,
        "items": items,
        "focus": items[:5],
        "groups": _group_items(items),
        "counts": {
            "business": len(business),
            "life": len(life),
            "total": len(items),
            "duplicates_removed": duplicate_count,
        },
        "filters": {
            "sources": [{"name": k, "count": v} for k, v in sources.most_common()],
            "priorities": [{"name": k, "count": v} for k, v in priorities.most_common()],
            "tags": [{"name": k, "count": v} for k, v in tags.most_common(12)],
        },
        "summary": {
            "today_focus": _today_focus_text(items),
            "why_it_matters": "只保留有信号的内容：优先级、证据、与你的关系和下一步被拆开呈现，避免重复套话。",
            "next_action": "先看高优先焦点，再把有价值的信息写入个人记事或反馈为重要。",
        },
    }
