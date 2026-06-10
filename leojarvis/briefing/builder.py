from __future__ import annotations

import json
import re
import time
import html
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


def _is_email(row: dict) -> bool:
    return row.get("kind") == "email" or str(row.get("source") or "").startswith("email:")


def _is_x(row: dict) -> bool:
    source = str(row.get("source") or "")
    meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
    return row.get("kind") == "x_post" or source.startswith("intel:x:") or source.startswith("rss:X ·") or meta.get("channel") == "x_monitor"


def _looks_like_fallback(text: str | None) -> bool:
    value = str(text or "")
    return (
        value.startswith("英文来源摘要")
        or "英文来源摘要：" in value
        or value.startswith("中文摘要：")
    )


def _x_topic(text: str) -> str:
    raw = str(text or "").lower()
    terms: list[str] = []
    for needle, label in [
        ("grok", "Grok"),
        ("gemma", "Gemma"),
        ("claude", "Claude"),
        ("chatgpt", "ChatGPT"),
        ("openai", "OpenAI"),
        ("deepseek", "DeepSeek"),
        ("cursor", "Cursor"),
        ("langchain", "LangChain"),
        ("nvidia", "NVIDIA"),
        ("agent", "智能体"),
        ("model", "模型"),
        ("api", "API"),
        ("research", "研究"),
        ("benchmark", "基准测试"),
        ("coding", "编程"),
        ("code", "代码"),
        ("release", "发布"),
        ("launch", "发布"),
        ("open source", "开源"),
        ("multimodal", "多模态"),
    ]:
        if needle in raw and label not in terms:
            terms.append(label)
        if len(terms) >= 3:
            break
    return "、".join(terms) if terms else "AI 科技"


def _x_handle(meta: dict, row: dict) -> str:
    handle = str(meta.get("handle") or meta.get("feed_name") or row.get("source") or "X 监控")
    handle = handle.replace("intel:x:", "").replace("rss:", "").replace("X · ", "").strip()
    return handle if handle.startswith("@") else f"@{handle.lstrip('@')}"


def _x_display_title(row: dict, meta: dict) -> str:
    material = " ".join(str(x or "") for x in [row.get("title"), row.get("content"), meta.get("original_title")])
    return f"{_x_handle(meta, row)}｜{_x_topic(material)}动态"


def _x_display_summary(row: dict, meta: dict) -> str:
    material = " ".join(str(x or "") for x in [row.get("title"), row.get("content"), meta.get("original_title")])
    return f"来自 {_x_handle(meta, row)} 的 X 监控动态，主题集中在 {_x_topic(material)}。建议打开原帖确认上下文、回复和引用，再决定是否加入持续关注或个人记事。"


