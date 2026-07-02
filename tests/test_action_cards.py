"""V5 主动智能 · 行动卡编译器契约测试。

核心：把 actionable 待办确定性地熔成行动卡（reply/decision/anticipate），
reply 类附上判读阶段已备的草稿；排序按优先级；离线（无 LLM）也能出卡。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from leojarvis import db, action_compiler
from leojarvis.main import app


def _mk_email_event(title: str, *, actionable=True, action="reply", draft="", task_title="", summary="") -> str:
    """造一封 actionable 邮件事件 + triage 缓存，返回 event_id。"""
    db.init_db()
    eid = db.insert_event(source="email:Gmail", kind="email", content=f"{title} 正文",
                          title=title, dedup_key=f"test:{title}")
    db.upsert_email_triage(event_id=eid, summary=summary or "需要处理", tags=[],
                           actionable=actionable, action=action, object="", due="",
                           task_title=task_title or title, reply_draft=draft)
    return eid


def test_reply_action_becomes_reply_card_with_draft():
    db.init_db()
    eid = _mk_email_event("张昊问投放数据", action="reply",
                          draft="张昊你好，投放数据我整理如下……", task_title="回复张昊的投放数据问题")
    db.upsert_task(event_id=eid, title="回复张昊的投放数据问题", action="reply",
                   priority="P1", confidence=0.8, origin="email")
    out = action_compiler.compile_action_cards(limit=10)
    card = next((c for c in out["cards"] if c["event_id"] == eid), None)
    assert card is not None, "actionable 邮件未生成行动卡"
    assert card["type"] == "reply"
    assert card["has_draft"] is True
    assert "投放数据" in card["draft"]


def test_approve_action_becomes_decision_card():
    db.init_db()
    eid = db.insert_event(source="email:Gmail", kind="email", content="审批请求",
                          title="审批预算申请", dedup_key="test:approve1")
    db.upsert_email_triage(event_id=eid, summary="需你审批", tags=[], actionable=True,
                           action="approve", object="预算", due="", task_title="审批预算申请", reply_draft="")
    db.upsert_task(event_id=eid, title="审批预算申请", action="approve",
                   priority="P0", confidence=0.9, origin="email")
    out = action_compiler.compile_action_cards(limit=10)
    card = next((c for c in out["cards"] if c["event_id"] == eid), None)
    assert card and card["type"] == "decision"
    assert card["has_draft"] is False


def test_cards_sorted_by_priority():
    db.init_db()
    for title, pri, conf in [("低优", "P2", 0.5), ("最高优", "P0", 0.6), ("中优", "P1", 0.7)]:
        eid = db.insert_event(source="im", kind="im", content=title, title=title, dedup_key=f"test:{title}")
        db.upsert_task(event_id=eid, title=title, action="prepare", priority=pri,
                       confidence=conf, origin="im")
    out = action_compiler.compile_action_cards(limit=10)
    titles = [c["title"] for c in out["cards"] if c["title"] in ("低优", "中优", "最高优")]
    assert titles[0] == "最高优", f"P0 应排最前，实际 {titles}"


def test_render_cards_text_leads_with_things_to_do():
    cards = [
        {"type": "reply", "title": "回复张昊", "has_draft": True},
        {"type": "decision", "title": "审批预算", "has_draft": False},
        {"type": "anticipate", "title": "复盘会准备", "has_draft": False},
    ]
    txt = action_compiler.render_cards_text(cards)
    assert "3 件事" in txt
    assert "【回复】回复张昊" in txt and "我已起草" in txt
    assert "【决策】审批预算" in txt and "拍板" in txt
    assert "【预判】复盘会准备" in txt


def test_empty_cards_text_is_reassuring():
    assert "没有需要你亲自处理" in action_compiler.render_cards_text([])


def test_compile_is_offline_deterministic(monkeypatch):
    """不依赖 LLM：即使把 models_router.chat 打爆，行动卡仍能产出。"""
    from leojarvis import models_router
    monkeypatch.setattr(models_router, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no llm")))
    db.init_db()
    eid = db.insert_event(source="im", kind="im", content="x", title="离线也要出卡", dedup_key="test:offline")
    db.upsert_task(event_id=eid, title="离线也要出卡", action="prepare", priority="P1",
                   confidence=0.7, origin="im")
    out = action_compiler.compile_action_cards(limit=10)
    assert any(c["title"] == "离线也要出卡" for c in out["cards"])


def test_action_cards_api():
    db.init_db()
    eid = db.insert_event(source="im", kind="im", content="y", title="API 行动卡", dedup_key="test:apicard")
    db.upsert_task(event_id=eid, title="API 行动卡", action="reply", priority="P1",
                   confidence=0.8, origin="im")
    with TestClient(app) as client:
        res = client.get("/assistant/action-cards", params={"limit": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "cards" in body and "counts" in body
    assert set(body["counts"]) >= {"total", "by_type", "with_draft"}
