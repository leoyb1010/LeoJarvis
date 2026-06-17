from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import db
from .config import DATA_DIR, LEGACY_DATA_DIR
from .localize import to_chinese

_SENSITIVE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:api[_-]?key|token|secret|password|passwd|pwd)\b", re.I),
    re.compile(r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
]


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


def normalize_markdown_content(content: str) -> str:
    """Normalize pasted Markdown without changing the user's facts or wording."""
    text = str(content or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    stripped = text.strip()
    fenced = re.match(r"^```(?:markdown|md)?\s*\n(?P<body>.*)\n```$", stripped, flags=re.I | re.S)
    if fenced:
        text = fenced.group("body")
    # Some sources paste literal "\n" sequences instead of real line breaks.
    if text.count("\\n") >= 2 and text.count("\n") <= 1:
        text = text.replace("\\n", "\n")
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"(?m)^\s*([*+-])\s{2,}", r"\1 ", text)
    text = re.sub(r"(?m)^(\s*\d+\.)\s{2,}", r"\1 ", text)
    return text.strip()


def _plain_title(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^#{1,6}\s+", "", value)
    value = re.sub(r"^\s*[-*+]\s+", "", value)
    value = re.sub(r"^\s*\d+\.\s+", "", value)
    value = re.sub(r"[*_`~]+", "", value)
    return value.strip()


def _json_object_from_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip().strip("`")
    raw = re.sub(r"^json\s*", "", raw, flags=re.I).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def draft_from_natural_language(prompt: str, *, project_name: str = "") -> dict[str, Any]:
    """Turn a user's own natural-language note into an editable note draft.

    The model is instructed to preserve facts only. If LLM routing is unavailable,
    return a deterministic draft instead of blocking note creation.
    """
    text = str(prompt or "").strip()
    if not text:
        return {"title": "", "content": "", "tags": [], "project_name": project_name.strip()}
    fallback = {
        "title": _title_from(text),
        "content": text,
        "tags": [],
        "project_name": project_name.strip(),
    }
    try:
        from .models_router import chat
        raw = chat("default", [
            {
                "role": "system",
                "content": (
                    "你是 LeoJarvis 的个人记事整理器。把用户自己的输入整理为可编辑笔记草稿。"
                    "必须保留原始事实，不添加不存在的信息，不做外部知识补充，不替用户下结论。"
                    "输出 JSON 对象，字段必须是 title、content、tags、project_name。"
                    "content 用简体中文 Markdown，结构清晰但不要冗长；tags 最多 6 个短标签。"
                ),
            },
            {
                "role": "user",
                "content": f"默认项目：{project_name.strip() or '无'}\n原始输入：\n{text[:4000]}",
            },
        ], temperature=0.2)
        parsed = _json_object_from_text(raw)
        title = str(parsed.get("title") or fallback["title"]).strip()[:80]
        content = str(parsed.get("content") or fallback["content"]).strip()
        tags = _tags(parsed.get("tags") or [])
        project = str(parsed.get("project_name") or fallback["project_name"]).strip()
        return {
            "title": title or fallback["title"],
            "content": content or fallback["content"],
            "tags": tags,
            "project_name": project,
        }
    except Exception:
        return fallback


_TRANSFORM_TEMPLATES: dict[str, dict[str, str]] = {
    "summary": {
        "label": "摘要",
        "tag": "摘要",
        "prompt": (
            "把这条笔记整理成可复用的中文 Markdown 摘要。结构必须包含："
            "## 核心结论、## 关键信息、## 可引用细节。只使用原文事实，不添加外部信息。"
        ),
    },
    "key_points": {
        "label": "要点",
        "tag": "要点",
        "prompt": (
            "从这条笔记中提取关键概念和关键事实，输出中文 Markdown。"
            "结构必须包含：## 关键概念、## 关键事实、## 需要保留的原文线索。不要编造。"
        ),
    },
    "actions": {
        "label": "行动项",
        "tag": "行动项",
        "prompt": (
            "从这条笔记中提取下一步行动，输出中文 Markdown。"
            "结构必须包含：## 可执行事项、## 依赖信息、## 风险与待确认。没有明确行动就写“原文未给出”。"
        ),
    },
    "questions": {
        "label": "问题",
        "tag": "问题",
        "prompt": (
            "基于这条笔记生成后续研究问题，输出中文 Markdown。"
            "结构必须包含：## 需要追问、## 需要补充的资料源、## 可验证假设。不要添加新事实。"
        ),
    },
}


def _fallback_transform(note: dict, template: dict[str, str]) -> str:
    body = normalize_markdown_content(note.get("content") or note.get("excerpt") or "")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    bullets = "\n".join(f"- {line[:180]}" for line in lines[:8])
    if not bullets:
        bullets = "- 原笔记暂无可整理正文。"
    return f"## {template['label']}\n\n{bullets}"


def transform_note(note_id: str, template_key: str = "summary") -> dict[str, Any]:
    note = get_note(note_id)
    if not note:
        raise KeyError("note not found")
    template = _TRANSFORM_TEMPLATES.get(template_key) or _TRANSFORM_TEMPLATES["summary"]
    content = note.get("content") or note.get("excerpt") or ""
    result = ""
    try:
        from .models_router import chat
        result = chat("default", [
            {
                "role": "system",
                "content": (
                    "你是 LeoJarvis 的研究笔记整理器。你只能基于用户给出的笔记内容整理。"
                    "必须使用简体中文 Markdown；不得添加来源中没有的事实；不得泄露或扩写密钥。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"任务：{template['prompt']}\n"
                    f"原笔记标题：{note.get('title') or ''}\n"
                    f"原笔记项目：{note.get('project_name') or ''}\n"
                    f"原笔记内容：\n{content[:7000]}"
                ),
            },
        ], temperature=0.2)
        result = normalize_markdown_content(result)
    except Exception:
        result = ""
    if not result:
        result = _fallback_transform(note, template)
    tags = list(dict.fromkeys(["AI整理", template["tag"], *note.get("tags", [])]))[:12]
    new_note = save_note({
        "title": f"{template['label']}：{note.get('title') or _title_from(content)}",
        "content": result,
        "excerpt": _excerpt(result),
        "tags": tags,
        "project_name": note.get("project_name") or "",
        "source": "ai_transform",
        "source_title": note.get("title") or "",
        "source_url": note.get("source_url") or "",
        "import_meta": {
            "kind": "note_transformation",
            "template": template_key,
            "source_note_id": note_id,
        },
        "favorite": False,
        "pinned": False,
        "archived": False,
    }, reason=f"transform:{template_key}")
    return {"note": new_note, "template": template_key}


def is_sensitive_text(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _SENSITIVE_PATTERNS)


def _redact_sensitive(text: str, limit: int = 160) -> str:
    compact = " ".join((text or "").split())
    compact = re.sub(
        r"(?i)\b(api[_\s-]?key|token\s*key|secret|password|passwd|pwd)\b\s*[:=：]\s*\S+",
        lambda m: f"{m.group(1)}：••••••",
        compact,
    )
    compact = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[已隐藏密钥]", compact)
    return compact[:limit] or "暂无摘要"


def _title_from(content: str, fallback: str = "未命名记事") -> str:
    first = next((line.strip() for line in (content or "").splitlines() if line.strip()), "")
    return _plain_title(first)[:36] or fallback


def _row(row) -> dict:
    item = dict(row)
    item["tags"] = _tags(item.get("tags"))
    item["import_meta"] = _json(item.get("import_meta"), {})
    item["favorite"] = bool(item.get("favorite"))
    item["pinned"] = bool(item.get("pinned"))
    item["archived"] = bool(item.get("archived"))
    item["sensitive"] = is_sensitive_text(f"{item.get('title') or ''}\n{item.get('content') or ''}\n{item.get('tags') or ''}")
    item["safe_excerpt"] = _redact_sensitive(item.get("excerpt") or item.get("content") or "") if item["sensitive"] else item.get("excerpt")
    return item


def _json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default if default is not None else {}


def migrate_journal_events() -> int:
    """Bring the old Journal event store into the Jarvis note model."""
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


def _compact_note(item: dict) -> dict:
    compact = {
        key: item.get(key)
        for key in (
            "id", "title", "excerpt", "safe_excerpt", "tags", "source", "source_url", "source_title",
            "favorite", "pinned", "archived", "deleted_ts", "created_ts", "updated_ts", "project_name",
            "sensitive",
        )
    }
    if compact.get("sensitive") and compact.get("safe_excerpt"):
        compact["excerpt"] = compact["safe_excerpt"]
    return compact


def list_notes(
    q: str = "",
    tag: str = "",
    status: str = "active",
    project: str = "",
    limit: int = 100,
    compact: bool = False,
) -> list[dict]:
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
    notes = [_row(r) for r in rows]
    return [_compact_note(item) for item in notes] if compact else notes


def get_note(note_id: str) -> dict | None:
    migrate_journal_events()
    with db.conn() as c:
        row = c.execute("SELECT * FROM personal_notes WHERE id=? AND deleted_ts IS NULL", (note_id,)).fetchone()
    return _row(row) if row else None


def save_note(data: dict, note_id: str | None = None, reason: str = "save") -> dict:
    migrate_journal_events()
    now = db.now_ms()
    title = str(data.get("title") or "").strip()
    content = normalize_markdown_content(str(data.get("content") or ""))
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
                       project_name=?, import_meta=?, favorite=?, pinned=?, archived=?, updated_ts=?
                   WHERE id=?""",
                (
                    title, content, excerpt, json.dumps(tags, ensure_ascii=False),
                    source, source_url, source_title,
                    project_name, json.dumps(import_meta, ensure_ascii=False),
                    favorite, pinned, archived, now, note_id,
                ),
            )
        else:
            note_id = uuid.uuid4().hex
            c.execute(
                """INSERT INTO personal_notes(
                     id,title,content,excerpt,tags,source,source_url,source_title,import_meta,
                     project_name,favorite,pinned,archived,created_ts,updated_ts
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    note_id, title, content, excerpt, json.dumps(tags, ensure_ascii=False),
                    source, source_url, source_title, json.dumps(import_meta, ensure_ascii=False),
                    project_name, favorite, pinned, archived, now, now,
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
    # 容忍新旧两个 attachments 根：数据目录搬到 Application Support 后，DB 里历史绝对路径
    # 仍指向旧位（仓库内 data/attachments），文件也还在那（迁移是复制不删），照样能解析。
    roots = [(DATA_DIR / "attachments").resolve(), (LEGACY_DATA_DIR / "attachments").resolve()]
    if not any(r in path.parents for r in roots):
        return None
    return path if path.exists() else None


def import_url(url: str, notebook: str = "") -> dict:
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
        "project_name": (notebook or "").strip(),
        "import_meta": {"kind": "url", "domain": urlparse(cleaned_url).netloc, "role": "source"},
    })
    return note


