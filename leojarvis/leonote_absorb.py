from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db
from .config import DATA_DIR, ROOT


def _candidate_paths() -> list[Path]:
    raw: list[str] = []
    if os.environ.get("LEONOTE_DB_PATH"):
        raw.append(os.environ["LEONOTE_DB_PATH"])
    raw.extend([
        "~/Desktop/leoworkspace/leonote/data/leonote.db",
        "~/Desktop/leoworkspace/leonote/prisma/data/leonote.db",
        "~/leonote/data/leonote.db",
        "~/leonote/prisma/data/leonote.db",
        str(ROOT.parent / "leonote" / "data" / "leonote.db"),
        str(ROOT.parent / "leonote" / "prisma" / "data" / "leonote.db"),
    ])
    paths: list[Path] = []
    seen: set[str] = set()
    for item in raw:
        path = Path(item).expanduser().resolve()
        key = str(path)
        if key not in seen:
            seen.add(key)
            paths.append(path)
    return paths


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _count(conn: sqlite3.Connection, table: str, where: str = "") -> int:
    if not _table_exists(conn, table):
        return 0
    clause = f" WHERE {where}" if where else ""
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}{clause}").fetchone()[0] or 0)


def inspect_sources(paths: list[str] | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in [Path(p).expanduser().resolve() for p in paths or []] or _candidate_paths():
        item: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "valid": False,
            "note_count": 0,
            "active_note_count": 0,
            "project_count": 0,
            "tag_count": 0,
            "attachment_count": 0,
            "revision_count": 0,
            "latest_note_updated_at": "",
            "message": "",
        }
        if not path.exists():
            item["message"] = "文件不存在"
            rows.append(item)
            continue
        try:
            with _connect_readonly(path) as conn:
                if not _table_exists(conn, "Note"):
                    item["message"] = "不是 Leonote 数据库：缺少 Note 表"
                    rows.append(item)
                    continue
                note_cols = _columns(conn, "Note")
                deleted_filter = "deletedAt IS NULL" if "deletedAt" in note_cols else ""
                item.update({
                    "valid": True,
                    "note_count": _count(conn, "Note"),
                    "active_note_count": _count(conn, "Note", deleted_filter),
                    "project_count": _count(conn, "Project"),
                    "tag_count": _count(conn, "Tag"),
                    "attachment_count": _count(conn, "NoteAttachment"),
                    "revision_count": _count(conn, "NoteRevision"),
                    "latest_note_updated_at": _latest_note_update(conn),
                    "message": "可吸收" if _count(conn, "Note", deleted_filter) else "库可读，但没有有效笔记",
                })
        except Exception as exc:  # noqa: BLE001
            item["message"] = str(exc)[:180]
        rows.append(item)
    best = next((row for row in rows if row["valid"] and row["active_note_count"] > 0), None)
    return {"ok": True, "sources": rows, "best": best}


def _latest_note_update(conn: sqlite3.Connection) -> str:
    if not _table_exists(conn, "Note"):
        return ""
    cols = _columns(conn, "Note")
    if "updatedAt" not in cols:
        return ""
    row = conn.execute("SELECT MAX(updatedAt) AS value FROM Note").fetchone()
    return str(row["value"] or "") if row else ""


def absorb(path: str = "", dry_run: bool = False, limit: int = 0) -> dict[str, Any]:
    source = _choose_source(path)
    if not source:
        inspected = inspect_sources([path] if path else None)
        return {"ok": False, "message": "没有找到包含有效笔记的 Leonote 数据库", **inspected}

    db.init_db()
    summary = {
        "ok": True,
        "dry_run": dry_run,
        "source_path": str(source),
        "scanned": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "attachments": 0,
        "revisions": 0,
        "errors": [],
    }
    with _connect_readonly(source) as src:
        for row in _note_rows(src, limit=limit):
            summary["scanned"] += 1
            try:
                outcome = _absorb_note(src, source, row, dry_run=dry_run)
                summary[outcome["status"]] += 1
                summary["attachments"] += outcome.get("attachments", 0)
                summary["revisions"] += outcome.get("revisions", 0)
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append({"note_id": row["id"], "error": str(exc)[:180]})
    summary["ok"] = len(summary["errors"]) == 0
    return summary


