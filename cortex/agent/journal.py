"""Journal：个人日记。日记以 event(source=journal) 形式存储，这里提供读取/检索。"""
from __future__ import annotations

from .. import db


def add_entry(text: str) -> str | None:
    return db.insert_event(source="journal", kind="journal", domain="life",
                           title=text[:40], content=text)


def list_entries(limit: int = 50) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, ts, title, content FROM events WHERE source='journal' ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def search_entries(query: str, limit: int = 50) -> list[dict]:
    like = f"%{query}%"
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, ts, title, content FROM events WHERE source='journal' AND content LIKE ? "
            "ORDER BY ts DESC LIMIT ?",
            (like, limit),
        ).fetchall()
    return [dict(r) for r in rows]
