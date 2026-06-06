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
    names = database.table_names()
    if _TABLE_NAME not in names:
        dimension = int(settings().get("embeddings", {}).get("dimension", 768))
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dimension)),
            pa.field("text", pa.string()),
        ])
        return database.create_table(_TABLE_NAME, schema=schema)
    return database.open_table(_TABLE_NAME)


def remember_event(event_id: str, text: str) -> None:
    vector = embed(text)
    try:
        _open_table().add([{"id": event_id, "vector": vector, "text": text}])
    except Exception:
        db.insert_memory(text[:1000], memory_type="event_text", subject=event_id,
                         confidence=0.5, salience=0.4, source_events=[event_id])


def _text_score(query: str, text: str) -> float:
    q_terms = {t for t in query.lower().split() if t}
    if not q_terms:
        return 0.0
    hay = text.lower()
    hits = sum(1 for t in q_terms if t in hay)
    return hits / math.sqrt(len(q_terms))


def recall(query: str, k: int = 12) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        tbl = _open_table()
        if tbl.count_rows() > 0:
            return tbl.search(embed(query)).limit(k).to_list()
    except Exception:
        results = []
    rows = db.list_memories(limit=300)
    ranked = sorted(
        ({"id": r["id"], "text": r["statement"], "score": _text_score(query, r["statement"])} for r in rows),
        key=lambda x: x["score"], reverse=True,
    )
    return [r for r in ranked[:k] if r["score"] > 0]
