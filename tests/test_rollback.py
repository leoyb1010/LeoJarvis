"""V4 一键回滚契约测试。

核心闭环：可逆动作(文档编辑)在审计账本里带 undo_ref → 一键 undo 能还原；
不可逆动作(run_shell 等)不可回滚；shell 反向命令只提示不自动执行(安全红线)。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from leojarvis import db, documents
from leojarvis.agent import audit, rollback
from leojarvis.main import app


def test_document_edit_is_reversible_end_to_end():
    db.init_db()
    doc = documents.create("回滚测试文档", "原始内容 ABC")
    did = doc["id"]
    # 编辑
    res = documents.edit_replace(did, "ABC", "XYZ", reason="test")
    assert res["ok"] and documents.get(did)["content"] == "原始内容 XYZ"
    # 审计这次编辑（模拟 loop._log_action 的调用），应自动派生 doc: undo_ref
    aid = audit.record(tool="edit_document", args={"doc_id": did, "find": "ABC", "replace": "XYZ"},
                       result="已替换 1 处,文档已更新(旧版本已存档)。", status="auto")
    row = dict(db.get_audit_log(aid))
    assert row["reversible"] == 1
    assert row["undo_ref"] == f"doc:{did}"
    # 一键回滚 → 还原
    r = rollback.undo(aid)
    assert r["ok"] and r["undone"] is True
    assert documents.get(did)["content"] == "原始内容 ABC", "回滚未还原内容"


def test_irreversible_action_cannot_undo():
    db.init_db()
    aid = audit.record(tool="run_shell", args={"command": "rm x"}, result="done", status="approved")
    r = rollback.undo(aid)
    assert r["ok"] is False and "不可回滚" in r["error"]


def test_shell_reverse_command_is_hint_not_executed():
    """shell 反向命令只返回提示，绝不自动执行（安全红线）。"""
    db.init_db()
    aid = audit.record(tool="run_shell", args={"command": "mkdir /tmp/x"}, result="done",
                       status="approved", reversible=True,
                       undo_ref=rollback.make_shell_undo_ref("rmdir /tmp/x"))
    r = rollback.undo(aid)
    assert r["ok"] is True and r["undone"] is False
    assert r["kind"] == "shell_hint" and r["reverse_command"] == "rmdir /tmp/x"


def test_undo_nonexistent_audit():
    db.init_db()
    r = rollback.undo("nope-does-not-exist")
    assert r["ok"] is False


def test_undo_is_itself_audited():
    """回滚动作本身要留痕。"""
    db.init_db()
    doc = documents.create("留痕测试", "AAA")
    documents.edit_replace(doc["id"], "AAA", "BBB")
    aid = audit.record(tool="edit_document", args={"doc_id": doc["id"]},
                       result="已替换 1 处", status="auto")
    before = db.count_audit_logs(tool="rollback")
    rollback.undo(aid)
    assert db.count_audit_logs(tool="rollback") == before + 1


def test_undo_api():
    db.init_db()
    doc = documents.create("API 回滚", "hello")
    documents.edit_replace(doc["id"], "hello", "world")
    aid = audit.record(tool="edit_document", args={"doc_id": doc["id"]},
                       result="已替换 1 处", status="auto")
    with TestClient(app) as client:
        res = client.post(f"/audit/{aid}/undo")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert documents.get(doc["id"])["content"] == "hello"
