from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import os
import re
import shutil
import sqlite3
import tempfile
import time


CHROME_EPOCH_OFFSET_SECONDS = 11_644_473_600
DEFAULT_WINDOW_DAYS = 45
_CACHE_TTL_SECONDS = 10 * 60
_CACHE: dict[str, object] = {"ts": 0.0, "payload": None}


_STOPWORDS = {
    "about", "account", "accounts", "admin", "auth", "blog", "cache", "chrome",
    "cloud", "code", "com", "docs", "file", "from", "google", "home", "html",
    "http", "https", "index", "login", "mail", "main", "page", "profile",
    "search", "settings", "signin", "support", "the", "top", "user", "users", "with",
    "www", "你的", "我们", "这个", "一个", "登录", "首页", "搜索", "设置",
}

_SENSITIVE_HOST_MARKERS = (
    "localhost",
    ".local",
    ".corp",
    ".internal",
    ".intranet",
    "inner",
    "internal",
    "corp.",
    ".lan",
    ".home",
)

_NOISE_HOST_LABELS = {
    "account",
    "accounts",
    "auth",
    "id",
    "ids",
    "login",
    "mail",
    "myaccount",
    "oauth",
    "signin",
    "sso",
}

_NOISE_HOSTS = {
    "google.com",
    "accounts.google.com",
    "mail.google.com",
    "myaccount.google.com",
}

_CATEGORY_TERMS = {
    "AI / Agent": (
        "ai", "agent", "agents", "chatgpt", "openai", "claude", "anthropic",
        "codex", "cursor", "grok", "gemini", "deepseek", "llm", "model",
        "mcp", "rag", "模型", "智能体", "大模型",
    ),
    "开发工具": (
        "github", "gitlab", "shadcn", "react", "swift", "xcode", "python",
        "typescript", "developer", "devtools", "工程", "代码", "开源",
    ),
    "云与网络": (
        "cloudflare", "tailscale", "vercel", "aws", "tencent", "huawei",
        "deploy", "funnel", "cdn", "server", "云", "网络",
    ),
    "内容社区": (
        "bilibili", "xiaohongshu", "x", "twitter", "youtube", "notion",
        "视频", "社区", "笔记",
    ),
    "财经市场": (
        "nvda", "btc", "eth", "spy", "finance", "market", "stock",
        "crypto", "美股", "加密", "财经",
    ),
}


@dataclass(frozen=True)
class BrowserPreferenceTerm:
    term: str
    score: float
    visits: int
    source: str


def browser_preferences(
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    limit_terms: int = 40,
    limit_domains: int = 18,
    refresh: bool = False,
) -> dict:
    now = time.time()
    cache_key = f"{window_days}:{limit_terms}:{limit_domains}"
    cached = _CACHE.get("payload")
    if (
        not refresh
        and isinstance(cached, dict)
        and cached.get("_cache_key") == cache_key
        and now - float(_CACHE.get("ts") or 0) < _CACHE_TTL_SECONDS
    ):
        payload = dict(cached)
        payload.pop("_cache_key", None)
        payload["cached"] = True
        return payload

    rows, profile_count, errors = _read_recent_history(window_days)
    domain_counts: Counter[str] = Counter()
    term_counts: Counter[str] = Counter()
    public_domain_counts: Counter[str] = Counter()

    for row in rows:
        host = _clean_host(row.get("url", ""))
        if not host:
            continue
        visits = max(1, int(row.get("visits") or 1))
        if not _is_sensitive_host(host) and not _is_noise_host(host):
            public_domain_counts[host] += visits
            for part in _host_terms(host):
                term_counts[part] += visits
        domain_counts[host] += visits
        if _is_sensitive_host(host) or _is_noise_host(host):
            continue
        text = " ".join([str(row.get("title") or ""), str(row.get("url") or "")])
        for term in _extract_terms(text):
            term_counts[term] += visits

    categories = _category_scores(term_counts, public_domain_counts)
    terms = _rank_terms(term_counts, limit_terms)
    domains = _rank_domains(public_domain_counts, limit_domains)
    payload = {
        "ok": True,
        "enabled": bool(rows),
        "generated_at": int(now),
        "window_days": window_days,
        "profiles_scanned": profile_count,
        "visits_considered": sum(domain_counts.values()),
        "terms": terms,
        "domains": domains,
        "categories": categories,
        "privacy": "Chrome history is read locally; raw URLs, titles, localhost, and internal hosts are not returned.",
        "errors": errors[:3],
    }
    cache_payload = dict(payload)
    cache_payload["_cache_key"] = cache_key
    _CACHE["ts"] = now
    _CACHE["payload"] = cache_payload
    return payload


def browser_preference_terms(limit: int = 40) -> set[str]:
    prefs = browser_preferences(limit_terms=limit)
    terms: set[str] = set()
    for item in prefs.get("terms", []):
        term = str(item.get("term", "")).strip().lower()
        if term:
            terms.add(term)
    for item in prefs.get("domains", [])[:12]:
        domain = str(item.get("domain", "")).strip().lower()
        if domain:
            terms.add(domain)
            terms.update(_host_terms(domain))
    return terms


