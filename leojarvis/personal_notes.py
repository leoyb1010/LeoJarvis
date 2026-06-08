from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import db
from .config import DATA_DIR
from .localize import to_chinese


def _tags(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = re.split(r"[\s,，#]+", value)
    if not isinstance(value, list):
        return []
    cleaned = [
        "旧记录" if str(t).strip().lstrip("#") == "旧日记" else str(t).strip().lstrip("#")
        for t in value if str(t).strip()
    ]
    return list(dict.fromkeys(cleaned))[:12]


def _excerpt(content: str, limit: int = 120) -> str:
    compact = " ".join((content or "").split())
    return compact[:limit] or "暂无摘要"


def _title_from(content: str, fallback: str = "未命名记事") -> str:
    first = next((line.strip() for line in (content or "").splitlines() if line.strip()), "")
    return first[:36] or fallback


def _row(row) -> dict:
    item = dict(row)
    item["tags"] = _tags(item.get("tags"))
    item["import_meta"] = _json(item.get("import_meta"), {})
    item["favorite"] = bool(item.get("favorite"))
    item["pinned"] = bool(item.get("pinned"))
    item["archived"] = bool(item.get("archived"))
    return item


def _json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default if default is not None else {}


def migrate_journal_events() -> int:
    """Bring the old Journal event store into the Leonote-like note model."""
    db.init_db()
    migrated = 0
    with db.conn() as c:
        rows = c.execute(
            """
            SELECT id, ts, title, content FROM events
            WHERE source='journal'
              AND id NOT IN (SELECT id FROM personal_notes)
            ORDER BY ts ASC
            """
        ).fetchall()
        for r in rows:
            content = r["content"] or ""
            title = r["title"] or _title_from(content)
            c.execute(
                """INSERT INTO personal_notes(
                     id,title,content,excerpt,tags,source,source_title,import_meta,favorite,pinned,archived,created_ts,updated_ts
                   ) VALUES(?,?,?,?,?,'journal_migration',?,'{}',0,0,0,?,?)""",
                (
                    r["id"],
                    title,
                    content,
                    _excerpt(content),
                    json.dumps(["旧记录"], ensure_ascii=False),
                    title,
                    int(r["ts"]),
                    int(r["ts"]),
                ),
            )
            migrated += 1
    return migrated


def list_notes(q: str = "", tag: str = "", status: str = "active", project: str = "", limit: int = 100) -> list[dict]:
    migrate_journal_events()
    clauses = []
    params: list[Any] = []
    if status == "archived":
        clauses.append("archived=1 AND deleted_ts IS NULL")
    elif status == "all":
        clauses.append("deleted_ts IS NULL")
    else:
        clauses.append("archived=0 AND deleted_ts IS NULL")
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(title LIKE ? OR content LIKE ? OR excerpt LIKE ? OR tags LIKE ?)")
        params.extend([like, like, like, like])
    if tag.strip():
        clauses.append("tags LIKE ?")
        params.append(f"%{tag.strip()}%")
    if project.strip():
        clauses.append("project_name=?")
        params.append(project.strip())
    params.append(max(1, min(limit, 300)))
    with db.conn() as c:
        rows = c.execute(
            f"""
            SELECT * FROM personal_notes
            WHERE {' AND '.join(clauses)}
            ORDER BY pinned DESC, updated_ts DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row(r) for r in rows]


def get_note(note_id: str) -> dict | None:
    migrate_journal_events()
    with db.conn() as c:
        row = c.execute("SELECT * FROM personal_notes WHERE id=? AND deleted_ts IS NULL", (note_id,)).fetchone()
    return _row(row) if row else None


def save_note(data: dict, note_id: str | None = None, reason: str = "save") -> dict:
    migrate_journal_events()
    now = db.now_ms()
    title = str(data.get("title") or "").strip()
    content = str(data.get("content") or "").strip()
    title = title or _title_from(content)
    tags = _tags(data.get("tags", []))
    excerpt = str(data.get("excerpt") or "").strip() or _excerpt(content)
    favorite = 1 if data.get("favorite") else 0
    pinned = 1 if data.get("pinned") else 0
    archived = 1 if data.get("archived") else 0
    source = str(data.get("source") or "manual").strip() or "manual"
    source_url = str(data.get("source_url") or "").strip() or None
    source_title = str(data.get("source_title") or "").strip() or None
    project_name = str(data.get("project_name") or "").strip() or None
    absorbed_from = str(data.get("absorbed_from") or "").strip() or None
    import_meta = data.get("import_meta") if isinstance(data.get("import_meta"), dict) else {}
    created_new = note_id is None

    with db.conn() as c:
        if note_id:
            existing = c.execute("SELECT * FROM personal_notes WHERE id=?", (note_id,)).fetchone()
            if not existing:
                raise KeyError("note not found")
            if existing["title"] != title or existing["content"] != content or existing["excerpt"] != excerpt:
                c.execute(
                    """INSERT INTO personal_note_revisions(id,note_id,title,content,excerpt,reason,created_ts)
                       VALUES(?,?,?,?,?,?,?)""",
                    (uuid.uuid4().hex, note_id, existing["title"], existing["content"], existing["excerpt"], reason, now),
                )
            c.execute(
                """UPDATE personal_notes
                   SET title=?, content=?, excerpt=?, tags=?, source=?, source_url=?, source_title=?,
                       project_name=?, absorbed_from=?, import_meta=?, favorite=?, pinned=?, archived=?, updated_ts=?
                   WHERE id=?""",
                (
                    title, content, excerpt, json.dumps(tags, ensure_ascii=False),
                    source, source_url, source_title,
                    project_name, absorbed_from,
                    json.dumps(import_meta, ensure_ascii=False),
                    favorite, pinned, archived, now, note_id,
                ),
            )
        else:
            note_id = uuid.uuid4().hex
            c.execute(
                """INSERT INTO personal_notes(
                     id,title,content,excerpt,tags,source,source_url,source_title,import_meta,
                     project_name,absorbed_from,favorite,pinned,archived,created_ts,updated_ts
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    note_id, title, content, excerpt, json.dumps(tags, ensure_ascii=False),
                    source, source_url, source_title, json.dumps(import_meta, ensure_ascii=False),
                    project_name, absorbed_from,
                    favorite, pinned, archived, now, now,
                ),
            )
        row = c.execute("SELECT * FROM personal_notes WHERE id=?", (note_id,)).fetchone()
    if created_new:
        db.insert_event(source="personal_note", kind="note", domain="life",
                        title=title, content=content or excerpt, dedup_key=f"note:{note_id}")
    return _row(row)


def delete_note(note_id: str) -> bool:
    with db.conn() as c:
        cur = c.execute("UPDATE personal_notes SET deleted_ts=?, updated_ts=? WHERE id=?", (db.now_ms(), db.now_ms(), note_id))
    return cur.rowcount > 0


def list_revisions(note_id: str) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM personal_note_revisions WHERE note_id=? ORDER BY created_ts DESC LIMIT 20",
            (note_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_attachments(note_id: str) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM personal_note_attachments WHERE note_id=? ORDER BY created_ts DESC",
            (note_id,),
        ).fetchall()
    return [_attachment_row(r) for r in rows]


def _attachment_row(row) -> dict:
    item = dict(row)
    mime = str(item.get("mime_type") or "")
    item["is_image"] = mime.startswith("image/")
    item["url"] = f"/api/personal-notes/attachments/{item['id']}"
    return item


def get_attachment(attachment_id: str) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT * FROM personal_note_attachments WHERE id=?",
            (attachment_id,),
        ).fetchone()
    return _attachment_row(row) if row else None


