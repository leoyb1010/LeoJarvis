import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from leojarvis import db
from leojarvis.ingest.base import RawItem
from leojarvis.ingest.rss import x_monitor_feeds
from leojarvis.intelligence.scanner import github_radar
from leojarvis.judge.engine import judge_and_store
from leojarvis.localize import to_chinese
from leojarvis.main import app
from leojarvis import user_settings
from leojarvis.api.routes import _apply_remote_device_states


def test_health_endpoint():
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_event_judgment_briefing_feedback_cycle():
    db.init_db()
    event_id = None
    item = RawItem(
        source="test",
        domain="business",
        kind="market",
        title="NVDA AI 芯片需求继续增长",
        content="NVDA 与 AI Agent 基础设施相关，可能影响 Leo 关注的美股和 AI 主题。",
    )
    try:
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
            assert feedback.json()["memory_status"] == "pending"
            pending = client.get("/memories/pending")
            assert pending.status_code == 200
            assert any(row["id"] == feedback.json()["memory_candidate_id"] for row in pending.json())
    finally:
        if event_id:
            with db.conn() as c:
                c.execute("DELETE FROM feedback WHERE event_id=?", (event_id,))
                c.execute("DELETE FROM memories WHERE source_events LIKE ?", (f"%{event_id}%",))
                c.execute("DELETE FROM judgments WHERE event_id=?", (event_id,))
                c.execute("DELETE FROM events WHERE id=?", (event_id,))


def test_briefing_separates_email_from_news():
    db.init_db()
    email_id = None
    news_id = None
    try:
        email_id = db.insert_event(
            source="email:Apple Mail:INBOX",
            domain="life",
            kind="email",
            title="测试邮件不应进入新闻简报",
            content="From: test@example.com",
            dedup_key="pytest-email-separate",
        )
        news_id = db.insert_event(
            source="rss:pytest",
            domain="business",
            kind="news",
            title="测试 AI 新闻应进入新闻简报",
            content="AI Agent 和本地助理相关的重要新闻。",
            dedup_key="pytest-news-separate",
        )
        assert email_id and news_id
        db.insert_judgment(event_id=email_id, score=0.62, take="邮件摘要", triage="digest", reasons=["邮件观察"])
        db.insert_judgment(event_id=news_id, score=0.82, take="新闻摘要", triage="digest", reasons=["AI Agent"])
        with TestClient(app) as client:
            res = client.get("/briefing/today")
        assert res.status_code == 200
        payload = res.json()
        assert any(row["event_id"] == email_id for row in payload["mail"])
        assert all(row["event_id"] != email_id for row in payload["items"])
        assert any(row["event_id"] == news_id for row in payload["items"])
    finally:
        with db.conn() as c:
            for event_id in [email_id, news_id]:
                if event_id:
                    c.execute("DELETE FROM judgments WHERE event_id=?", (event_id,))
                    c.execute("DELETE FROM events WHERE id=?", (event_id,))


