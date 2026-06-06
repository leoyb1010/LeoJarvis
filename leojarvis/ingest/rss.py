from __future__ import annotations

import httpx
import feedparser
import trafilatura

from ..config import sources
from .. import user_settings
from .base import Collector, RawItem


def _x_monitor_feeds() -> list[dict]:
    """Expand the X / Twitter monitor config into RSS feed dicts.

    Each entry in x_monitor.users may be a bare handle (templated through
    rsshub_base) or a full feed URL (e.g. an rss.app generated feed).
    """
    cfg = user_settings.load().get("x_monitor", {}) or {}
    if not cfg.get("enabled", False):
        return []
    base = str(cfg.get("rsshub_base", "https://rsshub.app")).rstrip("/")
    feeds: list[dict] = []
    for entry in cfg.get("users", []) or []:
        if not entry:
            continue
        s = str(entry).strip()
        if s.startswith("http://") or s.startswith("https://"):
            url, name = s, s
        else:
            handle = s.lstrip("@")
            url = f"{base}/twitter/user/{handle}"
            name = f"X · {handle}"
        feeds.append({
            "name": name,
            "url": url,
            "domain": "business",
            "category": "X社媒",
            "fulltext": False,
            "limit": int(cfg.get("limit", 6)),
        })
    return feeds


def _all_feeds() -> list[dict]:
    """Merge curated feeds (sources.toml) + user/OPML feeds (settings) + X monitor.

    De-duplicated by feed URL so importing an OPML twice or overlapping the
    curated list never creates duplicate pulls.
    """
    merged: list[dict] = []
    seen: set[str] = set()

    def add(feed: dict) -> None:
        if not isinstance(feed, dict):
            return
        url = str(feed.get("url", "")).strip()
        if not url or url in seen:
            return
        seen.add(url)
        merged.append(feed)

    for feed in sources().get("rss", []) or []:
        add(feed)
    user_rss = user_settings.load().get("rss", {}) or {}
    for feed in user_rss.get("sources", []) or []:
        if isinstance(feed, dict) and feed.get("enabled", True):
            add(feed)
    for feed in _x_monitor_feeds():
        add(feed)
    return merged


class RSSCollector(Collector):
    name = "rss"

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        for feed in _all_feeds():
            try:
                parsed = feedparser.parse(feed["url"])
            except Exception:
                continue
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
                published = getattr(entry, "published", "") or getattr(entry, "updated", "")
                items.append(RawItem(
                    source=f"rss:{feed.get('name', 'unnamed')}",
                    domain=feed.get("domain", "business"),
                    kind="news",
                    title=title,
                    content=content or title,
                    url=link,
                    meta={
                        "category": feed.get("category", "综合资讯"),
                        "feed_name": feed.get("name", "RSS"),
                        "original_title": title,
                        "published": published,
                    },
                ))
        return items
