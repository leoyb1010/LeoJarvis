"""信息转任务收件箱（WorkDock 合并 M2）。

把已经被 judge 评过的事件（邮件/情报/agent 动作等）自动抽成**结构化待办**:
带来源(event_id)、置信度(judge score)、处理建议(analysis.next_step)。低置信只建议、不自动建。

judge 现产的是 analysis(title_zh/summary/take/why/relation/next_step)+score+triage+reasons,
没有结构化的 action/object/due/owner。这里用一次 LLM 批量抽取补齐(失败规则兜底),
落进 tasks 表(db.upsert_task,按 event_id 去重、用户表态过的不覆盖)。

设计同 LeoJarvis 既有理念:确认队列(unconfirmed→用户 confirm/ignore/done)、来源台账、低置信降级。
"""

from __future__ import annotations

import json

from . import db

# 只有这些 triage 才进收件箱(notify=需实时, digest=进简报即可)；ignore 不进。
_ACTIONABLE_TRIAGE = ("notify", "digest")
# 低于这个置信度只作为「建议」(仍入库 unconfirmed,但前端标注为低置信建议)。
_SUGGEST_ONLY_BELOW = 0.45

_VALID_ACTIONS = {"reply", "review", "fill_form", "create", "follow_up", "approve", "update_crm", "prepare"}

_EXTRACT_SYSTEM = """你是 Leo 的私人助理。下面是若干条已判定值得处理的信息。请把每条抽成一个结构化待办。
只输出 JSON 数组,每元素带 idx(与输入编号一致)和:
{"idx":int,"action":"reply|review|fill_form|create|follow_up|approve|prepare","object":"动作对象(简短)","due":"YYYY-MM-DD 或 空串(原文没提期限就空)","title":"一句话待办(动词开头,具体)"}
硬规则:title 必须是可执行的动作,不是复述信息;due 只在原文明确提到期限时填,否则空。返回与输入等长、idx 一一对应。"""


def _latest_judged_events(hours: int, limit: int) -> list:
    """近 hours 小时内、triage 为 notify/digest 的事件 + 其最新判定(复用 builder 的 join 思路)。"""
    db.init_db()
    since = db.now_ms() - hours * 3600 * 1000
    ph = ",".join("?" for _ in _ACTIONABLE_TRIAGE)
    with db.conn() as c:
        return c.execute(
            f"""
            WITH lj AS (
              SELECT event_id, MAX(ts) AS ts FROM judgments WHERE ts>=? GROUP BY event_id
            )
            SELECT e.id AS event_id, e.title, e.content, e.url, e.source, e.kind, e.meta,
                   j.score, j.take, j.triage, j.reasons, j.analysis
            FROM lj JOIN judgments j ON j.event_id=lj.event_id AND j.ts=lj.ts
            JOIN events e ON e.id=j.event_id
            WHERE j.triage IN ({ph})
            ORDER BY e.ts DESC LIMIT ?
            """,
            (since, *_ACTIONABLE_TRIAGE, limit),
        ).fetchall()


def _origin_of(source: str, kind: str) -> str:
    s = (source or "").lower()
    if s.startswith("email") or "mail" in s:
        return "email"
    if "intel" in s or "rss" in s:
        return "intel"
    if s.startswith("agent") or kind == "action":
        return "agent"
    if "calendar" in s or "ics" in s:
        return "calendar"
    return "manual"


def _priority_risk(score: float, triage: str) -> tuple[str, str]:
    """triage+score → 优先级/风险(judge 没产结构化风险,用 triage 近似)。"""
    if triage == "notify" and score >= 0.75:
        return "P0", "medium"
    if triage == "notify":
        return "P1", "medium"
    if score >= 0.6:
        return "P1", "low"
    return "P2", "low"


def _analysis(row) -> dict:
    raw = row["analysis"] if "analysis" in row.keys() else None
    if not raw:
        return {}
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


def _llm_extract(rows: list) -> dict[int, dict]:
    """批量抽 action/object/due/title。失败/不可用返回 {}（调用方走规则兜底）。"""
    if not rows:
        return {}
    blocks = []
    for i, r in enumerate(rows):
        a = _analysis(r)
        title = a.get("title_zh") or r["title"] or ""
        summ = a.get("summary") or (r["content"] or "")[:200]
        blocks.append(f"### {i}\n标题: {title}\n摘要: {summ}\n建议: {a.get('next_step','')}")
    try:
        from .models_router import chat
        raw = chat("agent", [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": "\n\n".join(blocks)},
        ], temperature=0.2)
        s, e = raw.find("["), raw.rfind("]")
        arr = json.loads(raw[s:e + 1]) if s >= 0 else []
        out: dict[int, dict] = {}
        for j, entry in enumerate(arr if isinstance(arr, list) else []):
            if not isinstance(entry, dict):
                continue
            idx = entry.get("idx")
            if not isinstance(idx, int) or idx < 0 or idx >= len(rows):
                idx = j
            out[idx] = entry
        return out
    except Exception:
        return {}


def rebuild(hours: int = 48, limit: int = 40) -> dict:
    """从近期已判定事件重建/补充收件箱。返回统计。"""
    rows = _latest_judged_events(hours, limit)
    if not rows:
        return {"ok": True, "scanned": 0, "created": 0, "note": "近期没有可转任务的事件。"}
    extracted = _llm_extract(rows)
    used_llm = bool(extracted)
    created = 0
    for i, r in enumerate(rows):
        a = _analysis(r)
        score = float(r["score"] or 0.3)
        triage = str(r["triage"] or "digest")
        priority, risk = _priority_risk(score, triage)
        ext = extracted.get(i, {})
        action = ext.get("action") if ext.get("action") in _VALID_ACTIONS else "review"
        title = (ext.get("title") or a.get("title_zh") or r["title"] or "待处理事项").strip()[:200]
        due = (ext.get("due") or "").strip() or None
        obj = (ext.get("object") or "").strip() or None
        preview = (a.get("summary") or r["take"] or (r["content"] or "")[:200] or "").strip()[:500]
        suggestion = (a.get("next_step") or a.get("take") or r["take"] or "").strip()[:300]
        try:
            reasons = json.loads(r["reasons"]) if r["reasons"] else []
        except Exception:
            reasons = []
        tid = db.upsert_task(
            event_id=r["event_id"], title=title, action=action, object=obj, due=due,
            owner="我", priority=priority, confidence=round(score, 3), risk_level=risk,
            origin=_origin_of(r["source"], r["kind"]), context_preview=preview,
            suggestion=suggestion, tags=[str(x) for x in reasons][:4],
        )
        if tid:
            created += 1
    return {"ok": True, "scanned": len(rows), "created": created, "used_llm": used_llm,
            "note": f"从 {len(rows)} 条已判定事件生成/更新 {created} 条待办（低置信仅作建议）。"}


def _row_to_dict(r) -> dict:
    d = dict(r)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except Exception:
        d["tags"] = []
    d["suggest_only"] = float(d.get("confidence") or 0) < _SUGGEST_ONLY_BELOW
    return d


def list_inbox(states: list[str] | None = None, limit: int = 100) -> dict:
    rows = db.list_tasks(states or ["unconfirmed", "confirmed"], limit=limit)
    return {"ok": True, "tasks": [_row_to_dict(r) for r in rows], "counts": db.task_state_counts()}


def set_state(task_id: str, state: str) -> dict:
    ok = db.set_task_state(task_id, state)
    return {"ok": ok, "task_id": task_id, "state": state}
