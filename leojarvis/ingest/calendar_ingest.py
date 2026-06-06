from __future__ import annotations

from datetime import date

import httpx

from ..config import sources
from .base import Collector, RawItem


class CalendarCollector(Collector):
    name = "calendar"
    domain = "life"

    def collect(self) -> list[RawItem]:
        cfg = sources().get("calendar", {})
        url = cfg.get("ics_url")
        if not url:
            return []
        try:
            text = httpx.get(url, timeout=10, follow_redirects=True).text
        except Exception:
            return []
        items: list[RawItem] = []
        today = date.today().isoformat().replace("-", "")
        cur: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line == "BEGIN:VEVENT":
                cur = {}
            elif line.startswith("SUMMARY:"):
                cur["summary"] = line[8:]
            elif line.startswith("DTSTART"):
                cur["start"] = line.split(":", 1)[-1]
            elif line == "END:VEVENT" and cur.get("start", "").startswith(today):
                title = cur.get("summary", "日程")
                items.append(RawItem(
                    source="calendar",
                    domain="life",
                    kind="calendar",
                    title=title,
                    content=f"今天 {cur.get('start', '')} · {title}",
                ))
        return items
