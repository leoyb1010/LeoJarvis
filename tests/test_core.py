from fastapi.testclient import TestClient

from cortex import db
from cortex.ingest.base import RawItem
from cortex.judge.engine import judge_and_store
from cortex.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_event_judgment_briefing_feedback_cycle():
    db.init_db()
    item = RawItem(
        source="test",
        domain="business",
        kind="market",
        title="NVDA AI 芯片需求继续增长",
        content="NVDA 与 AI Agent 基础设施相关，可能影响 Leo 关注的美股和 AI 主题。",
    )
    event_id = db.insert_event(source=item.source, domain=item.domain, kind=item.kind,
                               title=item.title, content=item.content, dedup_key="test-nvda-ai")
    if event_id is None:
        rows = db.query_events(0, limit=1000)
        event_id = next(r["id"] for r in rows if r["dedup_key"] == "test-nvda-ai")
    judgment = judge_and_store(event_id, item)
    assert judgment.triage in {"notify", "digest", "ignore"}
    with TestClient(app) as client:
        briefing = client.get("/briefing/today")
        assert briefing.status_code == 200
        feedback = client.post("/feedback", json={"event_id": event_id, "signal": "important"})
        assert feedback.status_code == 200
        assert feedback.json()["ok"] is True