def test_github_radar_has_chinese_display_fields():
    db.init_db()
    repo = "pytest/local-agent-demo"
    with db.conn() as c:
        c.execute("DELETE FROM github_repo_snapshots WHERE repo_full_name=?", (repo,))
        created = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat().replace("+00:00", "Z")
        pushed = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        c.execute(
            """INSERT INTO github_repo_snapshots(
                 id, repo_full_name, query, stars, forks, open_issues, description, url,
                 language, topics, license, created_at, pushed_at, updated_at, observed_ts
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "pytest-github-radar-display",
                repo,
                "personal AI assistant",
                1200,
                160,
                12,
                "A local-first AI agent desktop app with persistent memory and workflow automation.",
                "https://github.com/pytest/local-agent-demo",
                "TypeScript",
                '["ai-agent","local-first","automation"]',
                "MIT",
                created,
                pushed,
                pushed,
                db.now_ms(),
            ),
        )
    try:
        rows = github_radar(limit=200)
        item = next(row for row in rows if row["repo_full_name"] == repo)
        assert item["summary_zh"]
        assert "英文来源摘要" not in item["summary_zh"]
        assert not item["summary_zh"].startswith("中文摘要")
        assert "英文来源摘要" not in " ".join(item["display_topics"])
        assert "AI 智能体" in item["display_topics"]
        assert item["why_zh"]
        assert item["relation_zh"]
        assert item["next_step_zh"]
    finally:
        with db.conn() as c:
            c.execute("DELETE FROM github_repo_snapshots WHERE repo_full_name=?", (repo,))


def test_x_monitor_defaults_include_ai_tech_sources():
    cfg = user_settings.load()["x_monitor"]
    assert "OpenAI" in cfg["users"]
    assert "AnthropicAI" in cfg["users"]
    assert "GoogleDeepMind" in cfg["users"]
    feeds = x_monitor_feeds()
    assert any(feed["name"] == "X · @OpenAI" for feed in feeds)


def test_remote_cortex_connection_overrides_stale_device_heartbeat():
    now = 1_780_000_000
    rows = [{
        "device_id": "rc-pytest",
        "device_name": "pytest remote",
        "host_name": "pytest.local",
        "model": "Mac",
        "role": "remote-leojarvis",
        "generated_at": now - 5000,
        "last_seen_ts": now - 5000,
        "health": 96,
        "status": "健康",
        "metrics": {},
        "modules": {},
        "services": {"online": 1, "total": 1},
        "risks": [],
    }]
    connections = [{"id": "rc-pytest", "name": "pytest remote", "host": "pytest.local", "enabled": True, "connected": True, "last_error": ""}]

    merged = _apply_remote_device_states(rows, connections, now=now)

    assert merged[0]["online"] is True
    assert merged[0]["age_seconds"] == 5000
    assert merged[0]["status"] == "健康"


def test_remote_cortex_disconnected_device_gets_explicit_risk():
    now = 1_780_000_000
    rows: list[dict] = []
    connections = [{"id": "rc-pytest", "name": "pytest remote", "host": "pytest.local", "enabled": True, "connected": False, "last_error": "Connection refused"}]

    merged = _apply_remote_device_states(rows, connections, now=now)

    assert len(merged) == 1
    assert merged[0]["online"] is False
    assert merged[0]["status"] == "离线"
    assert "Connection refused" in merged[0]["risks"][0]["advice"]


def test_localize_fallback_uses_display_safe_label():
    text = to_chinese("A new agentic workflow automation benchmark for AI coding agents", allow_llm=False)
    assert "英文来源摘要" not in text
    assert text


def test_cockpit_and_personal_notes_endpoints():
    db.init_db()
    note_id = None
    attachment_id = None
    attachment_path = None
    with TestClient(app) as client:
        try:
            note = client.post("/personal-notes", json={
                "title": "测试个人记事",
                "content": "这是一条带标签的个人记事，用于验证产品化记事接口。",
                "tags": ["测试", "个人记事"],
            })
            assert note.status_code == 200
            body = note.json()
            assert body["ok"] is True
            note_id = body["note"]["id"]
            assert body["note"]["title"] == "测试个人记事"

            listed = client.get("/personal-notes?q=产品化")
            assert listed.status_code == 200
            assert listed.json()["stats"]["total"] >= 1

            attachment = client.post("/personal-notes/import-attachment", json={
                "note_id": note_id,
                "file_name": "pytest-note.md",
                "mime_type": "text/markdown",
                "data_base64": base64.b64encode("这是一份测试附件。".encode("utf-8")).decode("ascii"),
            })
            assert attachment.status_code == 200
            attachment_body = attachment.json()
            assert attachment_body["ok"] is True
            attachment_id = attachment_body["attachment"]["id"]
            attachment_path = attachment_body["attachment"]["path"]

            detail = client.get(f"/personal-notes/{note_id}")
            assert detail.status_code == 200
            assert any(a["id"] == attachment_id for a in detail.json()["attachments"])

            system = client.get("/system/overview")
            assert system.status_code == 200
            system_payload = system.json()
            assert "modules" in system_payload
            assert "ai_tools" in system_payload

            tools = client.get("/system/ai-tools")
            assert tools.status_code == 200
            assert any(row["name"] == "Codex CLI" for row in tools.json())

            cockpit = client.get("/cockpit/overview")
            assert cockpit.status_code == 200
            payload = cockpit.json()
            assert "health" in payload
            assert "notes" in payload
            assert "memory" in payload
        finally:
            if note_id:
                client.delete(f"/personal-notes/{note_id}")
                with db.conn() as c:
                    if attachment_id:
                        c.execute("DELETE FROM personal_note_attachments WHERE id=?", (attachment_id,))
                    c.execute("DELETE FROM personal_note_revisions WHERE note_id=?", (note_id,))
                    c.execute("DELETE FROM personal_notes WHERE id=?", (note_id,))
                    c.execute("DELETE FROM events WHERE dedup_key=?", (f"note:{note_id}",))
                if attachment_path:
                    Path(attachment_path).unlink(missing_ok=True)


def test_intelligence_overview_and_configuration_endpoints():
    db.init_db()
    target_query = "pytest intelligence radar"
    source_url = "https://example.com/cortex-pytest-radar"
    with db.conn() as c:
        c.execute("DELETE FROM intelligence_targets WHERE query=?", (target_query,))
        c.execute("DELETE FROM intelligence_sources WHERE url=?", (source_url,))

    with TestClient(app) as client:
        overview = client.get("/intelligence/overview")
        assert overview.status_code == 200
        assert "github" in overview.json()

        target = client.post("/intelligence/targets", json={"query": target_query, "label": target_query})
        assert target.status_code == 200
        target_id = target.json()["id"]

        disabled = client.patch(f"/intelligence/targets/{target_id}", json={"enabled": False})
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] == 0

        source = client.post("/intelligence/sources", json={
            "type": "web",
            "name": "pytest radar",
            "url": source_url,
        })
        assert source.status_code == 200
        source_id = source.json()["id"]

        source_disabled = client.patch(f"/intelligence/sources/{source_id}", json={"enabled": False})
        assert source_disabled.status_code == 200
        assert source_disabled.json()["enabled"] == 0

    with db.conn() as c:
        c.execute("DELETE FROM intelligence_targets WHERE query=?", (target_query,))
        c.execute("DELETE FROM intelligence_sources WHERE url=?", (source_url,))


def test_device_ops_and_reach_status_endpoints(monkeypatch):
    from leojarvis import device_ops, reach

    monkeypatch.setattr(device_ops, "fleet_status", lambda: {
        "ok": True,
        "generated_at": 1,
        "safe_default": True,
        "summary": {"targets": 1, "ready": 1, "missing": 0},
        "targets": [{
            "target_id": "local",
            "name": "Local Mac",
            "kind": "local",
            "ready": True,
            "mo_installed": True,
            "safe_mode": True,
            "commands": ["clean", "optimize"],
        }],
    })
    monkeypatch.setattr(reach, "channel_status", lambda: {
        "ok": True,
        "generated_at": 1,
        "summary": {"ready": 2, "total": 2, "core_ready": 2, "core_total": 2},
        "channels": [
            {"id": "web", "name": "任意网页", "tier": 0, "optional": False, "status": "ok", "message": "ok"},
            {"id": "github", "name": "GitHub", "tier": 0, "optional": False, "status": "ok", "message": "ok"},
        ],
    })

    with TestClient(app) as client:
        ops = client.get("/api/device-ops/status")
        channels = client.get("/api/reach/status")

    assert ops.status_code == 200
    assert ops.json()["summary"]["ready"] == 1
    assert channels.status_code == 200
    assert channels.json()["summary"]["core_ready"] == 2


def test_reach_catalog_keeps_agent_reach_source_breadth():
    from leojarvis import reach

    ids = {channel.id for channel in reach.CHANNELS}
    expected = {
        "web", "github", "rss", "youtube", "bilibili", "exa_search",
        "twitter", "reddit", "xiaohongshu", "douyin", "linkedin",
        "wechat", "weibo", "v2ex", "xueqiu", "xiaoyuzhou",
    }

    assert expected.issubset(ids)
    assert len(reach.source_matrix()) >= 4