def _source_label(source: str | None) -> str:
    if not source:
        return "未知来源"
    if source.startswith("email:"):
        return "Apple Mail" if "Apple Mail" in source else "邮箱"
    if source.startswith("intel:x:") or source.startswith("rss:X ·"):
        return "X 监控"
    if source.startswith("intel:rss:"):
        return "RSS 资讯"
    if source.startswith("intel:web:"):
        return "网页变化"
    if source.startswith("rss:"):
        return "RSS 资讯"
    if source.startswith("intel:"):
        return {
            "intel:github": "GitHub 项目雷达",
            "intel:rss": "RSS 资讯",
            "intel:x": "X 监控",
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
        meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
        return meta.get("next_step_zh") or "打开项目页，重点看 README、最近提交和可本地部署能力，再决定是否加入持续监控。"
    if _is_email(row):
        return "在 Apple Mail 里处理这封邮件；如不想展示已读邮件，可在设置里打开“只读未读”。"
    if _is_x(row):
        return "打开原帖确认上下文和评论信号，必要时把相关主题加入持续关注项。"
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
    if _is_email(row):
        return "来自你本机 Apple Mail 已授权邮箱，已进入 LeoJarvis 今日邮件摘要。"
    if _is_x(row):
        return "来自你配置的 X AI/科技监控源，适合捕捉官方发布、研究人员观点和早期趋势信号。"
    return to_chinese(
        f"它来自你配置的情报源或关注项，当前评分 {row.get('score', 0):.2f}，值得按优先级处理。",
        context="简报个性化关联",
        max_chars=160,
    )


def _why(row: dict, reasons: list[str]) -> str:
    if reasons:
        return to_chinese("；".join(reasons[:3]), context="简报重要性原因", max_chars=180)
    return to_chinese(row.get("take") or "该信息通过情报评分进入简报，可能影响今天的判断。", context="简报重要性原因", max_chars=180)


def _safe_tag(text: str) -> str:
    text = re.sub(r"^(英文来源摘要|中文摘要)[:：]\s*", "", str(text or "").strip())
    text = text.replace("相关动态", "")
    text = re.sub(r"[。；;，,].*$", "", text)
    text = text.strip()
    if not text or len(text) > 22:
        return ""
    return text


def _tags(row: dict, meta: dict, reasons: list[str]) -> list[str]:
    raw: list[str] = []
    for key in ("display_topics", "topics", "tags"):
        value = meta.get(key)
        if isinstance(value, list):
            raw.extend(str(v) for v in value)
    raw.extend(re.findall(r"[\u3400-\u9fffA-Za-z0-9.+-]{2,}", " ".join(reasons))[:4])
    if _is_github(row):
        raw.append("GitHub 项目")
    if _is_x(row):
        raw.append("X 监控")
    raw.append(_domain_label(row.get("domain")))
    tags = []
    for tag in chinese_tags(raw):
        clean = _safe_tag(tag)
        if clean and clean not in tags:
            tags.append(clean)
        if len(tags) >= 6:
            break
    return tags


def _detail_from(row: dict, analysis: dict, reasons: list[str], fallback: str) -> str:
    parts = []
    for key in ("detail", "impact", "evidence", "background"):
        value = analysis.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    content = html.unescape(re.sub(r"<[^>]+>", " ", str(row.get("content") or ""))).strip()
    if content and content not in " ".join(parts):
        parts.append(content[:900])
    text = "\n\n".join(dict.fromkeys(parts)) or fallback
    raw_detail = text[:1100].strip()
    translated = to_chinese(raw_detail, context="简报详情", max_chars=760)
    if _looks_like_fallback(translated) or ("相关动态" in translated and re.search(r"https?://|Article URL|Comments URL", raw_detail, re.I)):
        return raw_detail
    return translated


def _briefing_item(row: dict, memories: list[str], github_lookup: dict[str, dict] | None = None) -> dict:
    meta = _loads(row.get("meta"), {})
    reasons = _loads(row.get("reasons"), [])
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    analysis = _loads(row.get("analysis"), {}) or {}
    github_lookup = github_lookup or {}
    repo_name = meta.get("repo") or (row.get("title") or "").replace(" · GitHub 项目雷达", "")
    repo_snapshot = github_lookup.get(repo_name, {}) if _is_github(row) else {}

    if _is_github(row):
        title = analysis.get("title_zh") or f"{repo_name} · GitHub 高增速项目"
    elif _is_email(row):
        title = row.get("title") or "（无主题邮件）"
    elif _is_x(row):
        title = analysis.get("title_zh") or to_chinese(row.get("title") or "X 监控动态", context="X 监控标题", max_chars=120)
        if _looks_like_fallback(title):
            title = _x_display_title(row, meta)
    else:
        # 优先用判断器产出的中文标题，没有再回退到翻译，避免英文标题外泄
        title = analysis.get("title_zh") or to_chinese(row.get("title") or "未命名信息", context="简报标题", max_chars=120)

    # take / why / relation / next_step 一律优先用 LLM 产出的真实分析，没有才回退模板
    take = analysis.get("summary") or analysis.get("take") \
        or to_chinese(row.get("take") or row.get("content") or "", context="简报摘要", max_chars=220)
    if _is_github(row) and repo_snapshot:
        take = repo_snapshot.get("summary_zh") or repo_snapshot.get("display_description") or take
    if _is_x(row) and _looks_like_fallback(take):
        take = _x_display_summary(row, meta)
    priority = _priority(float(row.get("score") or 0), row.get("triage") or "digest")
    why = analysis.get("why") or _why(row, reasons)
    relation = analysis.get("relation") or _relation(row, reasons, memories)
    next_step = analysis.get("next_step") or _next_step(row, priority)
    detail = _detail_from(row, analysis, reasons, take)
    if _is_github(row) and repo_snapshot:
        stars = int(repo_snapshot.get("stars") or meta.get("stars") or 0)
        speed = repo_snapshot.get("stars_per_day") or repo_snapshot.get("cold_stars_per_day")
        topics = "、".join(repo_snapshot.get("display_topics") or []) or "GitHub 项目"
        take = repo_snapshot.get("summary_zh") or repo_snapshot.get("display_description") or take
        why = repo_snapshot.get("why_zh") or why
        relation = repo_snapshot.get("relation_zh") or relation
        next_step = repo_snapshot.get("next_step_zh") or next_step
        metric_parts = [
            f"{stars:,} 星标",
            f"动量约 {speed}/天" if speed is not None else "动量观察中",
            f"主要语言 {repo_snapshot.get('language') or meta.get('language') or '未知'}",
            f"主题 {topics}",
        ]
        detail = f"仓库介绍：{take}\n项目指标：{'；'.join(metric_parts)}。"
    if _is_x(row) and _looks_like_fallback(detail):
        detail = _x_display_summary(row, meta)
    item_tags = _tags(row, meta, reasons)
    if _is_github(row) and repo_snapshot.get("display_topics"):
        item_tags = list(dict.fromkeys((repo_snapshot.get("display_topics") or []) + ["GitHub 项目"]))[:6]
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
        "repo_stars": (repo_snapshot.get("stars") or meta.get("stars")) if _is_github(row) else None,
        "repo_speed": (repo_snapshot.get("stars_per_day") or velocity.get("stars_per_day")) if _is_github(row) else None,
        "channel": "x_monitor" if _is_x(row) else ("mail" if _is_email(row) else meta.get("channel")),
        "category": meta.get("category"),
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


_TOKEN_STOPWORDS = {
    "github", "项目", "发布", "推出", "宣布", "正式", "全新", "重磅", "首个", "首次",
    "the", "and", "for", "with", "from", "into", "new", "now", "via", "how", "why",
    "what", "your", "this", "that", "are", "has", "have", "will", "can", "all",
}


def _title_tokens(title: str) -> set[str]:
    """标题 → 关键词集合：ASCII 词（含单数字版本号）+ 中文双字组，用于相似聚类。"""
    text = re.sub(r"https?://\S+", "", (title or "").lower())
    ascii_words = {w for w in re.findall(r"[a-z0-9][a-z0-9_.+-]*", text) if w not in _TOKEN_STOPWORDS}
    cjk_runs = re.findall(r"[㐀-鿿]{2,}", text)
    bigrams: set[str] = set()
    for run in cjk_runs:
        bigrams.update(b for b in (run[i:i + 2] for i in range(len(run) - 1))
                       if b not in _TOKEN_STOPWORDS)
    return ascii_words | bigrams


def _cluster_similar(items: list[dict]) -> list[dict]:
    """把同一事件/同一主角的多来源报道折叠成一条主条目。

    简单标题归一只能去掉完全相同的标题；同一新闻在不同 RSS 源里标题各异
    （「Anthropic 发布 Claude Fable 5」vs「Claude Fable 5 初步印象」），
    会让简报里同一件事霸屏。按关键词重合度聚类，主条目取分数最高的一条，
    其余来源折叠进 related_sources，前端显示「N 个来源同时报道」。
    """
    kept: list[dict] = []
    kept_tokens: list[set[str]] = []
    for item in items:
        if item.get("kind") == "github_repo":
            kept.append(item)
            kept_tokens.append(set())
            continue
        tokens = _title_tokens(str(item.get("title") or "")) | _title_tokens(str(item.get("original_title") or ""))
        merged = False
        if len(tokens) >= 2:
            for idx, other in enumerate(kept_tokens):
                if not other:
                    continue
                overlap = len(tokens & other)
                if overlap < 2:
                    continue
                jaccard = overlap / len(tokens | other)
                containment = overlap / min(len(tokens), len(other))
                if jaccard >= 0.4 or containment >= 0.75:
                    primary = kept[idx]
                    related = primary.setdefault("related_sources", [])
                    if len(related) < 8:
                        related.append({
                            "event_id": item.get("event_id"),
                            "title": item.get("title"),
                            "source": item.get("source"),
                            "url": item.get("url"),
                        })
                    primary["dup_count"] = int(primary.get("dup_count") or 0) + 1
                    merged = True
                    break
        if merged:
            continue
        kept.append(item)
        kept_tokens.append(tokens)
    return kept


def _apply_priority_quota(items: list[dict]) -> None:
    """重排优先级：高优先是配额制的稀缺标签，不是分数阈值的副产品。

    画像命中型打分会让 AI 主题的整版资讯都≥0.78，结果满屏「高优先」——
    等于没有优先级。这里按当日分数排名重新分层：notify 触发的保底高优先，
    其余高优先最多 15%（≤6 条），其后 35% 为中优先，剩下是观察。
    """
    news = [it for it in items if it.get("kind") != "github_repo"]
    repos = [it for it in items if it.get("kind") == "github_repo"]
    if news:
        ranked = sorted(news, key=lambda it: -float(it.get("score") or 0))
        high_quota = max(1, min(6, round(len(ranked) * 0.15)))
        mid_quota = max(2, round(len(ranked) * 0.35))
        for idx, item in enumerate(ranked):
            if item.get("triage") == "notify":
                item["priority"] = "高优先"
            elif idx < high_quota and float(item.get("score") or 0) >= 0.6:
                item["priority"] = "高优先"
            elif idx < high_quota + mid_quota and float(item.get("score") or 0) >= 0.45:
                item["priority"] = "中优先"
            else:
                item["priority"] = "观察"
    if repos:
        # GitHub 雷达有自己的版块和动量排序，优先级只用来挑出头部几个。
        ranked_repos = sorted(repos, key=lambda it: (-float(it.get("repo_speed") or 0), -float(it.get("score") or 0)))
        for idx, item in enumerate(ranked_repos):
            item["priority"] = "高优先" if idx < 5 else ("中优先" if idx < 14 else "观察")


def _today_focus_text(items: list[dict]) -> str:
    if not items:
        return "今天还没有足够高价值的情报进入焦点。可以先运行采集或调整 RSS / X 监控源。"
    high = [it for it in items if it.get("priority") == "高优先" and it.get("kind") != "github_repo"]
    top = (high or items)[:3]
    lead = top[0]
    lead_take = str(lead.get("take") or "").split("。")[0].strip()
    if len(lead_take) > 110:
        # 在最近的次级标点处收口，避免把数字/词语拦腰截断。
        cut = max(lead_take.rfind(ch, 0, 110) for ch in "，、；,;")
        lead_take = lead_take[:cut] if cut > 30 else lead_take[:110]
    parts = [f"今天最值得看的是「{lead.get('title')}」"]
    if lead_take and lead_take != lead.get("title"):
        parts.append(f"——{lead_take}。")
    else:
        parts.append("。")
    if len(top) > 1:
        rest = "、".join(f"「{it.get('title')}」" for it in top[1:])
        parts.append(f"其次可以关注{rest}。")
    repo_count = sum(1 for it in items if it.get("kind") == "github_repo")
    if repo_count:
        parts.append(f"GitHub 雷达另有 {repo_count} 个高增速项目值得扫一眼。")
    return "".join(parts)


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
    try:
        from ..intelligence.scanner import github_radar
        github_lookup = {r.get("repo_full_name"): r for r in github_radar(limit=120) if r.get("repo_full_name")}
    except Exception:
        github_lookup = {}
    seen: set[str] = set()
    items: list[dict] = []
    mail_items: list[dict] = []
    duplicate_count = 0
    for raw in rows:
        row = dict(raw)
        key = _clean_key(row.get("title") or row.get("content") or row["event_id"])
        if key and key in seen:
            duplicate_count += 1
            continue
        if key:
            seen.add(key)
        raw_meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
        raw_repo = raw_meta.get("repo") or (row.get("title") or "").replace(" · GitHub 项目雷达", "")
        if _is_github(row) and github_lookup and raw_repo not in github_lookup:
            continue
        item = _briefing_item(row, memories, github_lookup)
        if _is_email(row):
            mail_items.append(item)
        else:
            items.append(item)

    clustered_away = len(items)
    items = _cluster_similar(items)
    clustered_away -= len(items)
    duplicate_count += clustered_away
    _apply_priority_quota(items)

    business = [it for it in items if it["domain"] == "business"]
    life = [it for it in items if it["domain"] == "life"]
    x_items = [it for it in items if it.get("channel") == "x_monitor" or it.get("kind") == "x_post"]
    github_items = [it for it in items if it.get("kind") == "github_repo"]
    sources = Counter(it["source"] for it in items)
    priorities = Counter(it["priority"] for it in items)
    tags = Counter(tag for it in items for tag in it.get("tags", []))

    return {
        "generated_at": int(time.time()),
        "business": business,
        "life": life,
        "items": items,
        "mail": mail_items,
        "x": x_items,
        "github": github_items,
        "focus": items[:5],
        "groups": _group_items(items),
        "counts": {
            "business": len(business),
            "life": len(life),
            "total": len(items),
            "mail": len(mail_items),
            "x": len(x_items),
            "github": len(github_items),
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
