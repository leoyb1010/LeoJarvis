import base64
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from leojarvis import db
from leojarvis.ingest.base import RawItem
from leojarvis.ingest.rss import x_monitor_feeds
from leojarvis.intelligence.scanner import github_radar, seed_defaults
from leojarvis.judge.engine import judge_and_store
from leojarvis.localize import has_noisy_english, to_chinese
from leojarvis.main import app
from leojarvis import user_settings
from leojarvis.briefing.builder import _is_homepage_scope_item


def _minimal_wav_base64() -> str:
    header = (
        b"RIFF" + (36).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data" + (0).to_bytes(4, "little")
    )
    return base64.b64encode(header).decode()


def test_health_endpoint():
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_speech_status_contract():
    with TestClient(app) as client:
        res = client.get("/api/speech/status")
    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    assert payload["default_model"] == "base"
    assert payload["allowed_models"] == ["tiny", "base", "small"]
    assert set(payload["models"]) == {"tiny", "base", "small"}


def test_speech_transcribe_uses_whisper_cpp_contract(monkeypatch, tmp_path):
    from leojarvis import speech

    binary = tmp_path / "whisper-cli"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "ggml-base.bin").write_bytes(b"model")

    def fake_run(cmd, capture_output, text, timeout):
        out_prefix = Path(cmd[cmd.index("-of") + 1])
        out_prefix.with_suffix(".txt").write_text("[00:00:00.000 --> 00:00:01.000] hello Jarvis\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(speech, "_binary", lambda: binary)
    monkeypatch.setattr(speech, "_model_dir", lambda: model_dir)
    monkeypatch.setattr(subprocess, "run", fake_run)

    payload = speech.transcribe_base64(
        data_base64=f"data:audio/wav;base64,{_minimal_wav_base64()}",
        mime_type="audio/wav",
        file_name="voice.wav",
        model="large",
        language="auto",
        prompt="personal notes",
        timeout=5,
    )

    assert payload["ok"] is True
    assert payload["model"] == "base"
    assert payload["text"] == "hello Jarvis"


def test_speech_transcribe_rejects_non_wav(monkeypatch, tmp_path):
    from leojarvis import speech

    binary = tmp_path / "whisper-cli"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "ggml-base.bin").write_bytes(b"model")
    monkeypatch.setattr(speech, "_binary", lambda: binary)
    monkeypatch.setattr(speech, "_model_dir", lambda: model_dir)

    with pytest.raises(ValueError, match="Only WAV audio"):
        speech.transcribe_base64(
            data_base64=base64.b64encode(b"not wav").decode(),
            mime_type="audio/webm",
            file_name="voice.webm",
        )


def test_api_token_guard_when_enabled(monkeypatch):
    monkeypatch.setenv("LEOJARVIS_API_TOKEN", "pytest-secret")
    with TestClient(app) as client:
        blocked = client.get("/api/health")
        allowed = client.get("/api/health", headers={"Authorization": "Bearer pytest-secret"})
    assert blocked.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["ok"] is True


def test_api_token_guard_rejects_spoofed_host(monkeypatch):
    """伪造 Host: localhost/127.0.0.1 不得再绕过 token（修复 Host 头鉴权绕过）。"""
    monkeypatch.setenv("LEOJARVIS_API_TOKEN", "pytest-secret")
    with TestClient(app) as client:
        spoof_localhost = client.get("/api/health", headers={"Host": "localhost"})
        spoof_loopback = client.get("/api/health", headers={"Host": "127.0.0.1:8787"})
        spoof_comma = client.get("/api/health", headers={"Host": "localhost, evil.example.com"})
    assert spoof_localhost.status_code == 401
    assert spoof_loopback.status_code == 401
    assert spoof_comma.status_code == 401


def test_trusted_local_helpers():
    """单元层验证：信任判断基于不可伪造的对端 IP，且带转发头的回环请求（隧道流量）不豁免。"""
    from leojarvis.auth import is_loopback_peer, has_forwarding_headers, is_trusted_local
    from starlette.datastructures import Headers

    assert is_loopback_peer("127.0.0.1") is True
    assert is_loopback_peer("::1") is True
    assert is_loopback_peer("::ffff:127.0.0.1") is True
    assert is_loopback_peer("10.0.0.5") is False
    assert is_loopback_peer(None) is False

    plain = Headers({"host": "localhost"})
    tunneled = Headers({"host": "localhost", "x-forwarded-for": "203.0.113.7"})
    cf = Headers({"host": "localhost", "cf-connecting-ip": "203.0.113.7"})

    assert has_forwarding_headers(plain) is False
    assert has_forwarding_headers(tunneled) is True
    # 本机直连（回环 + 无转发头）→ 豁免
    assert is_trusted_local("127.0.0.1", plain) is True
    # 隧道流量（回环对端但带转发头）→ 不豁免，必须带 token
    assert is_trusted_local("127.0.0.1", tunneled) is False
    assert is_trusted_local("127.0.0.1", cf) is False
    # 非回环对端 → 不豁免
    assert is_trusted_local("203.0.113.7", plain) is False


def test_ssrf_guard_blocks_internal_targets():
    """抓取 URL 前的 SSRF 防护：内网/本机/保留地址必须拒绝，公网放行。"""
    from leojarvis.netguard import ensure_public_url, BlockedURLError

    for bad in [
        "http://127.0.0.1:8787/health",
        "http://localhost/admin",
        "https://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "ftp://example.com/",
        "file:///etc/passwd",
    ]:
        with pytest.raises(BlockedURLError):
            ensure_public_url(bad)

    # 公网域名放行（不发起真实请求，仅做地址校验）
    assert ensure_public_url("https://example.com/") == "https://example.com/"


def test_gate_escalates_sensitive_paths():
    """读凭据路径（即便只读）必须升级为 confirm，挡掉无确认窃密。"""
    from leojarvis.agent.gate import evaluate

    assert evaluate("read_file", {"path": "~/.ssh/id_rsa"}) == "confirm"
    assert evaluate("read_file", {"path": "/Users/x/.aws/credentials"}) == "confirm"
    assert evaluate("read_file", {"path": "~/.claude/.credentials.json"}) == "confirm"
    assert evaluate("run_shell", {"command": "cat ~/.ssh/id_rsa"}) == "confirm"
    assert evaluate("run_shell", {"command": "grep token ~/.netrc"}) == "confirm"
    # 普通只读文件/命令仍自动执行
    assert evaluate("read_file", {"path": "~/project/README.md"}) == "auto"
    assert evaluate("run_shell", {"command": "ls ~/Documents"}) == "auto"