def attach_file(*, file_name: str, mime_type: str = "", data_base64: str = "",
                note_id: str | None = None, text_content: str = "", notebook: str = "") -> dict:
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
            "project_name": (notebook or "").strip(),
            "import_meta": {"kind": "attachment", "mime_type": mime_type, "size": len(raw), "role": "source"},
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
    recent = [_compact_note(note) for note in notes[:8]]
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
        "recent": recent,
    }


def notebook_overview() -> dict:
    migrate_journal_events()
    notes = list_notes(status="all", limit=500)
    buckets: dict[str, dict[str, Any]] = {}
    for note in notes:
        name = str(note.get("project_name") or "").strip() or "未归档"
        bucket = buckets.setdefault(name, {
            "name": name,
            "description": "Jarvis 个人记事项目空间",
            "note_count": 0,
            "source_count": 0,
            "favorite": 0,
            "pinned": 0,
            "updated_ts": 0,
            "tags": {},
            "recent": [],
        })
        bucket["note_count"] += 1
        bucket["favorite"] += 1 if note.get("favorite") else 0
        bucket["pinned"] += 1 if note.get("pinned") else 0
        bucket["updated_ts"] = max(int(bucket["updated_ts"] or 0), int(note.get("updated_ts") or 0))
        if note.get("source_url") or note.get("source") in {"link_import", "attachment_import"}:
            bucket["source_count"] += 1
        for tag in note.get("tags") or []:
            bucket["tags"][tag] = bucket["tags"].get(tag, 0) + 1
        if len(bucket["recent"]) < 4:
            bucket["recent"].append(_compact_note(note))
    rows = []
    for bucket in buckets.values():
        tags = sorted(bucket.pop("tags").items(), key=lambda x: (-x[1], x[0]))[:6]
        bucket["tags"] = [{"tag": tag, "count": count} for tag, count in tags]
        rows.append(bucket)
    rows.sort(key=lambda x: (x["name"] == "未归档", -int(x["updated_ts"] or 0), x["name"]))
    return {
        "notebooks": rows,
        "templates": [
            {"id": key, "label": value["label"], "tag": value["tag"]}
            for key, value in _TRANSFORM_TEMPLATES.items()
        ],
    }
