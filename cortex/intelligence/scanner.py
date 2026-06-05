from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus

import feedparser
import httpx
import trafilatura

from .. import db
from ..config import settings, sources
from ..ingest.base import RawItem
from ..judge.engine import Judgment, judge_and_store
from ..localize import chinese_tags, to_chinese
from ..memory.profile import profile_terms
from ..memory.store import remember_event
from ..notify.hub import hub

USER_AGENT = "Cortex-Intelligence/0.1 (+https://github.com/leoyb1010/cortex)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rowdict(row: Any) -> dict:
    return dict(row) if row is not None else {}


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _clean_text(text: str, limit: int = 6000) -> str:
    compact = " ".join((text or "").split())
    return compact[:limit]


def _event_day() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def seed_defaults() -> dict:
    """Create user-friendly intelligence defaults from existing config/profile."""
    db.init_db()
    created = {"targets": 0, "sources": 0}
    ts = db.now_ms()
    terms = sorted(profile_terms())
    base_targets = [t for t in terms if len(t) >= 2][:18]
    if not base_targets:
        base_targets = ["AI Agent", "本地大模型", "个人生产力", "Mac 自动化"]

    cfg = sources()
    radar_cfg = cfg.get("github_radar", {})
    for q in radar_cfg.get("queries", []):
        if str(q).strip():
            base_targets.append(str(q).strip())

    with db.conn() as c:
        for target in dict.fromkeys(base_targets):
            try:
                c.execute(
                    """INSERT INTO intelligence_targets(id,label,kind,query,enabled,created_ts,updated_ts)
                       VALUES(?,?,?,?,1,?,?)""",
                    (uuid.uuid4().hex, target, "topic", target, ts, ts),
                )
                created["targets"] += 1
            except Exception:
                created["skipped"] = created.get("skipped", 0) + 1

        for feed in cfg.get("rss", []):
            url = str(feed.get("url", "")).strip()
            if not url:
                continue
            meta = {
                "fulltext": bool(feed.get("fulltext", False)),
                "limit": int(feed.get("limit", 10)),
            }
            try:
                c.execute(
                    """INSERT INTO intelligence_sources(id,type,name,url,domain,enabled,meta,created_ts,updated_ts)
                       VALUES(?,?,?,?,?,1,?,?,?)""",
                    (
                        uuid.uuid4().hex,
                        "rss",
                        str(feed.get("name") or url),
                        url,
                        str(feed.get("domain", "business")),
                        json.dumps(meta, ensure_ascii=False),
                        ts,
                        ts,
                    ),
                )
                created["sources"] += 1
            except Exception:
                created["skipped"] = created.get("skipped", 0) + 1

        starter_web = [
            ("OpenAI Blog", "https://openai.com/news/", "business"),
            ("GitHub Trending", "https://github.com/trending", "business"),
        ]
        for name, url, domain in starter_web:
            try:
                c.execute(
                    """INSERT INTO intelligence_sources(id,type,name,url,domain,enabled,meta,created_ts,updated_ts)
                       VALUES(?,?,?,?,?,1,?,?,?)""",
                    (uuid.uuid4().hex, "web", name, url, domain, "{}", ts, ts),
                )
                created["sources"] += 1
            except Exception:
                created["skipped"] = created.get("skipped", 0) + 1
    return created


def list_targets() -> list[dict]:
    seed_defaults()
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM intelligence_targets ORDER BY enabled DESC, updated_ts DESC, label COLLATE NOCASE"
        ).fetchall()
    return [_rowdict(r) for r in rows]


def upsert_target(*, label: str, query: str, kind: str = "topic", enabled: bool = True) -> dict:
    db.init_db()
    ts = db.now_ms()
    label = label.strip() or query.strip()
    query = query.strip() or label
    kind = kind.strip() or "topic"
    with db.conn() as c:
        row = c.execute(
            "SELECT id FROM intelligence_targets WHERE kind=? AND query=?",
            (kind, query),
        ).fetchone()
        if row:
            c.execute(
                """UPDATE intelligence_targets
                   SET label=?, enabled=?, updated_ts=? WHERE id=?""",
                (label, 1 if enabled else 0, ts, row["id"]),
            )
            target_id = row["id"]
        else:
            target_id = uuid.uuid4().hex
            c.execute(
                """INSERT INTO intelligence_targets(id,label,kind,query,enabled,created_ts,updated_ts)
                   VALUES(?,?,?,?,?,?,?)""",
                (target_id, label, kind, query, 1 if enabled else 0, ts, ts),
            )
        target = c.execute("SELECT * FROM intelligence_targets WHERE id=?", (target_id,)).fetchone()
    return _rowdict(target)


