"""版本化文档(D)。清室重写,设计借鉴 odysseus 的 documents + version history + FIND/REPLACE 编辑工具,
代码全新、无 AGPL 牵连。

精简版:不做完整富文本编辑器,只做「数据模型 + 版本化 + agent 可编辑」:
  - create/get/list/list_versions
  - edit_replace(find, replace):字面 FIND/REPLACE;写前把旧内容快照进 document_versions(仿 personal_notes)。
  - set_content:整篇替换(也版本化)。
agent 工具 edit_document 挂到 TOOLBUS(gate=confirm),让 agent 能在确认下改文档。
"""

from __future__ import annotations

import json
import uuid

from . import db


def _row(r) -> dict:
    d = dict(r)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except Exception:
        d["tags"] = []
    return d


def create(title: str, content: str = "", *, kind: str = "doc", tags: list[str] | None = None) -> dict:
    db.init_db()
    did = uuid.uuid4().hex
    now = db.now_ms()
    with db.conn() as c:
        c.execute("INSERT INTO documents(id,title,content,kind,tags,created_ts,updated_ts) VALUES(?,?,?,?,?,?,?)",
                  (did, title.strip() or "未命名文档", content, kind, json.dumps(tags or [], ensure_ascii=False), now, now))
    return get(did)


def get(doc_id: str) -> dict | None:
    db.init_db()
    with db.conn() as c:
        r = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row(r) if r else None


def list_docs(limit: int = 100) -> list[dict]:
    db.init_db()
    with db.conn() as c:
        rows = c.execute("SELECT id,title,kind,tags,updated_ts FROM documents ORDER BY updated_ts DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def list_versions(doc_id: str, limit: int = 50) -> list[dict]:
    db.init_db()
    with db.conn() as c:
        rows = c.execute("SELECT id,reason,created_ts FROM document_versions WHERE document_id=? ORDER BY created_ts DESC LIMIT ?",
                         (doc_id, limit)).fetchall()
    return [dict(r) for r in rows]


def _snapshot(c, doc_id: str, old_content: str, reason: str) -> None:
    """把旧内容快照进 document_versions(写前调用,和 personal_notes 同序)。"""
    c.execute("INSERT INTO document_versions(id,document_id,content,reason,created_ts) VALUES(?,?,?,?,?)",
              (uuid.uuid4().hex, doc_id, old_content, reason, db.now_ms()))


def set_content(doc_id: str, content: str, *, reason: str = "edit") -> dict:
    db.init_db()
    with db.conn() as c:
        r = c.execute("SELECT content FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not r:
            return {"ok": False, "error": "文档不存在"}
        _snapshot(c, doc_id, r["content"], reason)
        c.execute("UPDATE documents SET content=?, updated_ts=? WHERE id=?", (content, db.now_ms(), doc_id))
    return {"ok": True, "document": get(doc_id)}


def edit_replace(doc_id: str, find: str, replace: str, *, count: int = 0, reason: str = "edit") -> dict:
    """字面 FIND/REPLACE。find 不存在 → 不改、不建版本,返回结构化错误。count=0 表示全替换。"""
    db.init_db()
    if not find:
        return {"ok": False, "error": "find 不能为空"}
    with db.conn() as c:
        r = c.execute("SELECT content FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not r:
            return {"ok": False, "error": "文档不存在"}
        old = r["content"] or ""
        if find not in old:
            return {"ok": False, "error": "find 字符串在文档中不存在", "replaced": 0}
        n = old.count(find) if count <= 0 else min(count, old.count(find))
        new = old.replace(find, replace, n if count > 0 else -1)
        _snapshot(c, doc_id, old, reason)
        c.execute("UPDATE documents SET content=?, updated_ts=? WHERE id=?", (new, db.now_ms(), doc_id))
    return {"ok": True, "replaced": n, "document": get(doc_id)}


def edit_document_tool(args: dict) -> str:
    """agent 工具入口:{doc_id, find, replace} → edit_replace。"""
    doc_id = str(args.get("doc_id") or args.get("id") or "").strip()
    find = str(args.get("find") or "")
    replace = str(args.get("replace") or "")
    if not doc_id:
        return "缺少 doc_id"
    res = edit_replace(doc_id, find, replace, reason="agent")
    if not res.get("ok"):
        return f"编辑失败:{res.get('error')}"
    return f"已替换 {res['replaced']} 处,文档已更新(旧版本已存档)。"