def test_final_streamer_incremental_extraction():
    """_FinalStreamer：从分块流入的 JSON 里增量提取 final 字符串值，正确处理转义。"""
    from leojarvis.agent.loop import _FinalStreamer

    s = _FinalStreamer()
    out = ""
    # 模拟逐 token 流入，final 值里含转义换行与引号
    for chunk in ['{"thought"', ': "想一下", ', '"final": "第一行', '\\n第二行 ', '\\"引用\\""}']:
        out += s.feed(chunk)
    assert out == '第一行\n第二行 "引用"'
    assert s._done is True


def test_run_agent_stream_final(monkeypatch):
    """run_agent_stream：模型直接给 final 时，流出 token 事件并以 final 事件收尾。"""
    from leojarvis.agent import loop

    def fake_stream(task, messages, **kw):
        for piece in ['{"thought":"好的",', ' "final":"你好', '，世界"}']:
            yield piece

    monkeypatch.setattr(loop, "chat_stream", fake_stream)
    monkeypatch.setattr(loop, "recall", lambda *a, **k: [])
    events = list(loop.run_agent_stream([{"role": "user", "content": "hi"}]))
    types = [e["type"] for e in events]
    assert types[-1] == "final"
    token_text = "".join(e["text"] for e in events if e["type"] == "token")
    assert token_text == "你好，世界"
    assert events[-1]["reply"] == "你好，世界"


def test_run_agent_stream_pending_for_high_risk(monkeypatch):
    """run_agent_stream：高风险工具走 pending 事件，不在本轮执行。"""
    from leojarvis.agent import loop

    def fake_stream(task, messages, **kw):
        # 请求一个 confirm 级工具（restart_service）
        yield '{"thought":"重启","action":{"tool":"restart_service","args":{"name":"x"}}}'

    monkeypatch.setattr(loop, "chat_stream", fake_stream)
    monkeypatch.setattr(loop, "recall", lambda *a, **k: [])
    events = list(loop.run_agent_stream([{"role": "user", "content": "restart x"}]))
    pend = [e for e in events if e["type"] == "pending"]
    assert len(pend) == 1
    assert pend[0]["pending_actions"][0]["tool"] == "restart_service"
    # pending 后应停止（不再产 final）
    assert events[-1]["type"] == "pending"


def test_prune_retention_keeps_referenced(monkeypatch, tmp_path):
    """保留窗口：删旧事件，但被 feedback / 记忆引用的事件必须保留。"""
    from leojarvis import db

    old_ts = db.now_ms() - 200 * 86_400_000   # 200 天前，远超 90 天窗口
    # 三条旧事件：plain 会被删；fb 被反馈引用、mem 被记忆引用 → 必须保留
    for eid, title in [("ev-plain", "旧普通事件"), ("ev-fb", "旧被反馈"), ("ev-mem", "旧被记忆")]:
        with db.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO events(id,source,kind,domain,title,content,url,meta,dedup_key,ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (eid, "test", "news", "business", title, "x", "", "{}", f"dk-{eid}", old_ts),
            )
            c.execute(
                "INSERT OR REPLACE INTO judgments(id,event_id,ts,score,take,triage,reasons,analysis) VALUES(?,?,?,?,?,?,?,?)",
                (f"j-{eid}", eid, old_ts, 0.5, "t", "digest", "[]", None),
            )
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO feedback(id,event_id,signal,ts) VALUES(?,?,?,?)", ("fb1", "ev-fb", "important", old_ts))
    db.insert_memory("记住这条", memory_type="insight", subject="s", source_events=["ev-mem"], status="active")

    removed = db.prune_old_data(event_days=90)
    assert removed["events"] >= 1
    with db.conn() as c:
        rows = {r[0] if not isinstance(r, dict) else r["id"]
                for r in c.execute("SELECT id FROM events WHERE id IN ('ev-plain','ev-fb','ev-mem')")}
    assert "ev-plain" not in rows      # 普通旧事件被删
    assert "ev-fb" in rows             # 被反馈引用 → 保留
    assert "ev-mem" in rows            # 被记忆引用 → 保留


def test_layered_memory_and_forget():
    """超级 Jarvis P1：分层记忆写入/按层查询/反馈强化/按来源遗忘。"""
    from leojarvis import db
    db.init_db()
    f = db.insert_memory("P1 测试事实", layer="fact", status="active",
                         origin="pytest", source_ref="pytest:p1", salience=0.5)
    db.insert_memory("P1 测试规律", layer="pattern", status="active",
                     origin="pytest", source_ref="pytest:p1")
    db.insert_memory("P1 测试情景", layer="episode", status="active",
                     origin="pytest", source_ref="pytest:p1-other")
    counts = db.memory_layer_counts()
    assert counts.get("fact", 0) >= 1 and counts.get("pattern", 0) >= 1
    facts = db.list_memories_by_layer(["fact"], limit=50)
    assert any(r["statement"] == "P1 测试事实" for r in facts)
    # 反馈强化
    assert db.adjust_memory(f, salience_delta=0.2) is True
    # 被遗忘权：删 pytest:p1 来源应删掉 fact+pattern 两条，不动 p1-other
    deleted = db.delete_memories_by_source("pytest:p1")
    assert deleted == 2
    remaining = [r["statement"] for r in db.list_memories_by_layer(None, limit=200)]
    assert "P1 测试事实" not in remaining and "P1 测试规律" not in remaining
    assert "P1 测试情景" in remaining
    # 清理
    db.delete_memories_by_source("pytest:p1-other")


def test_personal_data_privacy_gate():
    """超级 Jarvis P2：同意分级 + 红线 + 脱敏 + 按来源遗忘。"""
    from leojarvis import personal_data, db
    db.init_db()
    # work 默认同意 → 收
    work = personal_data.ingest_items(personal_data.from_text_document(
        "测试工作内容", source_ref="pytest:pd-work", kind="work"))
    assert work.accepted == 1
    # chat 默认不同意 → 跳过
    chat = personal_data.ingest_items(personal_data.from_chat_export(
        [{"sender": "x", "text": "hi"}], source_ref="pytest:pd-chat"))
    assert chat.accepted == 0 and chat.skipped_no_consent == 1
    # 红线词 → 跳过
    rl = personal_data.ingest_items([personal_data.DataItem(
        text="我的密码是 abc", kind="work", source_ref="pytest:pd-rl")])
    assert rl.skipped_redline == 1
    # 脱敏：sk- key 被替换但仍收
    rd = personal_data.ingest_items([personal_data.DataItem(
        text="key sk-abcdefghijklmnop1234 备注", kind="work", source_ref="pytest:pd-rd")])
    assert rd.accepted == 1 and rd.redacted == 1
    # 被遗忘权
    assert personal_data.forget_source("pytest:pd-work") == 1
    personal_data.forget_source("pytest:pd-rd")


