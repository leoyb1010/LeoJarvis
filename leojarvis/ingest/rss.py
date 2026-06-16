from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx
import feedparser
import trafilatura

from ..config import sources
from .. import user_settings
from ..localize import to_chinese
from .base import Collector, RawItem


def x_monitor_feeds() -> list[dict]:
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
            route = "custom_feed"
        else:
            handle = s.lstrip("@")
            # rsshub.app 的 Twitter/X 路由需要实例侧账号配置，公共实例经常 404。
            # 用户配置自建 RSSHub 时继续走 RSSHub；默认公共实例则用 Nitter RSS 兜底。
            if base in {"https://rsshub.app", "http://rsshub.app"}:
                url = f"https://nitter.net/{handle}/rss"
                route = "nitter_fallback"
            else:
                url = f"{base}/twitter/user/{handle}"
                route = "rsshub"
            name = f"X · @{handle}"
        feeds.append({
            "name": name,
            "url": url,
            "domain": "business",
            "category": "X社媒",
            "fulltext": False,
            "limit": int(cfg.get("limit", 6)),
            "meta": {
                "channel": "x_monitor",
                "handle": s if s.startswith("http") else f"@{s.lstrip('@')}",
                "route": route,
            },
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
    for feed in x_monitor_feeds():
        add(feed)
    return merged


class RSSCollector(Collector):
    name = "rss"

    def collect(self) -> list[RawItem]:
        feeds = _all_feeds()
        if not feeds:
            return []
        # 并行抓取所有源：14+ 个源不再串行累加，总耗时≈最慢一个源，大幅提速。
        with ThreadPoolExecutor(max_workers=min(16, len(feeds))) as ex:
            batches = list(ex.map(self._fetch_feed, feeds))
        items: list[RawItem] = []
        for b in batches:
            items.extend(b)
        return items

    def _fetch_feed(self, feed: dict) -> list[RawItem]:
        items: list[RawItem] = []
        timeout = httpx.Timeout(8.0, connect=4.0)
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                res = client.get(feed["url"])
                res.raise_for_status()
                parsed = feedparser.parse(res.content)
                for entry in parsed.entries[: int(feed.get("limit", 15))]:
                    content = getattr(entry, "summary", "") or ""
                    link = getattr(entry, "link", "") or ""
                    if feed.get("fulltext") and link:
                        try:
                            html = client.get(link, timeout=httpx.Timeout(10.0, connect=4.0)).text
                            content = trafilatura.extract(html) or content
                        except Exception:
                            content = content or "正文抓取失败，保留摘要。"
                    title = getattr(entry, "title", "") or "（无标题）"
                    published = getattr(entry, "published", "") or getattr(entry, "updated", "")
                    is_x = (feed.get("category") == "X社媒") or ((feed.get("meta") or {}).get("channel") == "x_monitor")
                    display_title = to_chinese(title, context="X 监控动态标题" if is_x else "RSS 资讯标题", max_chars=140) if is_x else title
                    display_content = to_chinese(content or title, context="X 监控动态摘要" if is_x else "RSS 资讯摘要", max_chars=1200) if is_x else (content or title)
                    items.append(RawItem(
                        source=f"rss:{feed.get('name', 'unnamed')}",
                        domain=feed.get("domain", "business"),
                        kind="x_post" if is_x else "news",
                        title=display_title,
                        content=display_content,
                        url=link,
                        meta={
                            "category": feed.get("category", "综合资讯"),
                            "feed_name": feed.get("name", "RSS"),
                            "original_title": title,
                            "published": published,
                            **(feed.get("meta") or {}),
                        },
                    ))
        except Exception:
            return items
        return items
