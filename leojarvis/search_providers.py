"""多源搜索 + 排序(C2)。清室重写,设计借鉴 odysseus 的 SearchService/providers/ranking,
代码全新、无 AGPL 牵连。

把现仅 Tavily 的 mcp_gateway.search_web 抽象成可插拔 provider:
  - 免费源优先:SearXNG(自建)/DuckDuckGo;key-gated:Brave/Serper/Google-PSE。
  - Tavily 走现有付费预算保留,作兜底(不绕过 intelligence 的配额)。
然后对合并结果做 rank():相关度 + 时效衰减 + 域名权威。结果交给调用方(research_deep 等)前
**经 prompt_security 包裹**(外部内容防注入)。

降级:一个 provider 都不可用 → {ok:True, items:[], degraded:True},绝不抛。
配置 config/settings.toml [search]。
"""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger("search_providers")

_CACHE: dict[str, tuple[float, list]] = {}   # query → (ts, results);进程内,结果本就易变,不落库


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    provider: str
    published_ts: int | None = None
    raw_score: float | None = None


def _cfg() -> dict:
    try:
        from .config import settings
        return settings().get("search", {}) or {}
    except Exception:
        return {}


def _http_json(url: str, *, headers: dict | None = None, timeout: float = 12) -> dict | None:
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "LeoJarvis-Search/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        log.debug("search http failed %s: %s", url, exc)
        return None


# ---------- providers(每个独立、可降级) ----------

def _searxng(query: str, limit: int) -> list[SearchResult]:
    base = str(_cfg().get("searxng_url", "")).strip()
    if not base:
        return []
    url = base.rstrip("/") + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    data = _http_json(url) or {}
    out = []
    for r in (data.get("results") or [])[:limit]:
        out.append(SearchResult(title=r.get("title", ""), url=r.get("url", ""),
                                content=r.get("content", ""), provider="searxng", raw_score=r.get("score")))
    return out


def _brave(query: str, limit: int) -> list[SearchResult]:
    import os
    key = str(_cfg().get("brave_key", "") or os.environ.get("BRAVE_API_KEY", "")).strip()
    if not key:
        return []
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": limit})
    data = _http_json(url, headers={"X-Subscription-Token": key, "Accept": "application/json"}) or {}
    out = []
    for r in ((data.get("web") or {}).get("results") or [])[:limit]:
        out.append(SearchResult(title=r.get("title", ""), url=r.get("url", ""),
                                content=r.get("description", ""), provider="brave"))
    return out


def _tavily(query: str, limit: int) -> list[SearchResult]:
    """Tavily 走现有 mcp_gateway(含付费预算保留),作兜底。"""
    try:
        from . import mcp_gateway
        res = mcp_gateway.search_web(query, limit=limit)
        return [SearchResult(title=i.get("title", ""), url=i.get("url", ""), content=i.get("content", ""),
                             provider="tavily", raw_score=i.get("score")) for i in res.get("items", [])]
    except Exception:
        return []


# provider 注册:免费/自建优先,Tavily(付费)排最后兜底。
_PROVIDERS = {"searxng": _searxng, "brave": _brave, "tavily": _tavily}
_DEFAULT_ORDER = ["searxng", "brave", "tavily"]


# ---------- 排序 ----------

_TRUSTED = {"gov", "edu", "wikipedia.org", "arxiv.org", "github.com", "nature.com", "reuters.com",
            "apnews.com", "bbc.co.uk", "nytimes.com"}
_LOWVALUE = {"pinterest.com", "quora.com"}


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def _authority(url: str) -> float:
    h = _host(url)
    cfg = _cfg().get("authority", {}) or {}
    boost = set(cfg.get("boost", [])) | _TRUSTED
    penalize = set(cfg.get("penalize", [])) | _LOWVALUE
    if any(b in h for b in boost):
        return 1.0
    if any(p in h for p in penalize):
        return 0.2
    return 0.6


def rank(results: list[SearchResult], query: str) -> list[SearchResult]:
    """相关度 + 时效 + 权威 加权排序(全确定性)。"""
    from .memory.store import _text_score
    w = _cfg().get("weights", {}) or {}
    w_rel, w_rec, w_auth = float(w.get("relevance", 0.6)), float(w.get("recency", 0.2)), float(w.get("authority", 0.2))
    half = float(_cfg().get("recency_half_life_days", 30)) or 30
    now = time.time()

    def score(r: SearchResult) -> float:
        rel = _text_score(query, f"{r.title} {r.content}")
        if r.raw_score is not None:
            rel = max(rel, min(1.0, float(r.raw_score)))
        if r.published_ts:
            age_days = max(0.0, (now - r.published_ts / 1000) / 86400)
            rec = math.exp(-age_days / half)
        else:
            rec = 0.5
        return w_rel * rel + w_rec * rec + w_auth * _authority(r.url)
    return sorted(results, key=score, reverse=True)


def _enhance(query: str) -> str:
    """短/泛查询时,用画像关键词补一点上下文(确定性,不调 LLM)。"""
    q = (query or "").strip()
    if len(q) >= 12:
        return q
    try:
        from .memory.profile import profile_terms
        terms = [t for t in profile_terms() if t][:2]
        return (q + " " + " ".join(terms)).strip() if terms else q
    except Exception:
        return q


def search(query: str, *, limit: int = 8, enhance: bool = True, wrap: bool = False) -> dict:
    """多源搜索 + 排序。wrap=True 时附带 prompt_security 包好的 text(给喂模型用)。"""
    q0 = (query or "").strip()
    if not q0:
        return {"ok": False, "error": "query required"}
    q = _enhance(q0) if enhance else q0

    cache_ttl = float(_cfg().get("cache_ttl_s", 900))
    hit = _CACHE.get(q)
    if hit and (time.time() - hit[0]) < cache_ttl:
        merged = hit[1]
        provider_used = "cache"
    else:
        order = [p for p in (_cfg().get("order") or _DEFAULT_ORDER) if p in _PROVIDERS]
        merged: list[SearchResult] = []
        provider_used = None
        for pid in order:
            try:
                got = _PROVIDERS[pid](q, limit)
            except Exception:
                got = []
            if got:
                provider_used = provider_used or pid
                merged.extend(got)
                if len(merged) >= limit:  # 拿够就停,免无谓付费源
                    break
        # URL 去重
        seen, dedup = set(), []
        for r in merged:
            key = _host(r.url) + urllib.parse.urlparse(r.url).path if r.url else r.title
            if key in seen:
                continue
            seen.add(key)
            dedup.append(r)
        merged = dedup
        if merged:
            _CACHE[q] = (time.time(), merged)

    if not merged:
        return {"ok": True, "query": q, "items": [], "degraded": True,
                "note": "未配置可用搜索源(SearXNG/Brave/Tavily 均不可用)。"}

    ranked = rank(merged, q)[:limit]
    items = [{"title": r.title, "url": r.url, "content": r.content, "provider": r.provider} for r in ranked]
    out = {"ok": True, "query": q, "provider_used": provider_used, "items": items, "degraded": False}
    if wrap:
        from .prompt_security import wrap_search_results
        out["wrapped"] = wrap_search_results(items, source="search")
    return out
