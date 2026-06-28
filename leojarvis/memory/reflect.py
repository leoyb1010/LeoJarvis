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
        # 事件反思产物多为「习惯/偏好」→ 默认归 fact 层（pattern 由 reflect_personal_data 专门提炼）。
        db.insert_memory(
            stmt, memory_type=it.get("type", "semantic"),
            subject=it.get("subject"),
            confidence=0.75, salience=float(it.get("salience", 0.5)),
            layer="fact", origin="reflect",
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


_DISTILL_SYSTEM = """你是 Leo 的私人记忆官。下面是 Leo 投喂的个人数据（工作内容、聊天、行为记录等）的情景片段。
请从这些零散片段里提炼出**关于 Leo 本人**、值得长期记住的高阶结论，分三类：
  fact    —— 稳定事实（在做什么项目、长期偏好、关注的人/持仓/主题）
  pattern —— 反复出现的行为规律（如「常深夜写代码」「决策前要看数据对比」「反感周末打扰」）
  entity  —— 重要的人/项目及其与 Leo 的关系
硬规则：只提炼能跨场景复用的结论，不要复述单条片段；pattern 必须是多次出现的规律，不是一次性事件。
只输出 JSON 数组，每个元素：{"layer":"fact|pattern|entity","subject":"实体/主题","statement":"一句话结论","salience":0.0-1.0}
最多 10 条。"""


def reflect_personal_data(limit: int = 200) -> dict:
    """超级 Jarvis P3：把累积的 episode 记忆（来自个人数据投喂）提炼成 fact/pattern/entity。

    产物全部进 pending 队列，需用户确认后才转正——和事件反思一致，不偷偷沉淀。
    """
    db.init_db()
    episodes = db.list_memories_by_layer(["episode"], limit=limit, status="active")
    if not episodes:
        return {"ok": True, "created": 0, "note": "暂无可提炼的情景记忆（先投喂个人数据）。"}

    digest = "\n".join(f"- {str(r['statement'])[:160]}" for r in episodes[:160])
    insights: list[dict] = []
    used_llm = False
    try:
        from ..models_router import chat
        raw = chat("reflect", [
            {"role": "system", "content": _DISTILL_SYSTEM},
            {"role": "user", "content": f"## Leo 画像\n{profile_text()}\n\n## 情景片段\n{digest}"},
        ], temperature=0.3)
        start, end = raw.find("["), raw.rfind("]")
        insights = json.loads(raw[start:end + 1]) if start >= 0 else []
        used_llm = True
    except Exception:
        insights = []

    if not insights:
        # 无 LLM 兜底：按 subject 频次粗提 pattern。
        subjects = Counter(str(r["subject"] or "").strip() for r in episodes if r["subject"])
        for subj, n in subjects.most_common(6):
            if subj and n >= 3:
                insights.append({"layer": "pattern", "subject": subj,
                                 "statement": f"Leo 的个人数据里『{subj}』反复出现（{n} 次），可能是稳定的行为/关注规律。",
                                 "salience": min(0.85, 0.5 + n * 0.05)})

    valid = {"fact", "pattern", "entity"}
    created = 0
    for it in insights:
        stmt = str(it.get("statement", "")).strip()
        if not stmt:
            continue
        layer = str(it.get("layer", "fact"))
        if layer not in valid:
            layer = "fact"
        db.insert_memory(
            stmt, memory_type=f"distilled:{layer}", subject=it.get("subject"),
            confidence=0.7, salience=float(it.get("salience", 0.5)),
            layer=layer, origin="reflect_personal_data",
        )
        created += 1

    db.insert_event(source="reflection", kind="insight", domain="business",
                    title=f"个人数据提炼：{created} 条待确认记忆",
                    content=f"{'LLM' if used_llm else '规则'}从 {len(episodes)} 条情景记忆提炼出 {created} 条 fact/pattern/entity",
                    meta={"used_llm": used_llm, "created": created, "episodes": len(episodes)})
    return {"ok": True, "created": created, "used_llm": used_llm,
            "episodes": len(episodes),
            "note": f"已从 {len(episodes)} 条情景记忆提炼出 {created} 条待确认的 fact/pattern/entity。"}


# ---------- B 自动记忆:每轮抽 ≤2 条用户陈述事实(进待确认队列,不自动 active) ----------

_TURN_FACT_SYSTEM = """从下面这轮对话里抽取**用户主动陈述的、长期有用的个人事实/偏好**(不是任务内容、不是你的话)。
最多 2 条;没有就返回 []。只输出 JSON 数组:[{"layer":"fact|pattern|entity","subject":"主语","statement":"一句话事实","salience":0.5}]
例:用户说"我用 Cursor 写代码"→ [{"layer":"pattern","subject":"Leo","statement":"用 Cursor 写代码","salience":0.6}]。
营销/闲聊/一次性内容不要抽。"""


def extract_turn_facts(messages: list[dict], reply: str) -> int:
    """每轮跑完抽 ≤2 条用户事实 → status=pending(进现有 /memories/pending 确认队列,守"不自动记"不变量)。
    返回新增条数。LLM 不可用则用极简规则(只认"我叫/我是/我用/我喜欢")。"""
    user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    if not user.strip():
        return 0
    facts: list[dict] = []
    try:
        from ..models_router import chat
        raw = chat("agent", [
            {"role": "system", "content": _TURN_FACT_SYSTEM},
            {"role": "user", "content": f"用户:{user[:500]}\n助理:{reply[:300]}"},
        ], temperature=0.2)
        s, e = raw.find("["), raw.rfind("]")
        arr = json.loads(raw[s:e + 1]) if s >= 0 else []
        facts = [x for x in arr if isinstance(x, dict) and x.get("statement")][:2]
    except Exception:
        # 兜底:极简规则,只在明确自述时抽一条。
        import re as _re
        m = _re.search(r"我(叫|是|用|喜欢|讨厌|习惯)([^,。;\n]{1,30})", user)
        if m:
            facts = [{"layer": "fact", "subject": "Leo", "statement": ("我" + m.group(1) + m.group(2)).strip(), "salience": 0.5}]
    created = 0
    for f in facts:
        stmt = str(f.get("statement") or "").strip()[:300]
        if not stmt:
            continue
        layer = f.get("layer") if f.get("layer") in {"fact", "pattern", "entity"} else "fact"
        mid = db.insert_memory(stmt, memory_type="semantic", subject=f.get("subject"),
                               confidence=0.7, salience=float(f.get("salience", 0.5)),
                               layer=layer, origin="auto_turn", status="pending")
        # 向量化(可降级),便于以后召回。
        try:
            from .store import remember
            remember(stmt, ref_id=mid, layer=layer)
        except Exception:
            pass
        created += 1
    return created


_CURATE_SYSTEM = """下面是若干条记忆,有些是近义重复。请把**确属同一事实的重复**分组合并。
只输出 JSON:{"groups":[["id1","id2"]]}(每组是该合并的 id 列表,保留第一个、归档其余)。没有重复就 {"groups":[]}。"""


def curate_duplicates(limit: int = 100) -> dict:
    """夜间整理:把近义重复的 fact/pattern 记忆合并(归档重复、强化留存)。LLM 不可用则按规范化文本去重。"""
    db.init_db()
    with db.conn() as c:
        rows = c.execute("SELECT id, statement FROM memories WHERE status='active' AND type='semantic' "
                         "AND layer IN ('fact','pattern') ORDER BY updated_ts DESC LIMIT ?", (limit,)).fetchall()
    if len(rows) < 2:
        return {"ok": True, "merged": 0}
    groups: list[list[str]] = []
    try:
        from ..models_router import chat
        raw = chat("agent", [
            {"role": "system", "content": _CURATE_SYSTEM},
            {"role": "user", "content": json.dumps([{"id": r["id"], "statement": r["statement"]} for r in rows], ensure_ascii=False)[:4000]},
        ], temperature=0.1)
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        groups = [g for g in obj.get("groups", []) if isinstance(g, list) and len(g) >= 2]
    except Exception:
        # 兜底:规范化文本完全相同才算重复。
        seen: dict[str, list[str]] = {}
        for r in rows:
            key = "".join(str(r["statement"] or "").lower().split())
            seen.setdefault(key, []).append(r["id"])
        groups = [ids for ids in seen.values() if len(ids) >= 2]
    merged = 0
    for g in groups:
        keep, dupes = g[0], g[1:]
        for did in dupes:
            if db.update_memory_status(did, "archived") if hasattr(db, "update_memory_status") else None:
                pass
            try:
                with db.conn() as c:
                    c.execute("UPDATE memories SET status='archived', updated_ts=? WHERE id=?", (db.now_ms(), did))
            except Exception:
                pass
            merged += 1
        try:
            db.adjust_memory(keep, salience_delta=0.1)
        except Exception:
            pass
    return {"ok": True, "merged": merged, "groups": len(groups)}