def test_distill_personal_data_and_dynamic_profile(monkeypatch):
    """超级 Jarvis P3：从情景记忆提炼 fact/pattern，确认后并入动态画像。"""
    from leojarvis import db, personal_data, models_router
    from leojarvis.memory import reflect, profile
    db.init_db()
    personal_data.ingest_items(personal_data.from_text_document(
        "周一先看持仓再写代码。\n\n深夜还在调记忆模块。",
        source_ref="pytest:p3test", kind="work"), auto_confirm=True)
    fake = ('[{"layer":"pattern","subject":"作息","statement":"P3测试规律深夜写码","salience":0.8},'
            '{"layer":"fact","subject":"项目","statement":"P3测试事实在做记忆模块","salience":0.7}]')
    monkeypatch.setattr(models_router, "chat", lambda *a, **k: fake)
    r = reflect.reflect_personal_data(limit=50)
    assert r["created"] == 2
    distilled = [p for p in db.list_pending_memories(limit=50) if p["origin"] == "reflect_personal_data"]
    assert len(distilled) == 2
    for p in distilled:
        db.update_memory_status(p["id"], "active")
    ptext = profile.profile_text()
    assert "已学到的事实/规律" in ptext and "P3测试" in ptext
    # cleanup
    personal_data.forget_source("pytest:p3test")
    with db.conn() as c:
        c.execute("DELETE FROM memories WHERE statement LIKE 'P3测试%'")


def test_cognition_advise_decide_anticipate(monkeypatch):
    """超级 Jarvis P4：出主意/决策/预判产出结构化结果，LLM 不可用时优雅降级。"""
    from leojarvis import db, cognition, models_router
    db.init_db()
    db.insert_memory("P4测试事实", layer="fact", status="active", origin="pytest",
                     source_ref="pytest:p4test", confidence=0.8, salience=0.7)
    db.insert_memory("P4测试规律", layer="pattern", status="active", origin="pytest",
                     source_ref="pytest:p4test", confidence=0.8, salience=0.7)
    monkeypatch.setattr(models_router, "chat",
                        lambda *a, **k: '{"summary":"建议X","suggestions":["a"],"rationale":"r"}')
    assert cognition.advise("某情境")["summary"] == "建议X"
    monkeypatch.setattr(models_router, "chat",
                        lambda *a, **k: '{"options":[{"name":"A","pros":[],"cons":[],"score":80},{"name":"B","pros":[],"cons":[],"score":40}],"recommendation":"A","why":"w"}')
    d = cognition.decide("选哪个", ["A", "B"])
    assert d["recommendation"] == "A" and len(d["options"]) == 2
    monkeypatch.setattr(models_router, "chat",
                        lambda *a, **k: '[{"headline":"提醒","reason":"规律","urgency":"low"}]')
    assert len(cognition.anticipate("ctx")["predictions"]) == 1
    # 降级不崩
    monkeypatch.setattr(models_router, "chat", lambda *a, **k: (_ for _ in ()).throw(Exception("down")))
    assert cognition.advise("x")["ok"] and cognition.decide("q", ["1", "2"])["ok"]
    # 边界校验
    assert cognition.decide("q", ["only-one"]).get("ok") is False
    db.delete_memories_by_source("pytest:p4test")


def test_feedback_loop_and_memory_sweep():
    """超级 Jarvis P5：反馈强化/衰减、更正建新记忆、记忆体检归档低置信。"""
    from leojarvis import db
    db.init_db()
    mid = db.insert_memory("P5测试记忆", layer="fact", status="active", origin="pytest",
                           source_ref="pytest:p5t", confidence=0.5, salience=0.5)

    def state(i):
        with db.conn() as c:
            r = c.execute("SELECT salience,confidence,status FROM memories WHERE id=?", (i,)).fetchone()
        return round(r["salience"], 3), round(r["confidence"], 3), r["status"]

    assert db.adjust_memory(mid, salience_delta=0.15, confidence_delta=0.1)
    s, conf, _ = state(mid)
    assert s > 0.5 and conf > 0.5
    assert db.adjust_memory(mid, salience_delta=-0.15)
    # 体检：低置信记忆应被归档
    low = db.insert_memory("低置信", layer="fact", status="active", origin="pytest",
                           source_ref="pytest:p5t", confidence=0.05)
    swept = db.memory_health_sweep(min_confidence=0.2)
    assert swept["archived"] >= 1
    assert state(low)[2] == "archived"
    db.delete_memories_by_source("pytest:p5t")


def test_embedding_backend_degrades_gracefully():
    """embed() 多后端：未配置真模型时降级哈希向量、维度稳定、不抛异常。"""
    from leojarvis import embeddings
    vec = embeddings.embed("中文 and english mixed 测试文本")
    assert isinstance(vec, list)
    assert len(vec) == embeddings._dimension()
    assert all(isinstance(x, float) for x in vec[:8])


def test_judge_batch_and_fallback(monkeypatch):
    """judge_batch：一次调用判多条，按 idx 映射；JSON 异常时返回空 dict 让调用方逐条兜底。"""
    from dataclasses import dataclass
    from leojarvis.judge import engine

    @dataclass
    class FakeItem:
        title: str
        content: str
        source: str = "s"
        domain: str = "business"
        kind: str = "news"

    items = [FakeItem("AI agent 框架发布", "新框架"), FakeItem("无关八卦", "明星")]
    arr = ('[{"idx":0,"score":0.8,"triage":"notify","title_zh":"AI 框架","take":"机会","reasons":["a"]},'
           '{"idx":1,"score":0.1,"triage":"ignore","title_zh":"八卦","take":"背景","reasons":["b"]}]')
    monkeypatch.setattr(engine, "profile_text", lambda: "画像")
    monkeypatch.setattr(engine, "chat", lambda *a, **k: arr)
    out = engine.judge_batch(items)
    assert set(out.keys()) == {0, 1}
    assert out[0].triage == "notify" and out[0].analysis["title_zh"] == "AI 框架"
    assert out[1].triage == "ignore"

    monkeypatch.setattr(engine, "chat", lambda *a, **k: "not json")
    assert engine.judge_batch(items) == {}   # 解析失败 → 空，触发逐条回退


