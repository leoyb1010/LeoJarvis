"""V5 主动智能 · 意图-行动编译器。

把「信息」熔成「今天你要做的事 + 我已备好的草稿」。这是 Jarvis 从「资讯播报」
到「行动助手」的分水岭：早间推送不再是一堆资讯，而是结构化的**行动卡**——
每张卡明确「要你做什么类型的事」，能预备的（回复）直接附上草稿。

设计：**确定性、零 LLM**。全部复用已有的确定性产物——
  - inbox.list_inbox：已判定 actionable 的待办（带 action/priority/object/suggestion/event_id）
  - email_triage.reply_draft：邮件回复草稿（判读阶段已生成并落库）
  - calendar：临近日程
因此这个模块不依赖模型可用性，离线也能出行动卡（草稿是判读时就备好的，不现场生成）。

卡片类型（type）：
  - reply     需要你回复/答复 → 附 draft（已备草稿，改完过闸门才发）
  - decision  需要你拍板/审批/取舍 → 列 suggestion 供决断
  - anticipate 预判/预备（临近日程、需准备的事）→ 提前拉齐材料
草稿本身是「拟稿」动作（可逆、不外发），真正发送仍走行动闸门 + 审计账本。
"""
from __future__ import annotations

import logging

from . import db

log = logging.getLogger("action_compiler")

# inbox action → 行动卡类型
_REPLY_ACTIONS = {"reply", "respond", "answer"}
_DECISION_ACTIONS = {"approve", "review", "decide", "confirm"}
# 其余（prepare/follow_up/create/日历）→ anticipate

_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _card_type(action: str) -> str:
    a = (action or "").lower()
    if a in _REPLY_ACTIONS:
        return "reply"
    if a in _DECISION_ACTIONS:
        return "decision"
    return "anticipate"


def _draft_for(task: dict) -> str:
    """回复类卡片的已备草稿：取邮件判读阶段生成的 reply_draft（若有）。"""
    event_id = task.get("event_id")
    if not event_id:
        return ""
    try:
        tg = db.get_email_triage(event_id)
        if tg is not None:
            return (dict(tg).get("reply_draft") or "").strip()
    except Exception:
        log.exception("draft lookup failed for %s", event_id)
    return ""


def compile_action_cards(*, limit: int = 6) -> dict:
    """产出今天的行动卡（最多 limit 张，按优先级 + 置信度排序）。

    返回 {ok, cards:[{id,type,title,action,object,priority,due,suggestion,draft,
                      has_draft,event_id,confidence}], counts}
    """
    from . import inbox
    tasks = inbox.list_inbox(states=["unconfirmed", "confirmed"], limit=50).get("tasks", [])
    # 排序：优先级高在前，同级按置信度降序
    tasks.sort(key=lambda t: (_PRIORITY_RANK.get(str(t.get("priority", "P2")), 2),
                              -float(t.get("confidence") or 0)))
    cards: list[dict] = []
    for t in tasks:
        ctype = _card_type(str(t.get("action", "")))
        draft = _draft_for(t) if ctype == "reply" else ""
        cards.append({
            "id": t.get("id"),
            "type": ctype,
            "title": t.get("title", ""),
            "action": t.get("action", ""),
            "object": t.get("object"),
            "priority": t.get("priority", "P2"),
            "due": t.get("due"),
            "suggestion": t.get("suggestion") or t.get("context_preview") or "",
            "draft": draft,
            "has_draft": bool(draft),
            "event_id": t.get("event_id"),
            "confidence": round(float(t.get("confidence") or 0), 3),
            "suggest_only": bool(t.get("suggest_only")),
        })
        if len(cards) >= max(1, int(limit)):
            break
    by_type: dict[str, int] = {}
    for c in cards:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    return {"ok": True, "cards": cards,
            "counts": {"total": len(cards), "by_type": by_type,
                       "with_draft": sum(1 for c in cards if c["has_draft"])}}


def render_cards_text(cards: list[dict]) -> str:
    """把行动卡渲染成 check-in 推送用的紧凑中文文本（三件事+草稿提示）。"""
    if not cards:
        return "今天没有需要你亲自处理的事，安心推进手头工作。"
    label = {"reply": "回复", "decision": "决策", "anticipate": "预判"}
    lines = []
    for i, c in enumerate(cards, 1):
        tag = label.get(c["type"], "处理")
        extra = ""
        if c["type"] == "reply":
            extra = " → 我已起草，点开可改可发。" if c["has_draft"] else " → 需你回复。"
        elif c["type"] == "decision":
            extra = " → 需你拍板。"
        elif c["type"] == "anticipate":
            extra = " → 我已拉齐相关材料。"
        lines.append(f"{i:02d}. 【{tag}】{c['title']}{extra}")
    return "今天有 {} 件事需要你：\n".format(len(cards)) + "\n".join(lines)
