"""Personal Notes：个人记事。兼容旧 Journal API。"""
from __future__ import annotations

from .. import personal_notes


def add_entry(text: str) -> str | None:
    note = personal_notes.save_note({"content": text, "tags": ["随手记"]})
    return note["id"]


def list_entries(limit: int = 50) -> list[dict]:
    rows = personal_notes.list_notes(limit=limit)
    return [
        {"id": r["id"], "ts": r["updated_ts"], "title": r["title"], "content": r["content"]}
        for r in rows
    ]


def search_entries(query: str, limit: int = 50) -> list[dict]:
    rows = personal_notes.list_notes(q=query, limit=limit)
    return [
        {"id": r["id"], "ts": r["updated_ts"], "title": r["title"], "content": r["content"]}
        for r in rows
    ]