def test_websocket_token_guard_when_enabled(monkeypatch):
    monkeypatch.setenv("LEOJARVIS_API_TOKEN", "pytest-secret")
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws/notify"):
                pass
        with client.websocket_connect("/api/ws/notify?token=pytest-secret") as ws:
            ws.send_text("ping")


def test_agent_chat_route_contract(monkeypatch):
    from leojarvis.api import routes

    def fake_run_agent(messages):
        assert messages == [{"role": "user", "content": "ping"}]
        return {"reply": "pong", "pending_actions": []}

    monkeypatch.setattr(routes, "run_agent", fake_run_agent)
    with TestClient(app) as client:
        res = client.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "ping"}]})
    assert res.status_code == 200
    assert res.json()["reply"] == "pong"
    assert res.json()["pending_actions"] == []


def test_cli_agent_run_route_contract(monkeypatch):
    from leojarvis.agent import cli_agents

    def fake_spawn_cli_agent(name, prompt, cwd=None, model=None):
        assert name == "codex"
        assert prompt == "safe smoke"
        assert cwd == "/tmp"
        assert model == "default"
        return {"ok": True, "id": "session-test"}

    monkeypatch.setattr(cli_agents, "spawn_cli_agent", fake_spawn_cli_agent)
    with TestClient(app) as client:
        res = client.post(
            "/api/agents/cli/run",
            json={"name": "codex", "prompt": "safe smoke", "cwd": "/tmp", "model": "default"},
        )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "id": "session-test"}


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


def test_briefing_detail_keeps_readable_source_body():
    db.init_db()
    event_id = None
    body = (
        "Article URL: https://example.com/post Comments URL: https://news.ycombinator.com/item?id=1 "
        "Points: 54 # Comments: 11 "
        + "这条资讯详细说明了产品发布背景、关键功能、用户影响、技术实现差异和后续观察点。"
        * 45
    )
    try:
        event_id = db.insert_event(
            source="rss:pytest",
            domain="business",
            kind="news",
            title="测试长资讯详情",
            content=body,
            dedup_key="pytest-long-briefing-detail",
        )
        assert event_id
        db.insert_judgment(
            event_id=event_id,
            score=0.9,
            take="这是一条用于验证详情阅读面积和正文长度的高优先资讯。",
            triage="digest",
            reasons=["长正文", "产品相关"],
            analysis={"summary": "长资讯摘要"},
        )
        with TestClient(app) as client:
            res = client.get(f"/briefing/items/{event_id}")
        assert res.status_code == 200
        item = res.json()["item"]
        assert len(item["detail"]) > 900
        assert item["detail"] == item["source_detail"]
        assert item["source_detail_missing"] is False
        assert "Article URL" not in item["detail"]
        assert "Comments URL" not in item["detail"]
        assert "Points:" not in item["detail"]
        assert "这条资讯详细说明了产品发布背景" in item["detail"]
    finally:
        if event_id:
            with db.conn() as c:
                c.execute("DELETE FROM judgments WHERE event_id=?", (event_id,))
                c.execute("DELETE FROM events WHERE id=?", (event_id,))


def test_briefing_source_detail_translates_english_without_rewriting(monkeypatch):
    import leojarvis.models_router as models_router

    db.init_db()
    event_id = None
    source_text = (
        "Pytest unique source detail 20260610 says AlphaTool shipped version 2.1 with offline mode, "
        "three benchmark results, and a migration guide for existing users. "
    ) * 8

    def fake_chat(task, messages, **kwargs):
        assert task == "translate"
        assert "不摘要、不扩写、不推断" in messages[0]["content"]
        assert "AlphaTool shipped version 2.1" in messages[1]["content"]
        return "Pytest 唯一来源详情 20260610 表示 AlphaTool 发布了 2.1 版本，包含离线模式、三项基准结果，以及面向现有用户的迁移指南。"

    monkeypatch.setattr(models_router, "chat", fake_chat)
    monkeypatch.setenv("LEOJARVIS_ENABLE_TEST_TRANSLATION", "1")
    try:
        event_id = db.insert_event(
            source="rss:pytest",
            domain="business",
            kind="news",
            title="English source detail translation test",
            content=source_text,
            dedup_key="pytest-source-detail-translation",
        )
        assert event_id
        db.insert_judgment(
            event_id=event_id,
            score=0.91,
            take="测试英文来源详情翻译。",
            triage="digest",
            reasons=["translation"],
            analysis={"summary": "英文详情翻译测试"},
        )
        with TestClient(app) as client:
            res = client.get(f"/briefing/items/{event_id}")
        assert res.status_code == 200
        item = res.json()["item"]
        assert item["source_detail_translated"] is True
        assert "AlphaTool 发布了 2.1 版本" in item["source_detail"]
        assert "AlphaTool shipped version 2.1" not in item["source_detail"]
        assert "AlphaTool shipped version 2.1" in item["source_detail_raw"]
        assert item["detail"] == item["source_detail"]
    finally:
        if event_id:
            with db.conn() as c:
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


def test_seed_defaults_disables_polluted_browser_history_targets():
    db.init_db()
    ts = db.now_ms()
    bad_ids = [f"pytest-polluted-target-{uuid.uuid4().hex}" for _ in range(3)]
    good_id = f"pytest-useful-target-{uuid.uuid4().hex}"
    rows = [
        (bad_ids[0], "and", "topic", "and"),
        (bad_ids[1], "appstoreconnect.apple.com", "topic", "appstoreconnect.apple.com"),
        (bad_ids[2], "netease", "topic", "netease"),
        (good_id, "OpenAI", "topic", "OpenAI"),
    ]
    with db.conn() as c:
        for row_id, label, kind, query in rows:
            c.execute("DELETE FROM intelligence_targets WHERE id=?", (row_id,))
            c.execute("DELETE FROM intelligence_targets WHERE kind=? AND query=?", (kind, query))
            c.execute(
                """INSERT INTO intelligence_targets(id,label,kind,query,enabled,created_ts,updated_ts)
                   VALUES(?,?,?,?,1,?,?)""",
                (row_id, label, kind, query, ts, ts),
            )

    try:
        seed_defaults()
        with db.conn() as c:
            states = {
                row["query"]: int(row["enabled"])
                for row in c.execute(
                    "SELECT query, enabled FROM intelligence_targets WHERE id IN (?,?,?,?)",
                    (*bad_ids, good_id),
                ).fetchall()
            }
        assert states["and"] == 0
        assert states["appstoreconnect.apple.com"] == 0
        assert states["netease"] == 0
        assert states["OpenAI"] == 1
    finally:
        with db.conn() as c:
            c.execute(
                "DELETE FROM intelligence_targets WHERE id IN (?,?,?,?)",
                (*bad_ids, good_id),
            )


