"""Re-judge existing events with the upgraded LLM judge so stored analysis
becomes real, distinct, Chinese per-item content (replaces stale fallback)."""
from __future__ import annotations

import sys
import time
from types import SimpleNamespace

from leojarvis import db
from leojarvis.judge.engine import judge_and_store


def main(hours: int = 96) -> None:
    since = int((time.time() - hours * 3600) * 1000)
    with db.conn() as c:
        events = c.execute(
            "SELECT id, source, domain, kind, title, content, url FROM events WHERE ts>=? ORDER BY ts DESC",
            (since,),
        ).fetchall()
    total = len(events)
    print(f"re-judging {total} events from last {hours}h")
    for i, e in enumerate(events, 1):
        item = SimpleNamespace(
            source=e["source"], domain=e["domain"] or "business", kind=e["kind"],
            title=e["title"] or "", content=e["content"] or "", url=e["url"] or "",
        )
        with db.conn() as c:
            c.execute("DELETE FROM judgments WHERE event_id=?", (e["id"],))
        try:
            j = judge_and_store(e["id"], item)
            tag = j.triage
        except Exception as exc:  # noqa: BLE001
            tag = f"ERR:{exc}"
        if i % 5 == 0 or i == total:
            print(f"  [{i}/{total}] {tag} :: {(e['title'] or '')[:48]}", flush=True)
    print("done")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 96)