def set_target_enabled(target_id: str, enabled: bool) -> dict:
    with db.conn() as c:
        c.execute(
            "UPDATE intelligence_targets SET enabled=?, updated_ts=? WHERE id=?",
            (1 if enabled else 0, db.now_ms(), target_id),
        )
        row = c.execute("SELECT * FROM intelligence_targets WHERE id=?", (target_id,)).fetchone()
    return _rowdict(row)


def list_sources() -> list[dict]:
    seed_defaults()
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM intelligence_sources ORDER BY enabled DESC, type, updated_ts DESC"
        ).fetchall()
    result = []
    for row in rows:
        item = _rowdict(row)
        item["meta"] = _json_loads(item.get("meta"), {})
        result.append(item)
    return result


def upsert_source(*, source_type: str, name: str, url: str, domain: str = "business",
                  enabled: bool = True, meta: dict | None = None) -> dict:
    db.init_db()
    ts = db.now_ms()
    source_type = source_type.strip().lower()
    if source_type not in {"rss", "web"}:
        raise ValueError("source_type must be rss or web")
    name = name.strip() or url.strip()
    url = url.strip()
    if not url:
        raise ValueError("url is required")
    with db.conn() as c:
        row = c.execute(
            "SELECT id FROM intelligence_sources WHERE type=? AND url=?",
            (source_type, url),
        ).fetchone()
        if row:
            c.execute(
                """UPDATE intelligence_sources
                   SET name=?, domain=?, enabled=?, meta=?, updated_ts=? WHERE id=?""",
                (name, domain, 1 if enabled else 0,
                 json.dumps(meta or {}, ensure_ascii=False), ts, row["id"]),
            )
            source_id = row["id"]
        else:
            source_id = uuid.uuid4().hex
            c.execute(
                """INSERT INTO intelligence_sources(id,type,name,url,domain,enabled,meta,created_ts,updated_ts)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    source_id,
                    source_type,
                    name,
                    url,
                    domain,
                    1 if enabled else 0,
                    json.dumps(meta or {}, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
        source = c.execute("SELECT * FROM intelligence_sources WHERE id=?", (source_id,)).fetchone()
    item = _rowdict(source)
    item["meta"] = _json_loads(item.get("meta"), {})
    return item


def set_source_enabled(source_id: str, enabled: bool) -> dict:
    with db.conn() as c:
        c.execute(
            "UPDATE intelligence_sources SET enabled=?, updated_ts=? WHERE id=?",
            (1 if enabled else 0, db.now_ms(), source_id),
        )
        row = c.execute("SELECT * FROM intelligence_sources WHERE id=?", (source_id,)).fetchone()
    item = _rowdict(row)
    item["meta"] = _json_loads(item.get("meta"), {})
    return item


async def _store_raw_item(item: RawItem, *, dedup_key: str | None = None) -> tuple[str | None, Judgment | None]:
    event_id = db.insert_event(
        source=item.source,
        domain=item.domain,
        kind=item.kind,
        title=item.title,
        content=item.content,
        url=item.url,
        meta=item.meta,
        dedup_key=dedup_key or item.dedup_key,
    )
    if event_id is None:
        return None, None
    remember_event(event_id, f"{item.title}\n{item.content[:900]}")
    judgment = judge_and_store(event_id, item)
    if judgment.triage == "notify":
        await hub.push({
            "type": "notify",
            "source": "Intelligence",
            "event_id": event_id,
            "title": item.title,
            "take": judgment.take,
            "url": item.url,
            "score": judgment.score,
        })
    return event_id, judgment


async def _scan_rss_sources(client: httpx.AsyncClient) -> dict:
    stats = {"seen": 0, "inserted": 0, "notify": 0, "errors": []}
    for src in [s for s in list_sources() if s["enabled"] and s["type"] == "rss"]:
        try:
            parsed = feedparser.parse(src["url"])
            meta = src.get("meta") or {}
            limit = int(meta.get("limit", 12))
            for entry in parsed.entries[:limit]:
                stats["seen"] += 1
                original_title = getattr(entry, "title", "") or "（无标题）"
                link = getattr(entry, "link", "") or ""
                content = getattr(entry, "summary", "") or original_title
                if meta.get("fulltext") and link:
                    try:
                        html = (await client.get(link)).text
                        content = trafilatura.extract(html) or content
                    except Exception:
                        content = content or "正文抓取失败，保留摘要。"
                title = to_chinese(original_title, context="RSS 资讯标题", max_chars=120)
                chinese_content = to_chinese(content, context="RSS 资讯摘要", max_chars=1500)
                published = getattr(entry, "published", "") or getattr(entry, "updated", "")
                item = RawItem(
                    source=f"intel:rss:{src['name']}",
                    domain=src.get("domain") or "business",
                    kind="news",
                    title=title,
                    content=_clean_text(chinese_content),
                    url=link,
                    meta={"source_id": src["id"], "published": published, "original_title": original_title},
                )
                event_id, judgment = await _store_raw_item(item)
                if event_id:
                    stats["inserted"] += 1
                    if judgment and judgment.triage == "notify":
                        stats["notify"] += 1
            with db.conn() as c:
                c.execute("UPDATE intelligence_sources SET last_scan_ts=? WHERE id=?", (db.now_ms(), src["id"]))
        except Exception as exc:
            stats["errors"].append({"source": src["name"], "error": str(exc)})
    return stats


async def _scan_web_sources(client: httpx.AsyncClient) -> dict:
    stats = {"seen": 0, "changed": 0, "inserted": 0, "notify": 0, "errors": []}
    for src in [s for s in list_sources() if s["enabled"] and s["type"] == "web"]:
        try:
            stats["seen"] += 1
            res = await client.get(src["url"])
            res.raise_for_status()
            extracted = trafilatura.extract(res.text, include_comments=False, include_tables=False)
            text = _clean_text(extracted or res.text, limit=10000)
            if not text:
                continue
            digest = _hash_text(text)
            changed = digest != src.get("last_hash")
            first_seen = not src.get("last_hash")
            with db.conn() as c:
                c.execute(
                    "UPDATE intelligence_sources SET last_scan_ts=?, last_hash=?, updated_ts=? WHERE id=?",
                    (db.now_ms(), digest, db.now_ms(), src["id"]),
                )
            if not changed:
                continue
            stats["changed"] += 1
            title = f"{src['name']} {'首次纳入监控' if first_seen else '出现内容变化'}"
            chinese_text = to_chinese(text[:3500], context="网页变化摘要", max_chars=1600)
            item = RawItem(
                source=f"intel:web:{src['name']}",
                domain=src.get("domain") or "business",
                kind="web_change",
                title=title,
                content=chinese_text,
                url=src["url"],
                meta={"source_id": src["id"], "first_seen": first_seen, "hash": digest},
            )
            event_id, judgment = await _store_raw_item(item, dedup_key=f"web:{src['id']}:{digest}")
            if event_id:
                stats["inserted"] += 1
                if judgment and judgment.triage == "notify":
                    stats["notify"] += 1
        except Exception as exc:
            stats["errors"].append({"source": src["name"], "error": str(exc)})
    return stats


def _github_queries() -> list[str]:
    seed_defaults()
    cfg = sources().get("github_radar", {})
    configured = [str(q).strip() for q in cfg.get("queries", []) if str(q).strip()]
    target_queries = [
        str(t["query"]).strip()
        for t in list_targets()
        if t.get("enabled") and str(t.get("query", "")).strip()
    ]
    queries = list(dict.fromkeys(configured + target_queries))
    return queries[: int(cfg.get("max_queries", 10))]


def _parse_github_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except Exception:
            return None


def _snapshot_velocity(repo_full_name: str, stars: int, observed_ts: int) -> dict:
    since_24h = observed_ts - 24 * 3600 * 1000
    since_7d = observed_ts - 7 * 24 * 3600 * 1000
    with db.conn() as c:
        prev_any = c.execute(
            """SELECT stars, observed_ts FROM github_repo_snapshots
               WHERE repo_full_name=? AND observed_ts<?
               ORDER BY observed_ts DESC LIMIT 1""",
            (repo_full_name, observed_ts),
        ).fetchone()
        prev_24 = c.execute(
            """SELECT stars, observed_ts FROM github_repo_snapshots
               WHERE repo_full_name=? AND observed_ts<=?
               ORDER BY observed_ts DESC LIMIT 1""",
            (repo_full_name, since_24h),
        ).fetchone()
        prev_7d = c.execute(
            """SELECT stars, observed_ts FROM github_repo_snapshots
               WHERE repo_full_name=? AND observed_ts<=?
               ORDER BY observed_ts DESC LIMIT 1""",
            (repo_full_name, since_7d),
        ).fetchone()
    delta_24h = stars - int(prev_24["stars"]) if prev_24 else None
    delta_7d = stars - int(prev_7d["stars"]) if prev_7d else None
    per_day = None
    delta_since_last = None
    last_interval_hours = None
    if prev_any:
        delta_since_last = stars - int(prev_any["stars"])
        elapsed_ms = max(observed_ts - int(prev_any["observed_ts"]), 1)
        days = max(elapsed_ms / 86_400_000, 1 / 24)
        last_interval_hours = round(elapsed_ms / 3_600_000, 2)
        per_day = round(delta_since_last / days, 2)
    return {
        "delta_since_last": delta_since_last,
        "last_interval_hours": last_interval_hours,
        "delta_24h": delta_24h,
        "delta_7d": delta_7d,
        "stars_per_day": per_day,
    }


def _github_score(repo: dict, velocity: dict) -> tuple[float, list[str]]:
    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    created = _parse_github_dt(repo.get("created_at"))
    pushed = _parse_github_dt(repo.get("pushed_at"))
    now = datetime.now(timezone.utc)
    age_days = max((now - created).days, 1) if created else 365
    pushed_days = max((now - pushed).days, 0) if pushed else 365
    cold_momentum = stars / max(age_days, 1)
    growth = velocity.get("stars_per_day")
    reasons: list[str] = []

    score = 0.25
    if stars >= 1000:
        score += 0.12
        reasons.append("star 基数已过 1k")
    if stars >= 10000:
        score += 0.08
        reasons.append("高 star 项目")
    if forks >= max(stars * 0.08, 50):
        score += 0.06
        reasons.append("fork 活跃")
    if pushed_days <= 7:
        score += 0.12
        reasons.append("最近一周仍活跃")
    if age_days <= 180 and cold_momentum >= 15:
        score += 0.2
        reasons.append(f"冷启动动量强：约 {cold_momentum:.1f} star/天")
    elif cold_momentum >= 8:
        score += 0.12
        reasons.append(f"长期增速不错：约 {cold_momentum:.1f} star/天")
    if growth is not None:
        if growth >= 100:
            score += 0.28
            reasons.append(f"实测 star 增速很快：约 {growth:.0f}/天")
        elif growth >= 25:
            score += 0.18
            reasons.append(f"实测 star 增速明显：约 {growth:.0f}/天")
        elif growth > 0:
            score += 0.08
            reasons.append(f"实测 star 仍在增长：约 {growth:.1f}/天")
    return min(score, 0.98), reasons or ["GitHub radar"]


def _insert_repo_snapshot(repo: dict, query: str, velocity: dict) -> None:
    with db.conn() as c:
        c.execute(
            """INSERT INTO github_repo_snapshots(
                 id, repo_full_name, query, stars, forks, open_issues, description, url,
                 language, topics, license, created_at, pushed_at, updated_at, observed_ts
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uuid.uuid4().hex,
                repo["full_name"],
                query,
                int(repo.get("stargazers_count") or 0),
                int(repo.get("forks_count") or 0),
                int(repo.get("open_issues_count") or 0),
                repo.get("description") or "",
                repo.get("html_url") or "",
                repo.get("language") or "",
                json.dumps(repo.get("topics") or [], ensure_ascii=False),
                (repo.get("license") or {}).get("spdx_id") or "",
                repo.get("created_at") or "",
                repo.get("pushed_at") or "",
                repo.get("updated_at") or "",
                db.now_ms(),
            ),
        )


