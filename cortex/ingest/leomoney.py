from __future__ import annotations

import httpx

from ..config import sources
from .base import Collector, RawItem


class LeomoneyCollector(Collector):
    name = "leomoney"
    domain = "business"

    def collect(self) -> list[RawItem]:
        cfg = sources().get("leomoney", {})
        base = cfg.get("base_url", "http://localhost:3210").rstrip("/")
        try:
            data = httpx.get(f"{base}/api/intel/digest", timeout=10).json()
        except Exception:
            return []
        items: list[RawItem] = []
        for it in data.get("items", []):
            title = it.get("title") or it.get("symbol") or "leomoney 动态"
            content = it.get("summary") or it.get("content") or title
            items.append(RawItem(
                source="leomoney",
                domain="business",
                kind="market",
                title=title,
                content=content,
                url=it.get("url", ""),
                meta={"symbol": it.get("symbol"), "raw_type": it.get("type")},
            ))
        return items