def attachment_path(attachment: dict) -> Path | None:
    raw = str(attachment.get("path") or "")
    if not raw:
        return None
    path = Path(raw).resolve()
    attachment_root = (DATA_DIR / "attachments").resolve()
    if attachment_root not in path.parents:
        return None
    return path if path.exists() else None


def import_url(url: str) -> dict:
    import httpx
    import trafilatura

    cleaned_url = url.strip()
    if not cleaned_url:
        raise ValueError("url is required")
    if not re.match(r"^https?://", cleaned_url):
        cleaned_url = "https://" + cleaned_url
    with httpx.Client(timeout=15, follow_redirects=True, trust_env=False) as client:
        res = client.get(cleaned_url, headers={"User-Agent": "LeoJarvis-Notes-Importer/0.1"})
        res.raise_for_status()
        html = res.text
    extracted = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    raw_title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else urlparse(cleaned_url).netloc
    title = to_chinese(raw_title, context="链接导入标题", max_chars=80)
    summary_source = extracted[:3000] or raw_title
    summary = to_chinese(summary_source, context="链接导入摘要", max_chars=520)
    content = f"{summary}\n\n来源：{cleaned_url}"
    if extracted:
        content += "\n\n原始摘录：\n" + to_chinese(extracted[:2500], context="链接正文摘录", max_chars=1200)
    note = save_note({
        "title": title,
        "content": content,
        "excerpt": summary,
        "tags": ["链接导入", urlparse(cleaned_url).netloc],
        "source": "link_import",
        "source_url": cleaned_url,
        "source_title": raw_title,
        "import_meta": {"kind": "url", "domain": urlparse(cleaned_url).netloc},
    })
    return note


