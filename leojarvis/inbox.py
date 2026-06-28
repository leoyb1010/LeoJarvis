"""信息转任务收件箱。

核心原则(纠错):**收件箱只装真正需要 Leo 行动的事**,不是信息流。
新闻/情报(kind=news/github_repo/x_post)无论 judge 多看重,都**不进**收件箱——它们只是
资讯,在情报流里看就行。只有**真·请求源**(kind=email/calendar:邮件里 @你/请求你的、
日历待办)才可能进,且还要再过一道 actionable 闸门(判定"这是不是真要你回复/处理/审批的事",
而非订阅邮件/系统通知)。

落进 tasks 表(db.upsert_task,按 event_id 去重、用户表态过的不覆盖)。
设计:确认队列(unconfirmed→confirm/ignore/done)、来源台账、低置信降级。
"""

from __future__ import annotations

import json

from . import db

# 只有这些 kind 的事件才可能进收件箱(真·请求源)。news/github_repo/x_post 永不进。
_ACTIONABLE_KINDS = ("email", "calendar")
# 低于这个置信度只作为「建议」(仍入库 unconfirmed,但前端标注为低置信建议)。
_SUGGEST_ONLY_BELOW = 0.45

_VALID_ACTIONS = {"reply", "review", "fill_form", "create", "follow_up", "approve", "update_crm", "prepare"}


def _latest_judged_events(hours: int, limit: int) -> list:
    """近 hours 小时内、**真·请求源(email/calendar)**的事件 + 其最新判定。
    新闻/情报(news/github/x_post)一律不取——收件箱不是信息流。"""
    db.init_db()
    since = db.now_ms() - hours * 3600 * 1000
    kph = ",".join("?" for _ in _ACTIONABLE_KINDS)
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
            WHERE e.kind IN ({kph})
            ORDER BY e.ts DESC LIMIT ?
            """,
            (since, *_ACTIONABLE_KINDS, limit),
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


def _rule_actionable(row) -> bool:
    """LLM 不可用时的兜底:从严。日历项算 actionable;邮件只在标题/正文出现明确请求/截止词时才算。
    宁可漏(不进收件箱),也不愿把 newsletter 误塞进来。"""
    if row["kind"] == "calendar":
        return True
    text = f"{row['title'] or ''} {(row['content'] or '')[:400]}".lower()
    # 明确"需要你做"的信号词(中英)。订阅/营销/通知类不命中。
    signals = ("请回复", "请处理", "请确认", "请审批", "请填写", "请提供", "麻烦你", "截止", "deadline",
               "due ", "please reply", "please confirm", "action required", "rsvp", "awaiting your",
               "需要你", "等你", "回复我", "回复邮件")
    return any(s in text for s in signals)


def rebuild(hours: int = 48, limit: int = 40) -> dict:
    """从近期**真·请求源(email/calendar)**事件重建/补充收件箱。
    邮件:复用 P1 Email 腔理结果(单一事实来源)——只对 actionable 的建任务。
    日历:规则判定(临近/有待办即建)。newsletter/通知/纯资讯跳过。"""
    rows = _latest_judged_events(hours, limit)
    if not rows:
        return {"ok": True, "scanned": 0, "created": 0, "skipped": 0,
                "note": "近期没有需要处理的邮件/日历项。"}

    # P1: 先确保邮件都腔理过(populate 缓存),邮件的 actionable/动作以腔理结果为准。
    used_llm = False
    try:
        from . import email_triage
        tr = email_triage.triage(hours=max(hours, 1), limit=limit)
        used_llm = bool(tr.get("used_llm"))
    except Exception:
        pass

    created = 0
    skipped = 0
    # 标题级去重:重复的通知邮件(如反复的 CI 失败告警)会被抽成同名待办,只留一条。
    seen_titles = {
        str(t["title"]).strip()
        for t in db.list_tasks(states=["unconfirmed", "confirmed"], limit=500)
    }
    for r in rows:
        a = _analysis(r)
        score = float(r["score"] or 0.3)
        triage = str(r["triage"] or "digest")
        priority, risk = _priority_risk(score, triage)

        if r["kind"] == "email":
            # 邮件:以腔理结果为权威。
            tg = db.get_email_triage(r["event_id"])
            if tg is None or not tg["actionable"]:
                skipped += 1
                continue
            action = tg["action"] if tg["action"] in _VALID_ACTIONS else "reply"
            title = (tg["task_title"] or a.get("title_zh") or r["title"] or "待处理邮件").strip()[:200]
            obj = (tg["object"] or "").strip() or None
            due = (tg["due"] or "").strip() or None
            suggestion = (tg["summary"] or a.get("next_step") or r["take"] or "").strip()[:300]
        else:
            # 日历:规则(临近/明确待办)。
            if not _rule_actionable(r):
                skipped += 1
                continue
            action = "prepare"
            title = (a.get("title_zh") or r["title"] or "日程待办").strip()[:200]
            obj = None
            due = None
            suggestion = (a.get("summary") or r["take"] or (r["content"] or "")[:200] or "").strip()[:300]

        if title in seen_titles:   # 同名(重复通知)→ 跳过
            skipped += 1
            continue
        seen_titles.add(title)
        try:
            reasons = json.loads(r["reasons"]) if r["reasons"] else []
        except Exception:
            reasons = []
        tid = db.upsert_task(
            event_id=r["event_id"], title=title, action=action, object=obj, due=due,
            owner="我", priority=priority, confidence=round(score, 3), risk_level=risk,
            origin=_origin_of(r["source"], r["kind"]), context_preview=suggestion,
            suggestion=suggestion, tags=[str(x) for x in reasons][:4],
        )
        if tid:
            created += 1
            # P3：新建一条 actionable 邮件待办 → 触发事件,事件型定时任务可据此自动响应。
            if r["kind"] == "email":
                try:
                    from . import event_bus
                    event_bus.fire_event("email_actionable")
                except Exception:
                    pass
    return {"ok": True, "scanned": len(rows), "created": created, "skipped": skipped, "used_llm": used_llm,
            "note": f"扫描 {len(rows)} 封邮件/日历项,{created} 条需处理入收件箱,{skipped} 条(订阅/通知/资讯)跳过。"}


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
