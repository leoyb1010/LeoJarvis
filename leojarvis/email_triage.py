"""Email 腔理(P1)。清室重写,设计借鉴 odysseus 的 email 摘要/标签/分类管道,
但用 LeoJarvis 自己的 db / models_router / 事件模型,代码全新、无 AGPL 牵连。

对每封邮件(events.kind='email')做一次 LLM:
  - summary   一句话摘要
  - tags      标签(紧急/财务/订阅/通知/工作/个人…)
  - actionable 是否真需要 Leo 亲自处理(回复/审批/填表/跟进),还是订阅/营销/通知
  - 若 actionable:action / object / due / task_title(给收件箱用)
  - reply_draft 可选回复草稿(只生成,绝不自动发——发信走行动闸门)

结果缓存在 db.email_triage(按 event_id),避免重复判读。inbox.rebuild 直接复用本结果,
不再自己抽取(单一事实来源、省一次 LLM)。

注:LeoJarvis 已有 email 事件源(ingest/email_ingest.py 收 Gmail/Apple Mail → events kind=email)。
本模块只做"理解",不碰 IMAP 收信本身;实时收信/回信的 IMAP/SMTP 配置位见 settings.toml [email]。
"""

from __future__ import annotations

import json

from . import db

_TAGS = ["紧急", "财务", "工作", "个人", "订阅", "通知", "营销", "社交", "安全", "日程"]
_VALID_ACTIONS = {"reply", "review", "fill_form", "create", "follow_up", "approve", "prepare"}

_TRIAGE_SYSTEM = """你是 Leo 的私人邮件助理。对下面每封邮件做腔理判断。
只输出 JSON 数组,每元素带 idx(与输入编号一致)和:
{
 "idx":int,
 "summary":"一句话摘要(中文,客观)",
 "tags":["从这些里选 0-3 个: 紧急/财务/工作/个人/订阅/通知/营销/社交/安全/日程"],
 "actionable":true/false,
 "action":"reply|review|fill_form|create|follow_up|approve|prepare",
 "object":"动作对象(简短)",
 "due":"YYYY-MM-DD 或 空串",
 "title":"若 actionable:一句话待办(动词开头,具体)",
 "reply_draft":"若是需要回复的邮件:一段得体的中文回复草稿,否则空串"
}
硬规则:
- actionable=true 仅当确需 Leo 亲自处理(有人请求/截止/审批/需回复)。订阅/营销/自动通知/纯资讯=false。
- summary 始终给;tags 据实选;reply_draft 只在确需回复时给。
- 返回与输入等长、idx 一一对应。"""


def _recent_email_events(hours: int, limit: int) -> list:
    db.init_db()
    since = db.now_ms() - hours * 3600 * 1000
    with db.conn() as c:
        return c.execute(
            "SELECT id, title, content, meta, source, ts FROM events "
            "WHERE kind='email' AND ts>=? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        ).fetchall()


def _sender_of(row) -> str:
    try:
        m = json.loads(row["meta"]) if row["meta"] else {}
    except Exception:
        m = {}
    return str(m.get("from") or m.get("sender") or m.get("from_addr") or "")


def _block(i: int, row) -> str:
    sender = _sender_of(row)
    # 邮件正文是不可信外部内容(注入靶子)→ 护栏包裹(C1)。
    from .prompt_security import wrap_untrusted
    body = wrap_untrusted((row["content"] or "")[:600], source=f"email:{sender}")
    return f"### {i}\n发件人: {sender}\n主题: {row['title'] or ''}\n正文:\n{body}"


def _llm_triage(rows: list) -> dict[int, dict]:
    """批量腔理。失败/不可用返回 {}（调用方对未腔理的走规则兜底）。"""
    if not rows:
        return {}
    try:
        from .models_router import chat
        raw = chat("agent", [
            {"role": "system", "content": _TRIAGE_SYSTEM},
            {"role": "user", "content": "\n\n".join(_block(i, r) for i, r in enumerate(rows))},
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


def _rule_triage(row) -> dict:
    """LLM 不可用兜底:从严判 actionable(有明确请求/截止词才 true),summary 用正文首句。"""
    text = f"{row['title'] or ''} {(row['content'] or '')[:400]}".lower()
    signals = ("请回复", "请处理", "请确认", "请审批", "请填写", "请提供", "麻烦你", "截止", "deadline",
               "due ", "please reply", "please confirm", "action required", "rsvp", "需要你", "等你回")
    actionable = any(s in text for s in signals)
    summary = (row["content"] or "").strip().split("\n")[0][:120] or (row["title"] or "")
    return {"summary": summary, "tags": [], "actionable": actionable,
            "action": "reply" if actionable else "", "title": (row["title"] or "")[:200] if actionable else ""}


def triage(hours: int = 720, limit: int = 60, refresh: bool = False) -> dict:
    """腔理近 hours 小时的邮件,结果写入缓存。refresh=True 重判已缓存的。返回统计。"""
    rows = _recent_email_events(hours, limit)
    if not rows:
        return {"ok": True, "scanned": 0, "triaged": 0, "actionable": 0, "note": "近期没有邮件。"}
    # 只对未缓存(或 refresh)的跑 LLM,省成本。
    todo = [r for r in rows if refresh or db.get_email_triage(r["id"]) is None]
    extracted = _llm_triage(todo) if todo else {}
    used_llm = bool(extracted)
    triaged = 0
    for i, r in enumerate(todo):
        d = extracted.get(i) or _rule_triage(r)
        tags = [t for t in (d.get("tags") or []) if t in _TAGS][:3]
        actionable = bool(d.get("actionable", False))
        action = d.get("action") if d.get("action") in _VALID_ACTIONS else ("reply" if actionable else None)
        db.upsert_email_triage(
            event_id=r["id"], summary=(d.get("summary") or "").strip()[:400], tags=tags,
            actionable=actionable, action=action, object=(d.get("object") or "").strip() or None,
            due=(d.get("due") or "").strip() or None,
            task_title=(d.get("title") or "").strip()[:200] or None,
            reply_draft=(d.get("reply_draft") or "").strip()[:1200] or None,
            model_used="llm" if extracted.get(i) else "rule",
        )
        triaged += 1
    actionable_n = sum(1 for r in rows if (db.get_email_triage(r["id"]) or {}) and
                       db.get_email_triage(r["id"])["actionable"])
    return {"ok": True, "scanned": len(rows), "triaged": triaged, "used_llm": used_llm,
            "actionable": actionable_n,
            "note": f"腔理 {triaged} 封新邮件(共扫描 {len(rows)}),其中 {actionable_n} 封需处理。"}


def triage_dict(event_id: str) -> dict | None:
    """取某封邮件的腔理结果(给收件箱/前端用)。"""
    r = db.get_email_triage(event_id)
    if not r:
        return None
    d = dict(r)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except Exception:
        d["tags"] = []
    d["actionable"] = bool(d.get("actionable"))
    return d