def attach_file(*, file_name: str, mime_type: str = "", data_base64: str = "",
                note_id: str | None = None, text_content: str = "") -> dict:
    if not file_name.strip():
        raise ValueError("file_name is required")
    now = db.now_ms()
    attach_id = uuid.uuid4().hex
    safe_name = re.sub(r"[^A-Za-z0-9._\-\u3400-\u9fff]+", "_", file_name.strip())[:120]
    attachment_dir = DATA_DIR / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)
    path = attachment_dir / f"{attach_id}-{safe_name}"
    raw = b""
    if data_base64:
        raw = base64.b64decode(data_base64.split(",", 1)[-1])
        path.write_bytes(raw)
    elif text_content:
        raw = text_content.encode("utf-8")
        path.write_text(text_content, encoding="utf-8")
    else:
        path.write_bytes(b"")
    text_summary = ""
    if (mime_type.startswith("text/") or safe_name.lower().endswith((".md", ".txt", ".csv", ".json"))) and raw:
        text_summary = raw[:12000].decode("utf-8", errors="replace")
    elif mime_type == "application/pdf" or safe_name.lower().endswith(".pdf"):
        text_summary = "PDF 附件已保存，当前记录文件元信息。"
    elif mime_type.startswith("image/"):
        text_summary = "图片附件已保存，当前记录文件元信息。"
    else:
        text_summary = "附件已保存，当前记录文件元信息。"
    summary = to_chinese(text_summary, context="附件导入摘要", max_chars=520)
    if not note_id:
        note = save_note({
            "title": f"附件：{safe_name}",
            "content": f"{summary}\n\n附件：{safe_name}",
            "excerpt": summary,
            "tags": ["附件导入", safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else "文件"],
            "source": "attachment_import",
            "source_title": safe_name,
            "import_meta": {"kind": "attachment", "mime_type": mime_type, "size": len(raw)},
        })
        note_id = note["id"]
    with db.conn() as c:
        c.execute(
            """INSERT INTO personal_note_attachments(id,note_id,file_name,mime_type,size,path,summary,created_ts)
               VALUES(?,?,?,?,?,?,?,?)""",
            (attach_id, note_id, safe_name, mime_type, len(raw), str(path), summary, now),
        )
        row = c.execute("SELECT * FROM personal_note_attachments WHERE id=?", (attach_id,)).fetchone()
    return {"note": get_note(note_id), "attachment": _attachment_row(row)}


def note_stats() -> dict:
    migrate_journal_events()
    notes = list_notes(status="all", limit=500)
    tag_counts: dict[str, int] = {}
    for note in notes:
        for tag in note["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:12]
    project_counts: dict[str, int] = {}
    for note in notes:
        project = str(note.get("project_name") or "").strip()
        if project:
            project_counts[project] = project_counts.get(project, 0) + 1
    top_projects = sorted(project_counts.items(), key=lambda x: (-x[1], x[0]))[:12]
    return {
        "total": len(notes),
        "favorite": sum(1 for n in notes if n["favorite"]),
        "pinned": sum(1 for n in notes if n["pinned"]),
        "archived": sum(1 for n in notes if n["archived"]),
        "tags": [{"tag": tag, "count": count} for tag, count in top_tags],
        "projects": [{"name": name, "count": count} for name, count in top_projects],
        "recent": notes[:8],
    }