def test_homepage_briefing_scope_excludes_non_tech_finance_noise():
    assert _is_homepage_scope_item({
        "kind": "news",
        "source": "rss:IT之家",
        "title": "台积电加速研发 CoPoS 封装替代 CoWoS，玻璃基板降本30%",
        "content": "半导体先进封装和玻璃核心基板进展。",
    })
    assert _is_homepage_scope_item({
        "kind": "github_repo",
        "source": "intel:github",
        "title": "heygen-com/hyperframes · GitHub 项目雷达",
        "content": "AI 视频与开发者工具项目。",
    })
    assert not _is_homepage_scope_item({
        "kind": "news",
        "source": "rss:MarketWatch",
        "title": "内部推动削弱华盛顿最严厉金融监管机构",
        "content": "金融监管、华尔街和市场政策变化。",
    })
    assert not _is_homepage_scope_item({
        "kind": "news",
        "source": "rss:IT之家",
        "title": "加州“亿万富翁税”提案获足够签名",
        "content": "AI 热潮让许多科技富豪财富增长，英伟达 CEO 表态支持，但主题仍是税务公投。",
    })


def test_x_monitor_defaults_include_ai_tech_sources():
    cfg = user_settings.load()["x_monitor"]
    assert "OpenAI" in cfg["users"]
    assert "AnthropicAI" in cfg["users"]
    assert "GoogleDeepMind" in cfg["users"]
    feeds = x_monitor_feeds()
    assert any(feed["name"] == "X · @OpenAI" for feed in feeds)


def test_localize_fallback_uses_display_safe_label():
    text = to_chinese("A new agentic workflow automation benchmark for AI coding agents", allow_llm=False)
    assert "英文来源摘要" not in text
    assert "A new" not in text
    assert "for AI coding" not in text
    assert "基准测试" in text
    assert text


def test_localize_fallback_avoids_half_translated_social_security():
    text = to_chinese(
        "How to work in retirement without seeing your Social Security checks slashed",
        allow_llm=False,
    )
    assert "Social 安全" not in text
    assert "Social Security" not in text
    assert "社会保障" in text or "退休" in text


def test_localize_detects_mixed_chinese_english_titles():
    text = to_chinese("大语言模型 Are Complicated Now（重复）", context="简报标题", allow_llm=False)
    assert "Are Complicated Now" not in text
    assert "Are" not in text
    assert "大语言模型" in text
    assert not has_noisy_english(text)


def test_localize_keeps_technical_proper_nouns_in_chinese_titles():
    title = "NASA 测试新一代月球 / 火星探测车原型 ERNEST：含主动悬挂与 AI 强化自主系统"
    assert not has_noisy_english(title)
    assert to_chinese(title, context="简报标题", allow_llm=False).startswith("NASA 测试")


def test_tavily_paid_fallback_budget_is_capped(tmp_path, monkeypatch):
    from leojarvis.intelligence import scanner

    monkeypatch.setattr(scanner, "_TAVILY_USAGE_PATH", tmp_path / "tavily_usage.json")
    monkeypatch.setattr(scanner, "_TAVILY_DAILY_QUERY_LIMIT", 1)
    monkeypatch.setattr(scanner, "_TAVILY_COOLDOWN_SECONDS", 6 * 3600)

    allowed, first = scanner._reserve_tavily_query("pytest")
    blocked, second = scanner._reserve_tavily_query("pytest")

    assert allowed is True
    assert first["reserved"] is True
    assert blocked is False
    assert second["skipped"] in {"tavily_daily_limit", "tavily_cooldown"}


