"""记忆反思（M2）。

定期把零散的 events 归纳成“待确认长期记忆”：偏好、模式、结论。
有 LLM 时让模型归纳；无 LLM 时退化为基于频次的确定性归纳，保证闭环不依赖外部接口。
候选结论需要用户确认后才会变成 active 记忆。
"""
from __future__ import annotations

import json
import time
from collections import Counter

from .. import db
from ..config import settings
from .profile import profile_text

_REFLECT_SYSTEM = """你是 Leo 的私人记忆官。下面是 Leo 近期的事件流（对话、agent 动作、个人记事、反馈过的信息）。
请只归纳“可能值得长期记住、但必须由 Leo 确认”的候选结论：Leo 的偏好、工作习惯、反复出现的流程、长期关注方向、需要跟进的承诺。
硬规则：不要把单条新闻、RSS 标题、GitHub 项目、网页变化或普通笔记原文当成长期记忆；只能在它们反复体现 Leo 的偏好/行为模式时提炼为模式。
不要复述事件，要提炼。每条要具体、可复用。
只输出 JSON 数组，每个元素：
{"type":"semantic|episodic","subject":"实体或主题","statement":"一句话结论","salience":0.0-1.0}
最多 8 条，salience 表示重要性。"""

_MEMORY_SOURCE_PREFIXES = ("agent", "personal_note", "journal", "reflection")
_SIGNAL_SOURCES = ("intel", "rss")


def _recent_events(hours: int, limit: int = 200) -> list:
    since = int((time.time() - hours * 3600) * 1000)
    return db.query_events(since, limit=limit)


def _memory_worthy_rows(rows: list) -> list:
    filtered = []
    signal_votes = Counter()
    for r in rows:
        source = str(r["source"] or "")
        kind = str(r["kind"] or "")
        title = str(r["title"] or "")
        content = str(r["content"] or "")
        if source.startswith(_MEMORY_SOURCE_PREFIXES):
            filtered.append(r)
            continue
        if source.startswith(_SIGNAL_SOURCES):
            # 资讯/GitHub 只作为“偏好证据”，不允许原样进长期记忆。
            words = [w for w in (title + " " + content).replace("/", " ").replace("，", " ").split() if len(w) >= 2]
            for word in words[:12]:
                signal_votes[word[:40]] += 1
            continue
        if kind in {"action", "insight"}:
            filtered.append(r)
    for word, n in signal_votes.most_common(8):
        if n >= 3:
            filtered.append({"source": "signal_pattern", "kind": "preference", "title": word,
                             "content": f"近期情报中 {word} 反复出现 {n} 次，可作为关注倾向证据。"})
    return filtered


def _fallback_reflect(rows: list) -> list[dict]:
    """无 LLM 时：只按可长期复用的行为/偏好证据归纳，不把新闻或笔记原文塞进记忆。"""
    subjects = Counter()
    sources = Counter()
    for r in _memory_worthy_rows(rows):
        sources[str(r["source"])] += 1
        title = str(r["title"] or "").strip()
        if title and str(r["source"]).startswith(("agent", "personal_note", "signal_pattern")):
            subjects[title[:32]] += 1
    out: list[dict] = []
    for subject, n in subjects.most_common(5):
        if n >= 2:
            out.append({"type": "semantic", "subject": subject,
                        "statement": f"Leo 近期反复围绕『{subject}』行动或反馈，可能是当前工作/关注习惯的一部分。",
                        "salience": min(0.85, 0.45 + n * 0.08)})
    for src, n in sources.most_common(3):
        if src in {"rss", "intel"}:
            continue
        if n >= 3:
            out.append({"type": "episodic", "subject": src,
                        "statement": f"Leo 近期频繁使用 {src} 相关能力（{n} 次），可作为工作流偏好候选。",
                        "salience": 0.55})
    return out


def reflect(hours: int = 24) -> dict:
    rows = _recent_events(hours)
    if not rows:
        return {"ok": True, "created": 0, "note": "近期没有事件可反思。"}

    memory_rows = _memory_worthy_rows(rows)
    if not memory_rows:
        return {"ok": True, "created": 0, "events": len(rows), "note": "近期事件主要是资讯/项目/网页变化，没有足够的使用习惯证据生成长期记忆。"}

    digest = "\n".join(
        f"- [{r['source']}/{r['kind']}] {r['title'] or ''} {(r['content'] or '')[:120]}"
        for r in memory_rows[:120]
    )

    insights: list[dict] = []
    used_llm = False
    if settings().get("judge", {}).get("fallback_judge", True) is not None:
        try:
            from ..models_router import chat
            raw = chat("reflect", [
                {"role": "system", "content": _REFLECT_SYSTEM},
                {"role": "user", "content": f"## Leo 画像\n{profile_text()}\n\n## 近期事件\n{digest}"},
            ], temperature=0.3)
            start, end = raw.find("["), raw.rfind("]")
            insights = json.loads(raw[start:end + 1]) if start >= 0 else []
            used_llm = True
        except Exception:
            insights = []

    if not insights:
        insights = _fallback_reflect(memory_rows)

    created = 0
    for it in insights:
        stmt = str(it.get("statement", "")).strip()
        if not stmt:
            continue
        db.insert_memory(
            stmt, memory_type=it.get("type", "semantic"),
            subject=it.get("subject"),
            confidence=0.75, salience=float(it.get("salience", 0.5)),
        )
        created += 1

    # 反思自我记录。实际长期记忆需用户在前端确认后才 active。
    db.insert_event(source="reflection", kind="insight", domain="business",
                    title=f"反思：生成 {created} 条待确认记忆",
                    content=f"{'LLM' if used_llm else '规则'}从 {len(rows)} 条事件筛出 {len(memory_rows)} 条习惯证据 -> {created} 条待确认记忆",
                    meta={"used_llm": used_llm, "created": created, "memory_evidence_events": len(memory_rows)})
    return {
        "ok": True,
        "created": created,
        "used_llm": used_llm,
        "events": len(rows),
        "memory_evidence_events": len(memory_rows),
        "note": f"已从使用/行为证据中生成 {created} 条待确认记忆；新闻、普通笔记和项目条目不会原样写入长期记忆。",
    }
