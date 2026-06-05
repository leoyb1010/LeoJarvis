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

_REFLECT_SYSTEM = """你是 Leo 的私人记忆官。下面是 Leo 近期的事件流（资讯、判断、对话、agent 动作、个人记事）。
请归纳出“可能值得长期记住、但必须由 Leo 确认”的候选结论：Leo 的偏好、关注点、反复出现的模式、需要跟进的事。
不要复述事件，要提炼。每条要具体、可复用。
只输出 JSON 数组，每个元素：
{"type":"semantic|episodic","subject":"实体或主题","statement":"一句话结论","salience":0.0-1.0}
最多 8 条，salience 表示重要性。"""


def _recent_events(hours: int, limit: int = 200) -> list:
    since = int((time.time() - hours * 3600) * 1000)
    return db.query_events(since, limit=limit)


def _fallback_reflect(rows: list) -> list[dict]:
    """无 LLM 时：按 subject/source 频次给出确定性归纳。"""
    subjects = Counter()
    sources = Counter()
    for r in rows:
        sources[r["source"]] += 1
        if r["title"]:
            subjects[r["title"][:24]] += 1
    out: list[dict] = []
    for src, n in sources.most_common(3):
        if n >= 3:
            out.append({"type": "episodic", "subject": src,
                        "statement": f"近期来自 {src} 的条目较多（{n} 条），是当前活跃的信息来源。",
                        "salience": 0.5})
    return out


def reflect(hours: int = 24) -> dict:
    rows = _recent_events(hours)
    if not rows:
        return {"ok": True, "created": 0, "note": "近期没有事件可反思。"}

    digest = "\n".join(
        f"- [{r['source']}/{r['kind']}] {r['title'] or ''} {(r['content'] or '')[:120]}"
        for r in rows[:120]
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
        insights = _fallback_reflect(rows)

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
                    content=f"{'LLM' if used_llm else '规则'}反思 {len(rows)} 条事件 -> {created} 条待确认记忆",
                    meta={"used_llm": used_llm, "created": created})
    return {
        "ok": True,
        "created": created,
        "used_llm": used_llm,
        "events": len(rows),
        "note": f"已生成 {created} 条待确认记忆，确认前不会写入长期记忆。",
    }
