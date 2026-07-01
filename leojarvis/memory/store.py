from __future__ import annotations

import math
from typing import Any

from .. import db
from ..config import VECTORS_PATH, settings
from ..embeddings import embed

_TABLE_NAME = "events"


def _open_table():
    import lancedb
    import pyarrow as pa

    database = lancedb.connect(str(VECTORS_PATH))
    # 新版 lancedb 用 list_tables()，table_names() 已弃用（会告警，未来版本移除）；旧版无 list_tables。
    names = database.list_tables() if hasattr(database, "list_tables") else database.table_names()
    if _TABLE_NAME not in names:
        dimension = int(settings().get("embeddings", {}).get("dimension", 768))
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dimension)),
            pa.field("text", pa.string()),
            # 超级 Jarvis P1：向量行也带 layer，检索时可按层加权/过滤。
            pa.field("layer", pa.string()),
        ])
        return database.create_table(_TABLE_NAME, schema=schema)
    tbl = database.open_table(_TABLE_NAME)
    # 兼容旧表（无 layer 列）：旧表 search 仍可用，写入时只补已有列。
    return tbl


def _table_has_layer(tbl) -> bool:
    try:
        return "layer" in tbl.schema.names
    except Exception:
        return False


def remember(text: str, *, ref_id: str, layer: str = "episode") -> None:
    """把一段文本写入向量库（带 layer）。失败时降级到 SQLite memories（episode 层）。"""
    vector = embed(text)
    try:
        tbl = _open_table()
        row: dict[str, Any] = {"id": ref_id, "vector": vector, "text": text}
        if _table_has_layer(tbl):
            row["layer"] = layer
        tbl.add([row])
    except Exception:
        db.insert_memory(text[:1000], memory_type="event_text", subject=ref_id,
                         confidence=0.5, salience=0.4, source_events=[ref_id],
                         status="active", layer=layer, origin="vector_fallback")


def remember_event(event_id: str, text: str) -> None:
    """向后兼容入口：事件文本 → episode 层。"""
    remember(text, ref_id=event_id, layer="episode")


def forget_vectors(ids: list[str]) -> int:
    """被遗忘权：从向量库删除指定 id 的行（配合 db.delete_memories_by_source）。"""
    if not ids:
        return 0
    try:
        tbl = _open_table()
        quoted = ",".join("'" + str(i).replace("'", "''") + "'" for i in ids)
        tbl.delete(f"id IN ({quoted})")
        return len(ids)
    except Exception:
        return 0


def _text_score(query: str, text: str) -> float:
    q_terms = {t for t in query.lower().split() if t}
    if not q_terms:
        return 0.0
    hay = text.lower()
    hits = sum(1 for t in q_terms if t in hay)
    return hits / math.sqrt(len(q_terms))


def recall(query: str, k: int = 12, *, layers: list[str] | None = None) -> list[dict[str, Any]]:
    """语义召回。可选按 layer 过滤（如只取 fact+pattern 给决策用）。
    向量库优先；不可用时退回 SQLite memories 关键词粗排。"""
    try:
        tbl = _open_table()
        if tbl.count_rows() > 0:
            q = tbl.search(embed(query)).limit(k * 3 if layers else k)
            rows = q.to_list()
            if layers and rows and "layer" in (rows[0] or {}):
                rows = [r for r in rows if (r.get("layer") or "episode") in layers]
            return rows[:k]
    except Exception:
        pass
    # 降级：SQLite memories（支持 layer 过滤）
    db_rows = (db.list_memories_by_layer(layers, limit=300)
               if layers else db.list_memories(limit=300))
    ranked = sorted(
        ({"id": r["id"], "text": r["statement"], "layer": (r["layer"] if "layer" in r.keys() else "fact"),
          "score": _text_score(query, r["statement"])} for r in db_rows),
        key=lambda x: x["score"], reverse=True,
    )
    return [r for r in ranked[:k] if r["score"] > 0]