async def _scan_github(client: httpx.AsyncClient) -> dict:
    cfg = sources().get("github_radar", {})
    if cfg.get("enabled", True) is False:
        return {"seen": 0, "inserted": 0, "notify": 0, "errors": [], "disabled": True}
    min_stars = int(cfg.get("min_stars", 300))
    max_results = int(cfg.get("max_results_per_query", 8))
    pushed_days = int(cfg.get("pushed_days", 45))
    created_days = int(cfg.get("created_days", 730))
    pushed_after = (datetime.now(timezone.utc) - timedelta(days=pushed_days)).date().isoformat()
    created_after = (datetime.now(timezone.utc) - timedelta(days=created_days)).date().isoformat()
    stats = {"seen": 0, "inserted": 0, "notify": 0, "errors": [], "queries": []}
    seen_repos: set[str] = set()

    for query in _github_queries():
        search_q = f"{query} stars:>={min_stars} pushed:>={pushed_after} created:>={created_after}"
        url = (
            "https://api.github.com/search/repositories"
            f"?q={quote_plus(search_q)}&sort=stars&order=desc&per_page={max_results}"
        )
        stats["queries"].append(search_q)
        try:
            res = await client.get(url, headers={"Accept": "application/vnd.github+json"})
            res.raise_for_status()
            data = res.json()
            for repo in data.get("items", []):
                full_name = repo.get("full_name")
                if not full_name or full_name in seen_repos:
                    continue
                seen_repos.add(full_name)
                stats["seen"] += 1
                observed_ts = db.now_ms()
                velocity = _snapshot_velocity(full_name, int(repo.get("stargazers_count") or 0), observed_ts)
                score, reasons = _github_score(repo, velocity)
                _insert_repo_snapshot(repo, query, velocity)
                stars = int(repo.get("stargazers_count") or 0)
                forks = int(repo.get("forks_count") or 0)
                topics = repo.get("topics") or []
                original_description = repo.get("description") or "无描述"
                description = to_chinese(original_description, context="GitHub 项目描述", max_chars=180)
                per_day = velocity.get("stars_per_day")
                delta_24h = velocity.get("delta_24h")
                delta_7d = velocity.get("delta_7d")
                trend_line = (
                    f"实测增速：{per_day} star/天；24h 增量：{delta_24h}；7d 增量：{delta_7d}。"
                    if per_day is not None else "首次观察，先用项目年龄、star 基数和最近活跃度估算动量。"
                )
                content = (
                    f"{description}\n\n"
                    f"Stars：{stars}；Forks：{forks}；主要语言：{repo.get('language') or '未知'}。\n"
                    f"{trend_line}\n"
                    f"主题：{', '.join(chinese_tags(topics[:10])) or '暂无'}。\n"
                    f"雷达查询：{to_chinese(query, context='GitHub 搜索词', max_chars=80)}。\n"
                    f"入选原因：{'；'.join(reasons)}。"
                )
                triage = "notify" if score >= 0.76 else "digest" if score >= 0.46 else "ignore"
                item = RawItem(
                    source="intel:github",
                    domain="business",
                    kind="github_repo",
                    title=f"{full_name} · GitHub 项目雷达",
                    content=content,
                    url=repo.get("html_url") or "",
                    meta={
                        "repo": full_name,
                        "query": query,
                        "stars": stars,
                        "forks": forks,
                        "language": repo.get("language"),
                        "topics": topics,
                        "display_topics": chinese_tags(topics),
                        "original_description": original_description,
                        "display_description": description,
                        "momentum_score": round(score, 3),
                        "velocity": velocity,
                        "reasons": reasons,
                        "created_at": repo.get("created_at"),
                        "pushed_at": repo.get("pushed_at"),
                    },
                )
                event_id = db.insert_event(
                    source=item.source,
                    domain=item.domain,
                    kind=item.kind,
                    title=item.title,
                    content=item.content,
                    url=item.url,
                    meta=item.meta,
                    dedup_key=f"github:{full_name}:{_event_day()}",
                )
                if event_id is None:
                    continue
                stats["inserted"] += 1
                remember_event(event_id, f"{item.title}\n{item.content[:900]}")
                db.insert_judgment(
                    event_id=event_id,
                    score=round(score, 3),
                    take="这个 GitHub 项目值得进入雷达：" + "；".join(reasons[:4]),
                    triage=triage,
                    reasons=reasons,
                )
                if triage == "notify":
                    stats["notify"] += 1
                    await hub.push({
                        "type": "notify",
                        "source": "GitHub Radar",
                        "event_id": event_id,
                        "title": item.title,
                        "take": "；".join(reasons[:3]),
                        "url": item.url,
                        "score": round(score, 3),
                    })
        except Exception as exc:
            stats["errors"].append({"query": query, "error": str(exc)})
    return stats


