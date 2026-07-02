"""V4 审计账本契约测试。

账本是可信执行层的地基：每个工具调用必须留痕(做了什么/风险/状态/是否人确认/可逆性)，
且写账本绝不能打断主流程。以下把这些不变量固化为回归。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from leojarvis import db
from leojarvis.agent import audit, loop
from leojarvis.main import app


def test_insert_and_list_audit_log_roundtrip():
    db.init_db()
    aid = db.insert_audit_log(tool="system_status", status="auto", args={"x": 1},
                              output_summary="ok", risk="auto", duration_ms=12)
    assert aid
    rows = db.list_audit_logs(limit=10)
    got = [r for r in rows if r["id"] == aid]
    assert got, "刚写的审计记录没查到"
    r = dict(got[0])
    assert r["tool"] == "system_status" and r["status"] == "auto" and r["risk"] == "auto"
    assert r["duration_ms"] == 12


def test_audit_filters_by_tool_status_risk():
    db.init_db()
    db.insert_audit_log(tool="run_shell", status="denied", args={"command": "rm -rf /"},
                        output_summary="拒绝", risk="deny")
    db.insert_audit_log(tool="recall_memory", status="auto", args={}, risk="auto")
    denied = db.list_audit_logs(status="denied", limit=50)
    assert all(dict(r)["status"] == "denied" for r in denied)
    assert any(dict(r)["tool"] == "run_shell" for r in denied)
    shells = db.list_audit_logs(tool="run_shell", limit=50)
    assert all(dict(r)["tool"] == "run_shell" for r in shells)


def test_reversible_defaults_by_tool():
    """写类工具(run_shell/restart_service…)默认不可逆；只读/草稿默认可逆。"""
    db.init_db()
    a1 = db.get_audit_log(audit.record(tool="run_shell", args={"command": "ls"},
                                       result="x", status="approved"))
    a2 = db.get_audit_log(audit.record(tool="recall_memory", args={}, result="x", status="auto"))
    assert dict(a1)["reversible"] == 0, "run_shell 应默认不可逆"
    assert dict(a2)["reversible"] == 1, "recall_memory 应默认可逆"


def test_audit_record_never_raises_on_failure(monkeypatch):
    """审计写入失败必须被吞掉，绝不打断主流程。"""
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "insert_audit_log", boom)
    # 不应抛异常，返回 None
    assert audit.record(tool="system_status", args={}, result="x", status="auto") is None


def test_log_action_writes_ledger():
    """loop._log_action 既写台账事件，也写审计账本。"""
    db.init_db()
    before = db.count_audit_logs(tool="system_status")
    loop._log_action("system_status", {"probe": 1}, "结果", "auto", risk="auto", duration_ms=5)
    after = db.count_audit_logs(tool="system_status")
    assert after == before + 1, "._log_action 未写入审计账本"


def test_denied_action_is_audited():
    """被闸门拒绝的动作也必须留痕(risk=deny, status=denied)。"""
    db.init_db()
    loop._log_action("run_shell", {"command": "mkfs /dev/disk0"}, "⛔ 拒绝", "denied", risk="deny")
    rows = db.list_audit_logs(status="denied", tool="run_shell", limit=20)
    assert any(dict(r)["risk"] == "deny" for r in rows)


def test_audit_logs_api_pagination_and_filter():
    db.init_db()
    for i in range(3):
        db.insert_audit_log(tool="intelligence_scan", status="auto", args={"i": i}, risk="auto")
    with TestClient(app) as client:
        res = client.get("/audit/logs", params={"tool": "intelligence_scan", "limit": 2})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["total"] >= 3
    assert len(body["items"]) == 2
    assert all(it["tool"] == "intelligence_scan" for it in body["items"])
    assert {"id", "ts", "tool", "status", "risk", "reversible"} <= set(body["items"][0])


def test_prune_removes_old_audit_logs():
    """保留窗口：event_days 之前的审计记录应被 prune 掉。"""
    db.init_db()
    old_id = db.insert_audit_log(tool="system_status", status="auto", args={}, risk="auto")
    # 手动把这条时间戳改到 200 天前
    with db.conn() as c:
        c.execute("UPDATE audit_logs SET ts=? WHERE id=?",
                  (db.now_ms() - 200 * 86_400_000, old_id))
    removed = db.prune_old_data(event_days=90)
    assert removed.get("audit_logs", 0) >= 1
    assert db.get_audit_log(old_id) is None
