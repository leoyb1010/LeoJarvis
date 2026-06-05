from __future__ import annotations

import time

from .. import db


def build_today() -> dict:
    since = int((time.time() - 24 * 3600) * 1000)
    with db.conn() as c:
        rows = c.execute(
            """
            SELECT e.id AS event_id, e.title, e.url, e.domain, e.source, e.kind,
                   j.score, j.take, j.triage, j.reasons, j.ts
            FROM judgments j JOIN events e ON e.id=j.event_id
            WHERE j.ts>=? AND j.triage IN ('notify','digest')
            ORDER BY j.score DESC, j.ts DESC
            """,
            (since,),
        ).fetchall()
    business = [dict(r) for r in rows if r["domain"] == "business"]
    life = [dict(r) for r in rows if r["domain"] == "life"]
    return {
        "generated_at": int(time.time()),
        "business": business,
        "life": life,
        "counts": {"business": len(business), "life": len(life)},
    }