def _choose_source(path: str = "") -> Path | None:
    candidates = [Path(path).expanduser().resolve()] if path else _candidate_paths()
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            with _connect_readonly(candidate) as conn:
                if not _table_exists(conn, "Note"):
                    continue
                note_cols = _columns(conn, "Note")
                if "deletedAt" in note_cols and _count(conn, "Note", "deletedAt IS NULL") > 0:
                    return candidate
                if "deletedAt" not in note_cols and _count(conn, "Note") > 0:
                    return candidate
        except Exception:
            continue
    return None


def _note_rows(conn: sqlite3.Connection, limit: int = 0) -> list[sqlite3.Row]:
    note_cols = _columns(conn, "Note")
    project_join = "LEFT JOIN Project p ON p.id = n.projectId" if _table_exists(conn, "Project") and "projectId" in note_cols else ""
    project_select = "p.name AS project_name" if project_join else "NULL AS project_name"
    where = "WHERE n.deletedAt IS NULL" if "deletedAt" in note_cols else ""
    limit_clause = f" LIMIT {max(1, int(limit))}" if limit else ""
    return conn.execute(
        f"""
        SELECT n.*, {project_select}
        FROM Note n
        {project_join}
        {where}
        ORDER BY n.updatedAt DESC
        {limit_clause}
        """
    ).fetchall()


def _absorb_note(src: sqlite3.Connection, source_db: Path, row: sqlite3.Row, *, dry_run: bool) -> dict[str, Any]:
    source_url = f"leonote://{row['id']}"
    source_updated = _to_ms(row["updatedAt"])
    created_ts = _to_ms(row["createdAt"])
    tags = _note_tags(src, row["id"])
    project_name = str(row["project_name"] or "").strip()
    if project_name and project_name not in tags:
        tags.append(project_name)
    import_meta = {
        "kind": "leonote_absorb",
        "leonote_id": row["id"],
        "source_db": str(source_db),
        "leonote_created_at": str(row["createdAt"] or ""),
        "leonote_updated_at": str(row["updatedAt"] or ""),
        "project_name": project_name,
    }
    payload = {
        "title": str(row["title"] or "").strip() or "未命名笔记",
        "content": str(row["content"] or ""),
        "excerpt": str(row["excerpt"] or "") or _excerpt(str(row["content"] or "")),
        "tags": tags,
        "source": "leonote_absorb",
        "source_url": source_url,
        "source_title": "Leonote",
        "project_name": project_name,
        "absorbed_from": str(source_db),
        "import_meta": import_meta,
        "favorite": bool(row["isFavorite"] if "isFavorite" in row.keys() else False),
        "pinned": bool(row["isPinned"] if "isPinned" in row.keys() else False),
        "archived": bool(row["isArchived"] if "isArchived" in row.keys() else False),
        "created_ts": created_ts,
        "updated_ts": source_updated,
    }
    with db.conn() as dst:
        existing = dst.execute(
            "SELECT id, updated_ts FROM personal_notes WHERE source='leonote_absorb' AND source_url=?",
            (source_url,),
        ).fetchone()
        if dry_run:
            return {"status": "skipped" if existing else "created", "attachments": 0, "revisions": 0}
        if existing:
            note_id = existing["id"]
            if int(existing["updated_ts"] or 0) > source_updated:
                return {"status": "skipped", "attachments": 0, "revisions": 0}
            dst.execute(
                """UPDATE personal_notes
                   SET title=?, content=?, excerpt=?, tags=?, source_url=?, source_title=?,
                       project_name=?, absorbed_from=?, import_meta=?, favorite=?, pinned=?,
                       archived=?, updated_ts=?
                   WHERE id=?""",
                (
                    payload["title"], payload["content"], payload["excerpt"], json.dumps(tags, ensure_ascii=False),
                    source_url, payload["source_title"], project_name, payload["absorbed_from"],
                    json.dumps(import_meta, ensure_ascii=False), int(payload["favorite"]), int(payload["pinned"]),
                    int(payload["archived"]), source_updated, note_id,
                ),
            )
            status = "updated"
        else:
            note_id = uuid.uuid4().hex
            dst.execute(
                """INSERT INTO personal_notes(
                     id,title,content,excerpt,tags,source,source_url,source_title,project_name,absorbed_from,
                     import_meta,favorite,pinned,archived,created_ts,updated_ts
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    note_id, payload["title"], payload["content"], payload["excerpt"],
                    json.dumps(tags, ensure_ascii=False), payload["source"], source_url,
                    payload["source_title"], project_name, payload["absorbed_from"],
                    json.dumps(import_meta, ensure_ascii=False), int(payload["favorite"]), int(payload["pinned"]),
                    int(payload["archived"]), created_ts, source_updated,
                ),
            )
            status = "created"
        attachments = _copy_attachments(src, dst, source_db, row["id"], note_id)
        revisions = _copy_revisions(src, dst, row["id"], note_id)
    return {"status": status, "attachments": attachments, "revisions": revisions}


def _note_tags(conn: sqlite3.Connection, note_id: str) -> list[str]:
    if not (_table_exists(conn, "NoteTag") and _table_exists(conn, "Tag")):
        return []
    rows = conn.execute(
        """
        SELECT t.name FROM NoteTag nt
        JOIN Tag t ON t.id = nt.tagId
        WHERE nt.noteId=?
        ORDER BY t.name
        """,
        (note_id,),
    ).fetchall()
    tags = [str(row["name"]).strip().lstrip("#") for row in rows if str(row["name"] or "").strip()]
    return list(dict.fromkeys(tags))[:12]


def _copy_attachments(src: sqlite3.Connection, dst: sqlite3.Connection, source_db: Path, source_note_id: str, note_id: str) -> int:
    if not _table_exists(src, "NoteAttachment"):
        return 0
    rows = src.execute("SELECT * FROM NoteAttachment WHERE noteId=? ORDER BY createdAt ASC", (source_note_id,)).fetchall()
    count = 0
    root = source_db.parent
    attachment_dir = DATA_DIR / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        filename = _safe_name(str(row["filename"] or row["id"] or "attachment"))
        size = int(row["size"] or 0)
        exists = dst.execute(
            "SELECT 1 FROM personal_note_attachments WHERE note_id=? AND file_name=? AND size=?",
            (note_id, filename, size),
        ).fetchone()
        if exists:
            continue
        storage_path = str(row["storagePath"] or "")
        source_path = (root / "attachments" / storage_path).resolve()
        target_id = uuid.uuid4().hex
        target_path = attachment_dir / f"{target_id}-{filename}"
        if source_path.exists() and source_path.is_file():
            shutil.copyfile(source_path, target_path)
        else:
            target_path.write_bytes(b"")
        dst.execute(
            """INSERT INTO personal_note_attachments(id,note_id,file_name,mime_type,size,path,summary,created_ts)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                target_id, note_id, filename, str(row["mimeType"] or ""), size, str(target_path),
                "从 Leonote 吸收的附件。" if source_path.exists() else "Leonote 附件元信息已吸收，源文件未找到。",
                _to_ms(row["createdAt"]),
            ),
        )
        count += 1
    return count