def test_mcp_search_respects_tavily_paid_budget(tmp_path, monkeypatch):
    from leojarvis import mcp_gateway
    from leojarvis.intelligence import scanner

    calls = []

    def fake_search_web(query: str, *, limit: int = 8, include_answer: bool = False) -> dict:
        calls.append((query, limit, include_answer))
        return {"ok": True, "backend": "tavily_search", "items": [], "duration_ms": 1}

    monkeypatch.setattr(scanner, "_TAVILY_USAGE_PATH", tmp_path / "tavily_usage.json")
    monkeypatch.setattr(scanner, "_TAVILY_DAILY_QUERY_LIMIT", 1)
    monkeypatch.setattr(scanner, "_TAVILY_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(mcp_gateway, "search_web", fake_search_web)

    with TestClient(app) as client:
        first = client.post("/mcp/search", json={"query": "latest AI news", "limit": 2, "purpose": "intel_fallback"})
        second = client.post("/mcp/search", json={"query": "latest AI news", "limit": 2, "purpose": "intel_fallback"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["error"] == "tavily_budget_exhausted"
    assert len(calls) == 1


def test_mcp_search_rejects_non_fallback_paid_usage(tmp_path, monkeypatch):
    from leojarvis import mcp_gateway
    from leojarvis.intelligence import scanner

    calls = []

    def fake_search_web(query: str, *, limit: int = 8, include_answer: bool = False) -> dict:
        calls.append(query)
        return {"ok": True, "backend": "tavily_search", "items": [], "duration_ms": 1}

    monkeypatch.setattr(scanner, "_TAVILY_USAGE_PATH", tmp_path / "tavily_usage.json")
    monkeypatch.setattr(mcp_gateway, "search_web", fake_search_web)

    with TestClient(app) as client:
        res = client.post("/mcp/search", json={"query": "latest AI news", "limit": 2, "purpose": "manual"})

    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "tavily_reserved_for_intel_fallback"
    assert calls == []


def test_briefing_keeps_tavily_as_tail_fallback_after_sorting():
    from leojarvis.briefing import builder

    now = db.now_ms()
    primary = {
        "event_id": "pytest-primary",
        "title": "主信源新闻",
        "source_raw": "rss:pytest",
        "kind": "news",
        "domain": "business",
        "ts": now - 60 * 60 * 1000,
        "score": 0.43,
        "triage": "digest",
    }
    tavily = {
        "event_id": "pytest-tavily",
        "title": "Tavily 搜索补充",
        "source_raw": "intel:tavily:pytest",
        "channel": "tavily_search",
        "kind": "news",
        "domain": "business",
        "ts": now,
        "score": 0.99,
        "triage": "notify",
    }

    ranked = sorted([tavily, primary], key=builder._timely_priority_key, reverse=True)
    tailed = builder._with_tavily_tail(ranked)

    assert [row["event_id"] for row in tailed] == ["pytest-primary", "pytest-tavily"]


def test_briefing_recency_tier_then_priority_for_primary_sources():
    from leojarvis.briefing import builder

    now = db.now_ms()
    fresh_low = {
        "event_id": "pytest-fresh-low",
        "title": "最新主信源",
        "source_raw": "rss:pytest",
        "kind": "news",
        "domain": "business",
        "ts": now - 2 * 60 * 60 * 1000,
        "score": 0.43,
        "triage": "digest",
        "priority": "观察",
    }
    stale_high = {
        "event_id": "pytest-stale-high",
        "title": "较旧高分主信源",
        "source_raw": "rss:pytest",
        "kind": "news",
        "domain": "business",
        "ts": now - 8 * 60 * 60 * 1000,
        "score": 0.99,
        "triage": "notify",
        "priority": "高优先",
    }
    same_tier_high = {**fresh_low, "event_id": "pytest-same-high", "ts": now - 5 * 60 * 60 * 1000, "score": 0.85, "triage": "notify", "priority": "高优先"}
    same_tier_low = {**fresh_low, "event_id": "pytest-same-low", "ts": now - 2 * 60 * 60 * 1000, "score": 0.45, "triage": "digest", "priority": "观察"}

    ranked = sorted([stale_high, fresh_low], key=builder._timely_priority_key, reverse=True)
    assert ranked[0]["event_id"] == "pytest-fresh-low"

    ranked_same_window = sorted([same_tier_low, same_tier_high], key=builder._timely_priority_key, reverse=True)
    assert ranked_same_window[0]["event_id"] == "pytest-same-high"


def test_briefing_priority_quota_is_recency_aware():
    from leojarvis.briefing import builder

    now = db.now_ms()
    fresh = {
        "event_id": "pytest-fresh-important",
        "title": "六小时内的重要主信源",
        "source_raw": "rss:pytest",
        "kind": "news",
        "domain": "business",
        "ts": now - 2 * 60 * 60 * 1000,
        "score": 0.66,
        "triage": "digest",
        "priority": "观察",
    }
    stale = {
        "event_id": "pytest-stale-important",
        "title": "三十小时前的旧高分主信源",
        "source_raw": "rss:pytest",
        "kind": "news",
        "domain": "business",
        "ts": now - 30 * 60 * 60 * 1000,
        "score": 0.99,
        "triage": "notify",
        "priority": "高优先",
    }

    rows = [stale, fresh]
    builder._apply_priority_quota(rows)

    assert fresh["priority"] == "高优先"
    assert stale["priority"] != "高优先"


def test_briefing_deprioritizes_low_signal_web_changes():
    from leojarvis.briefing import builder

    now = db.now_ms()
    web_change = {
        "event_id": "pytest-web-change",
        "title": "海外资讯：Mac",
        "source_raw": "intel:web:海外资讯",
        "kind": "web_change",
        "domain": "business",
        "ts": now,
        "score": 0.8,
        "triage": "digest",
        "priority": "观察",
    }
    rss_news = {
        "event_id": "pytest-rss-news",
        "title": "Cloudflare 为 AI Agent 推出临时账户",
        "source_raw": "intel:rss:pytest",
        "kind": "news",
        "domain": "business",
        "ts": now - 5 * 60 * 1000,
        "score": 0.62,
        "triage": "digest",
        "priority": "中优先",
    }

    ranked = sorted([web_change, rss_news], key=builder._timely_priority_key, reverse=True)
    assert ranked[0]["event_id"] == "pytest-rss-news"


def test_tavily_removed_when_primary_sources_are_sufficient():
    from leojarvis.briefing import builder

    def primary(index: int) -> dict:
        return {
            "event_id": f"pytest-primary-{index}",
            "source_raw": f"rss:pytest:{index}",
            "kind": "news",
            "domain": "business",
            "ts": db.now_ms() - index,
        }

    def tavily(index: int) -> dict:
        return {
            "event_id": f"pytest-tavily-{index}",
            "source_raw": f"intel:tavily:pytest:{index}",
            "channel": "tavily_search",
            "kind": "news",
            "domain": "business",
            "ts": db.now_ms() + index,
        }

    now = db.now_ms()
    enough = [primary(i) | {"ts": now - i} for i in range(4)] + [tavily(i) for i in range(3)]
    assert all(item.get("channel") != "tavily_search" for item in builder._with_tavily_tail(enough))

    scarce = [primary(i) | {"ts": now - i} for i in range(3)] + [tavily(i) for i in range(3)]
    tailed = builder._with_tavily_tail(scarce)
    assert [item["event_id"] for item in tailed[-1:]] == ["pytest-tavily-0"]

    stale_primary = [primary(i) | {"ts": now - 30 * 60 * 60 * 1000 - i} for i in range(4)]
    stale_tailed = builder._with_tavily_tail(stale_primary + [tavily(9)])
    assert stale_tailed[-1]["event_id"] == "pytest-tavily-9"


def test_cockpit_homepage_caps_tavily_tail_fallback():
    from leojarvis import cockpit

    now = db.now_ms()
    primaries = [
        {"event_id": f"pytest-primary-{index}", "kind": "news", "source_raw": "rss:pytest", "ts": now - index}
        for index in range(3)
    ]
    tavily = [
        {
            "event_id": f"pytest-tavily-{index}",
            "kind": "news",
            "source_raw": f"intel:tavily:pytest:{index}",
            "channel": "tavily_search",
            "ts": now + index,
        }
        for index in range(3)
    ]

    rows = cockpit._homepage_briefing_top(primaries + tavily, limit=12)

    assert [item["event_id"] for item in rows] == [
        "pytest-primary-0",
        "pytest-primary-1",
        "pytest-primary-2",
        "pytest-tavily-2",
    ]


def test_briefing_display_strips_localization_prefixes():
    from leojarvis.briefing import builder

    title = builder._display_chinese("中文标题：宝马推出印度产 MINI Countryman C 车型", context="简报标题")
    summary = builder._display_chinese("中文摘要：这是一条摘要", context="简报摘要")
    repo_mail = builder._display_chinese("[leoyb1010/leoapi] CI 运行失败：main 分支", context="简报标题")

    assert not title.startswith("中文标题")
    assert title.startswith("宝马推出")
    assert summary == "这是一条摘要"
    assert repo_mail == "[leoyb1010/leoapi] CI 运行失败：main 分支"


def test_briefing_detects_generic_synthetic_titles():
    from leojarvis.briefing import builder

    assert builder._is_generic_synthetic_title("AI 与开发者工具资讯：AI")
    assert builder._is_generic_synthetic_title("AI 与开发者工具资讯：NVIDIA、AI")
    assert builder._is_generic_synthetic_title("海外资讯：Anthropic、DeepMind")
    assert not builder._is_generic_synthetic_title("NASA 测试新一代月球 / 火星探测车原型 ERNEST")


def test_github_briefing_title_preserves_repo_name():
    from leojarvis.briefing import builder

    row = {
        "event_id": "pytest-github-title",
        "title": "owner/project · GitHub 项目雷达",
        "content": "仓库介绍：测试",
        "url": "https://github.com/owner/project",
        "domain": "business",
        "source": "intel:github",
        "kind": "github_repo",
        "meta": '{"repo":"owner/project"}',
        "score": 0.8,
        "take": "测试",
        "triage": "digest",
        "reasons": "[]",
        "analysis": '{"title_zh":"owner/project · GitHub 高增速项目","summary":"测试"}',
        "ts": db.now_ms(),
    }

    item = builder._briefing_item(row, [], {"owner/project": {"repo_full_name": "owner/project"}})

    assert item["title"] == "owner/project · GitHub 高增速项目"


def test_compact_item_omits_original_title_from_list_payload():
    from leojarvis.briefing import builder

    compact = builder._compact_item({
        "event_id": "pytest",
        "title": "大语言模型现在变复杂了",
        "original_title": "LLMs Are Complicated Now",
    })

    assert compact["title"] == "大语言模型现在变复杂了"
    assert "original_title" not in compact


def test_briefing_uses_latest_judgment_per_event():
    from leojarvis.briefing import builder

    dedup_key = f"pytest-latest-judgment-{uuid.uuid4().hex}"
    event_id = db.insert_event(
        source="intel:rss:pytest",
        domain="business",
        kind="news",
        title="NASA 测试新一代月球探测车原型 ERNEST",
        content="NASA 公布 ERNEST 探测车原型，使用 AI 强化自主系统。",
        url="https://example.com/pytest-latest-judgment",
        meta={"published": "Sat, 20 Jun 2026 14:36:02 GMT", "category": "AI科技"},
        dedup_key=dedup_key,
    )
    try:
        old_id = db.insert_judgment(
            event_id=event_id,
            score=0.92,
            take="旧判断",
            triage="digest",
            reasons=["旧判断"],
            analysis={"title_zh": "AI 与开发者工具资讯：AI", "summary": "旧泛标题"},
        )
        new_id = db.insert_judgment(
            event_id=event_id,
            score=0.92,
            take="新判断",
            triage="digest",
            reasons=["新判断"],
            analysis={"title_zh": "NASA 测试新一代月球探测车原型 ERNEST", "summary": "新标题"},
        )
        now = db.now_ms()
        with db.conn() as c:
            c.execute("UPDATE judgments SET ts=? WHERE id=?", (now - 1000, old_id))
            c.execute("UPDATE judgments SET ts=? WHERE id=?", (now, new_id))

        builder.invalidate_today_cache()
        item = builder.build_item_detail(event_id)

        assert item is not None
        assert item["title"] == "NASA 测试新一代月球探测车原型 ERNEST"
    finally:
        with db.conn() as c:
            c.execute("DELETE FROM judgments WHERE event_id=?", (event_id,))
            c.execute("DELETE FROM events WHERE id=?", (event_id,))
        builder.invalidate_today_cache()


def test_compact_briefing_uses_tavily_only_as_tail_fallback():
    from leojarvis.briefing import builder

    now = db.now_ms()

    def primary(index: int) -> dict:
        return {
            "event_id": f"pytest-primary-{index}",
            "title": f"主信源 {index}",
            "source_raw": f"rss:pytest:{index}",
            "kind": "news",
            "domain": "business",
            "ts": now - index,
            "score": 0.5,
            "triage": "digest",
        }

    def tavily(index: int) -> dict:
        return {
            "event_id": f"pytest-tavily-{index}",
            "title": f"Tavily 补充 {index}",
            "source_raw": f"intel:tavily:pytest:{index}",
            "channel": "tavily_search",
            "kind": "news",
            "domain": "business",
            "ts": now + index,
            "score": 0.68,
            "triage": "digest",
        }

    enough_primary = [primary(i) | {"ts": now - i} for i in range(4)] + [tavily(i) for i in range(3)]
    compact = builder._balanced_compact_items({"items": enough_primary}, 12)
    assert all(item.get("channel") != "tavily_search" for item in compact)

    scarce_primary = [primary(i) | {"ts": now - i} for i in range(3)] + [tavily(i) for i in range(5)]
    compact = builder._balanced_compact_items({"items": scarce_primary}, 12)
    tavily_ids = [item["event_id"] for item in compact if item.get("channel") == "tavily_search"]
    assert tavily_ids == ["pytest-tavily-4"]
    assert compact[-1]["event_id"] == "pytest-tavily-4"


def test_compact_briefing_preserves_backend_order_and_drops_synthetic_noise():
    from leojarvis.briefing import builder

    now = db.now_ms()
    rows = [
        {
            "event_id": "pytest-fresh-primary",
            "title": "OpenAI 发布开发者工具更新",
            "source_raw": "intel:rss:OpenAI",
            "kind": "news",
            "domain": "business",
            "ts": now,
            "score": 0.62,
            "triage": "digest",
        },
        {
            "event_id": "pytest-noise",
            "title": "Cloudflare、Zero-trust、Tailscale 相关动态",
            "source_raw": "intel:web:海外资讯",
            "kind": "web_change",
            "domain": "business",
            "ts": now - 1,
            "score": 0.8,
            "triage": "digest",
        },
        {
            "event_id": "pytest-important-same-window",
            "title": "NVIDIA 发布推理性能更新",
            "source_raw": "intel:rss:NVIDIA",
            "kind": "news",
            "domain": "business",
            "ts": now - 2,
            "score": 0.88,
            "triage": "notify",
        },
        {
            "event_id": "pytest-tavily",
            "title": "Tavily 搜索补充",
            "source_raw": "intel:tavily:ai",
            "channel": "tavily_search",
            "kind": "news",
            "domain": "business",
            "ts": now + 60_000,
            "score": 0.68,
            "triage": "digest",
        },
    ]

    compact = builder._balanced_compact_items({"items": rows}, 12)

    assert [item["event_id"] for item in compact] == [
        "pytest-important-same-window",
        "pytest-fresh-primary",
        "pytest-tavily",
    ]


def test_compact_briefing_focus_uses_news_focus_not_raw_items_head():
    from leojarvis.briefing import builder

    data = {
        "items": [
            {
                "event_id": "pytest-github",
                "title": "owner/project · GitHub 高增速项目",
                "kind": "github_repo",
                "source_raw": "intel:github",
            },
            {
                "event_id": "pytest-news",
                "title": "OpenAI 发布开发者工具更新",
                "kind": "news",
                "source_raw": "intel:rss:OpenAI",
            },
        ],
        "focus": [
            {
                "event_id": "pytest-news",
                "title": "OpenAI 发布开发者工具更新",
                "kind": "news",
                "source_raw": "intel:rss:OpenAI",
            }
        ],
    }

    compact = builder._compact_today(data, limit=2)

    assert [item["event_id"] for item in compact["focus"]] == ["pytest-news"]


def test_today_focus_omits_low_information_fallback_summary():
    from leojarvis.briefing import builder

    rows = [
        {
            "event_id": "pytest-lead",
            "title": "Sean Lynch: MCP的真正价值在于将认证流程隔离在智能体上下文之外",
            "kind": "news",
            "priority": "高优先",
            "take": "来源提到智能体、MCP、模型，已保留原始链接，可打开查看完整上下文。",
        },
        {
            "event_id": "pytest-other",
            "title": "GPT-5.6 系列有望下周发布，性能与定价优势明显",
            "kind": "news",
            "priority": "高优先",
            "take": "模型发布节奏可能影响开发者工具选型。",
        },
        {
            "event_id": "pytest-repo",
            "title": "owner/project · GitHub 高增速项目",
            "kind": "github_repo",
            "priority": "高优先",
            "take": "测试",
        },
    ]

    text = builder._today_focus_text(rows)

    assert "来源提到" not in text
    assert "已保留原始链接" not in text
    assert text.count("GitHub 雷达另有") == 1
    assert "Sean Lynch" in text


def test_cockpit_and_personal_notes_endpoints(monkeypatch):
    import leojarvis.models_router as models_router

    def fake_chat(task, messages, **kwargs):
        return "## 核心结论\n\n- 已整理为结构化 Markdown。"

    monkeypatch.setattr(models_router, "chat", fake_chat)
    db.init_db()
    note_id = None
    transformed_id = None
    attachment_id = None
    attachment_path = None
    with TestClient(app) as client:
        try:
            note = client.post("/personal-notes", json={
                "title": "测试个人记事",
                "content": "```markdown\n# 测试个人记事\n\n-  这是一条带标签的个人记事，用于验证产品化记事接口。\n```",
                "tags": ["测试", "个人记事"],
                "project_name": "pytest notebook",
            })
            assert note.status_code == 200
            body = note.json()
            assert body["ok"] is True
            note_id = body["note"]["id"]
            assert body["note"]["title"] == "测试个人记事"
            assert body["note"]["content"].startswith("# 测试个人记事")
            assert "- 这是一条带标签" in body["note"]["content"]

            listed = client.get("/personal-notes?q=产品化")
            assert listed.status_code == 200
            assert listed.json()["stats"]["total"] >= 1
            limited = client.get("/personal-notes?compact=1&limit=1")
            assert limited.status_code == 200
            assert len(limited.json()["notes"]) <= 1

            notebooks = client.get("/personal-notes/notebooks")
            assert notebooks.status_code == 200
            assert any(row["name"] == "pytest notebook" for row in notebooks.json()["notebooks"])
            assert any(tpl["id"] == "summary" for tpl in notebooks.json()["templates"])

            transformed = client.post(f"/personal-notes/{note_id}/transform", json={"template": "summary"})
            assert transformed.status_code == 200
            transformed_id = transformed.json()["note"]["id"]
            assert "AI整理" in transformed.json()["note"]["tags"]
            assert "核心结论" in transformed.json()["note"]["content"]

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
                if transformed_id:
                    client.delete(f"/personal-notes/{transformed_id}")
                with db.conn() as c:
                    if attachment_id:
                        c.execute("DELETE FROM personal_note_attachments WHERE id=?", (attachment_id,))
                    for cleanup_id in [note_id, transformed_id]:
                        if cleanup_id:
                            c.execute("DELETE FROM personal_note_revisions WHERE note_id=?", (cleanup_id,))
                            c.execute("DELETE FROM personal_notes WHERE id=?", (cleanup_id,))
                            c.execute("DELETE FROM events WHERE dedup_key=?", (f"note:{cleanup_id}",))
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


def test_tavily_is_paid_fallback_not_core_intelligence_source():
    from leojarvis import reach

    matrix = reach.source_matrix()
    fallback = next(group for group in matrix if "兜底" in group["group"])
    core = next(group for group in matrix if group["group"] == "核心低噪")

    assert "tavily" in fallback["channels"]
    assert "tavily" not in core["channels"]
    assert "不参与默认情报扫描排序" in fallback["use"]


def test_mcp_gateway_status_is_secret_safe(monkeypatch):
    from leojarvis import mcp_gateway

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    status = mcp_gateway.status()

    server_ids = {row["id"] for row in status["servers"]}
    assert {"tavily", "github_mcp", "amap_maps"}.issubset(server_ids)
    assert status["summary"]["total"] >= 3
    assert "api_key" not in str(status)

    reach_channels = {row["id"] for row in mcp_gateway.reach_channels()}
    assert "tavily" in reach_channels

    public = mcp_gateway.public_settings({"servers": {"tavily": {"enabled": True, "api_key": "dummy-secret"}}})
    assert public["servers"]["tavily"]["api_key"] == ""
    assert public["servers"]["tavily"]["key_configured"] is True