async def run_intelligence_scan(*, include_rss: bool = True, include_web: bool = True,
                                include_github: bool = True) -> dict:
    seed_defaults()
    started = _now_iso()
    stats: dict[str, Any] = {"started_at": started, "rss": None, "web": None, "github": None}
    async with httpx.AsyncClient(
        timeout=18,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        trust_env=False,
    ) as client:
        if include_rss:
            stats["rss"] = await _scan_rss_sources(client)
        if include_web:
            stats["web"] = await _scan_web_sources(client)
        if include_github:
            stats["github"] = await _scan_github(client)
    stats["finished_at"] = _now_iso()
    return stats


def github_radar(limit: int = 24) -> list[dict]:
    seed_defaults()
    with db.conn() as c:
        rows = c.execute(
            """
            WITH latest AS (
              SELECT repo_full_name, MAX(observed_ts) AS observed_ts
              FROM github_repo_snapshots
              GROUP BY repo_full_name
            )
            SELECT s.*
            FROM github_repo_snapshots s
            JOIN latest l ON l.repo_full_name=s.repo_full_name AND l.observed_ts=s.observed_ts
            ORDER BY s.observed_ts DESC, s.stars DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    result = []
    with db.conn() as c:
        for row in rows:
            item = _rowdict(row)
            item["topics"] = _json_loads(item.get("topics"), [])
            velocity = _snapshot_velocity(item["repo_full_name"], int(item["stars"]), int(item["observed_ts"]))
            item.update(velocity)
            created = _parse_github_dt(item.get("created_at"))
            if created:
                age_days = max((datetime.now(timezone.utc) - created).days, 1)
                item["cold_stars_per_day"] = round(int(item["stars"]) / age_days, 2)
            else:
                item["cold_stars_per_day"] = None
            hist = c.execute(
                "SELECT stars, observed_ts FROM github_repo_snapshots WHERE repo_full_name=? ORDER BY observed_ts",
                (item["repo_full_name"],),
            ).fetchall()
            item["star_history"] = [{"ts": int(h["observed_ts"]), "stars": int(h["stars"])} for h in hist]
            result.append(item)
    return result


def recent_intelligence_events(hours: int = 72, limit: int = 80) -> list[dict]:
    since = int((time.time() - hours * 3600) * 1000)
    with db.conn() as c:
        rows = c.execute(
            """
            SELECT e.id AS event_id, e.ts, e.source, e.domain, e.kind, e.title, e.url, e.meta,
                   j.score, j.take, j.triage, j.reasons, j.analysis
            FROM events e
            LEFT JOIN judgments j ON j.event_id=e.id
            WHERE e.ts>=? AND (
                e.source LIKE 'intel:%' OR e.source LIKE 'rss:%'
                OR e.kind IN ('github_repo','web_change','news','market')
            )
            ORDER BY e.ts DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = _rowdict(row)
        item["meta"] = _json_loads(item.get("meta"), {})
        item["reasons"] = _json_loads(item.get("reasons"), [])
        item["analysis"] = _json_loads(item.get("analysis"), {}) or {}
        result.append(item)
    return result


def overview() -> dict:
    seed_defaults()
    events = recent_intelligence_events(hours=72, limit=60)
    github = github_radar(limit=18)
    sources_list = list_sources()
    targets = list_targets()
    return {
        "generated_at": int(time.time()),
        "targets": targets,
        "sources": sources_list,
        "events": events,
        "github": github,
        "stats": {
            "enabled_targets": sum(1 for t in targets if t.get("enabled")),
            "enabled_sources": sum(1 for s in sources_list if s.get("enabled")),
            "notify_events": sum(1 for e in events if e.get("triage") == "notify"),
            "github_repos": len(github),
        },
    }