def _copy_revisions(src: sqlite3.Connection, dst: sqlite3.Connection, source_note_id: str, note_id: str) -> int:
    if not _table_exists(src, "NoteRevision"):
        return 0
    rows = src.execute("SELECT * FROM NoteRevision WHERE noteId=? ORDER BY createdAt ASC", (source_note_id,)).fetchall()
    count = 0
    for row in rows:
        created_ts = _to_ms(row["createdAt"])
        exists = dst.execute(
            """SELECT 1 FROM personal_note_revisions
               WHERE note_id=? AND created_ts=? AND title=?""",
            (note_id, created_ts, str(row["title"] or "")),
        ).fetchone()
        if exists:
            continue
        dst.execute(
            """INSERT INTO personal_note_revisions(id,note_id,title,content,excerpt,reason,created_ts)
               VALUES(?,?,?,?,?,?,?)""",
            (
                uuid.uuid4().hex, note_id, str(row["title"] or ""), str(row["content"] or ""),
                str(row["excerpt"] or ""), f"leonote:{row['reason'] if 'reason' in row.keys() else 'revision'}",
                created_ts,
            ),
        )
        count += 1
    return count


def _to_ms(value: Any) -> int:
    if value is None:
        return db.now_ms()
    if isinstance(value, (int, float)):
        raw = int(value)
        return raw if raw > 10_000_000_000 else raw * 1000
    text = str(value).strip()
    if not text:
        return db.now_ms()
    if text.isdigit():
        return _to_ms(int(text))
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return db.now_ms()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-\u3400-\u9fff]+", "_", value.strip())[:120] or "attachment"


def _excerpt(content: str, limit: int = 140) -> str:
    return " ".join(content.split())[:limit]