def browser_preference_summary(limit: int = 10) -> str:
    prefs = browser_preferences(limit_terms=limit, limit_domains=8)
    terms = [str(item.get("term")) for item in prefs.get("terms", [])[:limit] if item.get("term")]
    categories = [str(item.get("name")) for item in prefs.get("categories", [])[:4] if item.get("name")]
    if not terms and not categories:
        return ""
    pieces = []
    if categories:
        pieces.append("方向：" + "、".join(categories))
    if terms:
        pieces.append("关键词：" + "、".join(terms[:limit]))
    return "；".join(pieces)


def _read_recent_history(window_days: int) -> tuple[list[dict], int, list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    profiles = _chrome_history_paths()
    cutoff_chrome_us = int((time.time() - window_days * 86400 + CHROME_EPOCH_OFFSET_SECONDS) * 1_000_000)
    for history_path in profiles:
        try:
            rows.extend(_read_history_db(history_path, cutoff_chrome_us))
        except Exception as exc:
            errors.append(f"{history_path.parent.name}: {type(exc).__name__}")
    return rows, len(profiles), errors


def _chrome_history_paths() -> list[Path]:
    root = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    candidates = []
    for profile in ["Default", *[f"Profile {i}" for i in range(1, 12)]]:
        path = root / profile / "History"
        if path.exists():
            candidates.append(path)
    extra = sorted(root.glob("*/History"))
    for path in extra:
        if path not in candidates and path.is_file():
            candidates.append(path)
    return candidates


def _read_history_db(path: Path, cutoff_chrome_us: int) -> list[dict]:
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(prefix="leojarvis-chrome-history-", suffix=".sqlite")
        os.close(fd)
        shutil.copy2(path, tmp_name)
        with sqlite3.connect(f"file:{tmp_name}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            records = conn.execute(
                """
                SELECT urls.url, urls.title, COUNT(visits.id) AS visits, MAX(visits.visit_time) AS last_visit_time
                FROM visits
                JOIN urls ON urls.id = visits.url
                WHERE visits.visit_time >= ?
                GROUP BY urls.id
                ORDER BY last_visit_time DESC
                LIMIT 5000
                """,
                (cutoff_chrome_us,),
            ).fetchall()
        return [dict(row) for row in records]
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _clean_host(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_sensitive_host(host: str) -> bool:
    lowered = host.lower()
    if any(marker in lowered for marker in _SENSITIVE_HOST_MARKERS):
        return True
    if lowered.startswith(("127.", "10.", "192.168.")):
        return True
    parts = lowered.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        first, second = int(parts[0]), int(parts[1])
        return first == 172 and 16 <= second <= 31 or first == 100 and 64 <= second <= 127
    return False


def _is_noise_host(host: str) -> bool:
    lowered = host.lower()
    if lowered in _NOISE_HOSTS:
        return True
    first = lowered.split(".", 1)[0]
    return first in _NOISE_HOST_LABELS


def _host_terms(host: str) -> list[str]:
    pieces = re.split(r"[^a-z0-9]+", host.lower())
    out = []
    for piece in pieces:
        if piece in {"app", "com", "cn", "dev", "net", "org", "io", "top", "ai", "www"}:
            if piece == "ai":
                out.append(piece)
            continue
        if len(piece) >= 2 and piece not in _STOPWORDS:
            out.append(piece)
    return out[:4]


def _extract_terms(text: str) -> list[str]:
    lowered = text.lower()
    raw_terms = re.findall(r"[a-z][a-z0-9+\-.]{1,30}|[\u4e00-\u9fff]{2,8}", lowered)
    terms = []
    for raw in raw_terms:
        term = raw.strip("._-+")
        if len(term) < 2 or term in _STOPWORDS:
            continue
        if re.fullmatch(r"\d+", term):
            continue
        if "." in term:
            terms.extend(_host_terms(term))
            continue
        terms.append(term)
    return terms[:80]


def _rank_terms(counter: Counter[str], limit: int) -> list[dict]:
    if not counter:
        return []
    max_count = max(counter.values()) or 1
    out = []
    for term, count in counter.most_common(limit * 3):
        if term in _STOPWORDS or len(term) < 2:
            continue
        score = min(1.0, 0.18 + count / max_count * 0.82)
        out.append({"term": term, "score": round(score, 3), "visits": int(count), "source": "chrome_history"})
        if len(out) >= limit:
            break
    return out


def _rank_domains(counter: Counter[str], limit: int) -> list[dict]:
    if not counter:
        return []
    max_count = max(counter.values()) or 1
    return [
        {"domain": host, "score": round(min(1.0, 0.2 + count / max_count * 0.8), 3), "visits": int(count)}
        for host, count in counter.most_common(limit)
    ]


def _category_scores(terms: Counter[str], domains: Counter[str]) -> list[dict]:
    combined = Counter(terms)
    for domain, count in domains.items():
        for part in _host_terms(domain):
            combined[part] += count
    rows = []
    for name, needles in _CATEGORY_TERMS.items():
        score = sum(combined.get(term.lower(), 0) for term in needles)
        if score:
            rows.append({"name": name, "score": int(score)})
    rows.sort(key=lambda item: item["score"], reverse=True)
    total = max(rows[0]["score"], 1) if rows else 1
    return [{**row, "weight": round(row["score"] / total, 3)} for row in rows[:6]]
