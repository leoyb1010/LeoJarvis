from __future__ import annotations

import httpx
import feedparser
import trafilatura

from ..config import sources
from .base import Collector, RawItem


class RSSCollector(Collector):
    name = "rss"

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        for feed in sources().get("rss", []):
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[: int(feed.get("limit", 15))]:
                content = getattr(entry, "summary", "") or ""
                link = getattr(entry, "link", "") or ""
                if feed.get("fulltext") and link:
                    try:
                        html = httpx.get(link, timeout=10, follow_redirects=True).text
                        content = trafilatura.extract(html) or content
                    except Exception:
                        content = content or "正文抓取失败，保留摘要。"
                title = getattr(entry, "title", "") or "（无标题）"
                items.append(RawItem(
                    source=f"rss:{feed.get('name', 'unnamed')}",
                    domain=feed.get("domain", "business"),
                    kind="news",
                    title=title,
                    content=content or title,
                    url=link,
                ))
        return items
