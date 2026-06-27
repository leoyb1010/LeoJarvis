from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any

from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  ts INTEGER NOT NULL,
  source TEXT NOT NULL,
  domain TEXT,
  kind TEXT NOT NULL,
  title TEXT,
  content TEXT NOT NULL,
  url TEXT,
  meta TEXT,
  dedup_key TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup ON events(dedup_key);

CREATE TABLE IF NOT EXISTS judgments (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  score REAL NOT NULL,
  take TEXT,
  triage TEXT NOT NULL,
  reasons TEXT,
  FOREIGN KEY(event_id) REFERENCES events(id)
);
CREATE INDEX IF NOT EXISTS idx_judgments_triage ON judgments(triage, ts);
CREATE INDEX IF NOT EXISTS idx_judgments_event_id ON judgments(event_id);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  subject TEXT,
  statement TEXT NOT NULL,
  confidence REAL DEFAULT 0.7,
  salience REAL DEFAULT 0.5,
  created_ts INTEGER,
  updated_ts INTEGER,
  decay_after INTEGER,
  source_events TEXT,
  status TEXT DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status, updated_ts);

CREATE TABLE IF NOT EXISTS personal_notes (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  excerpt TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  source TEXT,
  source_url TEXT,
  source_title TEXT,
  project_name TEXT,
  import_meta TEXT,
  favorite INTEGER DEFAULT 0,
  pinned INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0,
  deleted_ts INTEGER,
  created_ts INTEGER,
  updated_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_personal_notes_updated ON personal_notes(archived, deleted_ts, pinned, updated_ts);
CREATE INDEX IF NOT EXISTS idx_personal_notes_created ON personal_notes(created_ts);

CREATE TABLE IF NOT EXISTS personal_note_attachments (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  file_name TEXT NOT NULL,
  mime_type TEXT,
  size INTEGER DEFAULT 0,
  path TEXT,
  summary TEXT,
  created_ts INTEGER,
  FOREIGN KEY(note_id) REFERENCES personal_notes(id)
);
CREATE INDEX IF NOT EXISTS idx_personal_note_attachments_note ON personal_note_attachments(note_id, created_ts);

CREATE TABLE IF NOT EXISTS personal_note_revisions (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  excerpt TEXT NOT NULL DEFAULT '',
  reason TEXT DEFAULT 'save',
  created_ts INTEGER,
  FOREIGN KEY(note_id) REFERENCES personal_notes(id)
);
CREATE INDEX IF NOT EXISTS idx_personal_note_revisions_note ON personal_note_revisions(note_id, created_ts);

CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  event_id TEXT,
  ts INTEGER,
  signal TEXT CHECK(signal IN ('important','useless')),
  FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS intelligence_targets (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  kind TEXT DEFAULT 'topic',
  query TEXT NOT NULL,
  enabled INTEGER DEFAULT 1,
  created_ts INTEGER,
  updated_ts INTEGER,
  UNIQUE(kind, query)
);
CREATE INDEX IF NOT EXISTS idx_intelligence_targets_enabled ON intelligence_targets(enabled, updated_ts);

CREATE TABLE IF NOT EXISTS intelligence_sources (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL CHECK(type IN ('rss','web')),
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  domain TEXT DEFAULT 'business',
  enabled INTEGER DEFAULT 1,
  last_scan_ts INTEGER,
  last_hash TEXT,
  meta TEXT,
  created_ts INTEGER,
  updated_ts INTEGER,
  UNIQUE(type, url)
);
CREATE INDEX IF NOT EXISTS idx_intelligence_sources_enabled ON intelligence_sources(enabled, type);

CREATE TABLE IF NOT EXISTS github_repo_snapshots (
  id TEXT PRIMARY KEY,
  repo_full_name TEXT NOT NULL,
  query TEXT,
  stars INTEGER NOT NULL,
  forks INTEGER,
  open_issues INTEGER,
  description TEXT,
  url TEXT,
  language TEXT,
  topics TEXT,
  license TEXT,
  created_at TEXT,
  pushed_at TEXT,
  updated_at TEXT,
  observed_ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_github_repo_snapshots_repo_ts ON github_repo_snapshots(repo_full_name, observed_ts);
CREATE INDEX IF NOT EXISTS idx_github_repo_snapshots_observed ON github_repo_snapshots(observed_ts);

CREATE TABLE IF NOT EXISTS device_heartbeats (
  device_id TEXT PRIMARY KEY,
  device_name TEXT NOT NULL,
  host_name TEXT,
  model TEXT,
  role TEXT DEFAULT 'mac',
  summary_json TEXT NOT NULL,
  last_seen_ts INTEGER NOT NULL,
  created_ts INTEGER,
  updated_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_device_heartbeats_seen ON device_heartbeats(last_seen_ts);
"""


import threading

_INIT_LOCK = threading.Lock()
_SCHEMA_READY = False


@contextmanager
def conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    # timeout=30 + busy_timeout 让并发写入排队等待而不是直接抛 "database is locked"。
    c = sqlite3.connect(DB_PATH, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    if not globals().get("_SCHEMA_READY", False):
        c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db(force: bool = False) -> None:
    # 整个进程只建一次表/迁移一次。之前每次 query/insert 都调用 init_db()，
    # 等于每次读都跑一遍 SCHEMA + 写一次 "UPDATE memories"，把数据库锁死、首页/系统页/情报页转圈。
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    with _INIT_LOCK:
        if _SCHEMA_READY and not force:
            return
        _init_db_impl()
        _SCHEMA_READY = True


def _init_db_impl() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        memory_cols = {r["name"] for r in c.execute("PRAGMA table_info(memories)").fetchall()}
        if "status" not in memory_cols:
            c.execute("ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'")
        missing_status = c.execute("SELECT COUNT(*) FROM memories WHERE status IS NULL OR status=''").fetchone()[0]
        if missing_status:
            c.execute("UPDATE memories SET status='active' WHERE status IS NULL OR status=''")
        # 超级 Jarvis P1：分层记忆 + 来源台账（可溯源/可遗忘）。
        #   layer      : fact(语义事实) | episode(情景) | pattern(行为规律) | entity(人物图谱) | event_text(旧)
        #   origin     : 这条记忆来自哪里（reflect / personal_data:<connector> / chat / feedback ...）
        #   source_ref : 原始来源标识（文件路径/消息id/连接器键），用于「按来源一键删除」被遗忘权
        for col, ddl in {
            "layer": "ALTER TABLE memories ADD COLUMN layer TEXT DEFAULT 'fact'",
            "origin": "ALTER TABLE memories ADD COLUMN origin TEXT",
            "source_ref": "ALTER TABLE memories ADD COLUMN source_ref TEXT",
        }.items():
            if col not in memory_cols:
                c.execute(ddl)
        # 旧行回填 layer：event_text 类型归入 episode，其余按 fact。
        c.execute("UPDATE memories SET layer='episode' WHERE (layer IS NULL OR layer='') AND type='event_text'")
        c.execute("UPDATE memories SET layer='fact' WHERE layer IS NULL OR layer=''")
        note_cols = {r["name"] for r in c.execute("PRAGMA table_info(personal_notes)").fetchall()}
        for col, ddl in {
            "source_url": "ALTER TABLE personal_notes ADD COLUMN source_url TEXT",
            "source_title": "ALTER TABLE personal_notes ADD COLUMN source_title TEXT",
            "project_name": "ALTER TABLE personal_notes ADD COLUMN project_name TEXT",
            "import_meta": "ALTER TABLE personal_notes ADD COLUMN import_meta TEXT",
        }.items():
            if col not in note_cols:
                c.execute(ddl)
        judgment_cols = {r["name"] for r in c.execute("PRAGMA table_info(judgments)").fetchall()}
        if "analysis" not in judgment_cols:
            c.execute("ALTER TABLE judgments ADD COLUMN analysis TEXT")
        device_cols = {r["name"] for r in c.execute("PRAGMA table_info(device_heartbeats)").fetchall()}
        if "role" not in device_cols:
            c.execute("ALTER TABLE device_heartbeats ADD COLUMN role TEXT DEFAULT 'mac'")


def now_ms() -> int:
    return int(time.time() * 1000)


def insert_event(*, source: str, kind: str, content: str, domain: str | None = None,
                 title: str | None = None, url: str | None = None,
                 meta: dict[str, Any] | None = None, dedup_key: str | None = None) -> str | None:
    init_db()
    eid = uuid.uuid4().hex
    key = dedup_key or eid
    try:
        with conn() as c:
            c.execute(
                """INSERT INTO events(id,ts,source,domain,kind,title,content,url,meta,dedup_key)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (eid, now_ms(), source, domain, kind, title, content, url,
                 json.dumps(meta or {}, ensure_ascii=False), key),
            )
        return eid
    except sqlite3.IntegrityError:
        return None


def insert_judgment(*, event_id: str, score: float, take: str, triage: str,
                    reasons: list[str] | None = None,
                    analysis: dict[str, Any] | None = None) -> str:
    init_db()
    jid = uuid.uuid4().hex
    with conn() as c:
        c.execute(
            """INSERT INTO judgments(id,event_id,ts,score,take,triage,reasons,analysis)
               VALUES(?,?,?,?,?,?,?,?)""",
            (jid, event_id, now_ms(), score, take, triage,
             json.dumps(reasons or [], ensure_ascii=False),
             json.dumps(analysis, ensure_ascii=False) if analysis else None),
        )
    return jid


def insert_memory(statement: str, *, memory_type: str = "semantic", subject: str | None = None,
                  confidence: float = 0.7, salience: float = 0.5,
                  source_events: list[str] | None = None, status: str = "pending",
                  layer: str = "fact", origin: str | None = None, source_ref: str | None = None) -> str:
    init_db()
    mid = uuid.uuid4().hex
    ts = now_ms()
    with conn() as c:
        c.execute(
            """INSERT INTO memories(id,type,subject,statement,confidence,salience,created_ts,updated_ts,source_events,status,layer,origin,source_ref)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, memory_type, subject, statement, confidence, salience, ts, ts,
             json.dumps(source_events or [], ensure_ascii=False), status, layer, origin, source_ref),
        )
    return mid


def query_events(since_ms: int, limit: int = 500) -> list[sqlite3.Row]:
    init_db()
    with conn() as c:
        return c.execute(
            "SELECT * FROM events WHERE ts>=? ORDER BY ts DESC LIMIT ?",
            (since_ms, limit),
        ).fetchall()


def list_memories(limit: int = 100) -> list[sqlite3.Row]:
    init_db()
    with conn() as c:
        return c.execute(
            "SELECT * FROM memories WHERE status='active' ORDER BY salience DESC, updated_ts DESC LIMIT ?",
            (limit,),
        ).fetchall()


def list_pending_memories(limit: int = 100) -> list[sqlite3.Row]:
    init_db()
    with conn() as c:
        return c.execute(
            "SELECT * FROM memories WHERE status IN ('pending','later') ORDER BY status='pending' DESC, salience DESC, created_ts DESC LIMIT ?",
            (limit,),
        ).fetchall()


def update_memory_status(memory_id: str, status: str) -> bool:
    if status not in {"active", "rejected", "later"}:
        raise ValueError("invalid memory status")
    init_db()
    with conn() as c:
        cur = c.execute(
            "UPDATE memories SET status=?, updated_ts=? WHERE id=? AND status IN ('pending','later')",
            (status, now_ms(), memory_id),
        )
    return cur.rowcount > 0


# ---------- 超级 Jarvis：分层记忆查询 / 反馈强化 / 被遗忘权 ----------

def list_memories_by_layer(layers: list[str] | None = None, limit: int = 100,
                           status: str = "active") -> list[sqlite3.Row]:
    """按记忆层（fact/episode/pattern/entity）取记忆，供 RAG 加权检索与画像合成。"""
    init_db()
    with conn() as c:
        if layers:
            ph = ",".join("?" for _ in layers)
            return c.execute(
                f"SELECT * FROM memories WHERE status=? AND layer IN ({ph}) "
                f"ORDER BY salience DESC, updated_ts DESC LIMIT ?",
                (status, *layers, limit),
            ).fetchall()
        return c.execute(
            "SELECT * FROM memories WHERE status=? ORDER BY salience DESC, updated_ts DESC LIMIT ?",
            (status, limit),
        ).fetchall()


def memory_layer_counts() -> dict[str, int]:
    """各层活跃记忆条数（供 /metrics 展示「Jarvis 现在记得多少」）。"""
    init_db()
    with conn() as c:
        rows = c.execute(
            "SELECT layer, COUNT(*) AS n FROM memories WHERE status='active' GROUP BY layer"
        ).fetchall()
    out: dict[str, int] = {}
    for r in rows:
        out[str(r["layer"] or "fact")] = int(r["n"])
    with conn() as c:
        out["pending"] = int(c.execute(
            "SELECT COUNT(*) FROM memories WHERE status IN ('pending','later')"
        ).fetchone()[0])
    return out


def adjust_memory(memory_id: str, *, salience_delta: float = 0.0, confidence_delta: float = 0.0) -> bool:
    """反馈回流：采纳→加权，忽略→衰减。salience/confidence 钳到 [0,1]。"""
    init_db()
    with conn() as c:
        cur = c.execute(
            """UPDATE memories
               SET salience = MAX(0.0, MIN(1.0, salience + ?)),
                   confidence = MAX(0.0, MIN(1.0, confidence + ?)),
                   updated_ts = ?
               WHERE id = ?""",
            (salience_delta, confidence_delta, now_ms(), memory_id),
        )
    return cur.rowcount > 0


def delete_memories_by_source(source_ref: str) -> int:
    """被遗忘权：删除某来源（文件/消息/连接器键）衍生的全部记忆。返回删除条数。
    向量库里的同 id 行由调用方（memory.store）一并清理。"""
    init_db()
    if not source_ref:
        return 0
    with conn() as c:
        ids = [r["id"] for r in c.execute(
            "SELECT id FROM memories WHERE source_ref=?", (source_ref,)
        ).fetchall()]
        cur = c.execute("DELETE FROM memories WHERE source_ref=?", (source_ref,))
    deleted = cur.rowcount
    try:
        from .memory import store as _store
        _store.forget_vectors(ids)
    except Exception:
        pass
    return deleted


def memory_health_sweep(*, min_confidence: float = 0.2, stale_days: int = 120) -> dict[str, int]:
    """记忆体检（P5）：低置信或长期未更新的活跃记忆降级归档（status=archived），防「自信地记错」。"""
    init_db()
    cutoff = now_ms() - int(stale_days) * 86_400_000
    with conn() as c:
        cur = c.execute(
            """UPDATE memories SET status='archived', updated_ts=?
               WHERE status='active' AND (confidence < ? OR updated_ts < ?)""",
            (now_ms(), min_confidence, cutoff),
        )
    return {"archived": cur.rowcount}


def upsert_device_heartbeat(summary: dict[str, Any]) -> dict[str, Any]:
    init_db()
    ts = int(summary.get("last_seen_ts") or summary.get("generated_at") or time.time())
    now = now_ms()
    device_id = str(summary.get("device_id") or "").strip()
    if not device_id:
        raise ValueError("device_id required")
    device_name = str(summary.get("device_name") or device_id)
    host_name = str(summary.get("host_name") or "")
    model = str(summary.get("model") or "")
    role = str(summary.get("role") or "mac")
    payload = json.dumps(summary, ensure_ascii=False)
    with conn() as c:
        exists = c.execute("SELECT created_ts FROM device_heartbeats WHERE device_id=?", (device_id,)).fetchone()
        created = exists["created_ts"] if exists else now
        c.execute(
            """INSERT INTO device_heartbeats(device_id,device_name,host_name,model,role,summary_json,last_seen_ts,created_ts,updated_ts)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(device_id) DO UPDATE SET
                 device_name=excluded.device_name,
                 host_name=excluded.host_name,
                 model=excluded.model,
                 role=excluded.role,
                 summary_json=excluded.summary_json,
                 last_seen_ts=excluded.last_seen_ts,
                 updated_ts=excluded.updated_ts""",
            (device_id, device_name, host_name, model, role, payload, ts, created, now),
        )
    return summary


def list_device_heartbeats(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM device_heartbeats ORDER BY last_seen_ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            data = json.loads(r["summary_json"] or "{}")
        except json.JSONDecodeError:
            data = {}
        data.setdefault("device_id", r["device_id"])
        data.setdefault("device_name", r["device_name"])
        data.setdefault("host_name", r["host_name"])
        data.setdefault("model", r["model"])
        data.setdefault("role", r["role"])
        data.setdefault("last_seen_ts", r["last_seen_ts"])
        out.append(data)
    return out


def delete_device_heartbeat(device_id: str) -> None:
    init_db()
    with conn() as c:
        c.execute("DELETE FROM device_heartbeats WHERE device_id=?", (device_id,))


def prune_old_data(
    *,
    snapshot_days: int = 90,
    event_days: int = 90,
    revisions_per_note: int = 20,
) -> dict[str, int]:
    """给会无限增长的表做保留窗口（events / judgments / 快照 / 笔记历史版本）。

    - github_repo_snapshots：删 snapshot_days 之前的旧快照，但每个仓库永远保留最新一条
      （算 24h/7d 星标增量要用历史基线）。
    - events / judgments：删 event_days 之前的旧事件及其判断，但**保留被反馈或长期记忆引用的事件**
      （feedback.event_id / memories.source_events），避免删掉用户标注过或已沉淀成记忆的来源。
    - personal_note_revisions：每条笔记只保留最近 revisions_per_note 个历史版本。
    """
    init_db()
    snap_cutoff = now_ms() - int(snapshot_days) * 86_400_000
    evt_cutoff = now_ms() - int(event_days) * 86_400_000
    removed = {"snapshots": 0, "events": 0, "judgments": 0, "revisions": 0}
    with conn() as c:
        cur = c.execute(
            """
            DELETE FROM github_repo_snapshots
            WHERE observed_ts < ?
              AND id NOT IN (
                SELECT s.id FROM github_repo_snapshots s
                JOIN (
                  SELECT repo_full_name, MAX(observed_ts) AS m
                  FROM github_repo_snapshots GROUP BY repo_full_name
                ) t ON s.repo_full_name = t.repo_full_name AND s.observed_ts = t.m
              )
            """,
            (snap_cutoff,),
        )
        removed["snapshots"] = cur.rowcount

        # 被记忆引用的事件 id（source_events 是 JSON 数组文本，逐行收集）
        referenced: set[str] = set()
        for row in c.execute("SELECT source_events FROM memories WHERE source_events IS NOT NULL"):
            raw = row[0] if not isinstance(row, dict) else row.get("source_events")
            if not raw:
                continue
            try:
                referenced.update(str(x) for x in json.loads(raw))
            except Exception:
                continue

        # 待删旧事件：早于窗口、且不被 feedback 引用、且不被记忆引用
        old_ids = [
            (r[0] if not isinstance(r, dict) else r["id"])
            for r in c.execute(
                """
                SELECT e.id FROM events e
                WHERE e.ts < ?
                  AND e.id NOT IN (SELECT event_id FROM feedback WHERE event_id IS NOT NULL)
                """,
                (evt_cutoff,),
            )
        ]
        old_ids = [eid for eid in old_ids if eid not in referenced]
        for batch_start in range(0, len(old_ids), 500):
            chunk = old_ids[batch_start:batch_start + 500]
            ph = ",".join("?" for _ in chunk)
            jc = c.execute(f"DELETE FROM judgments WHERE event_id IN ({ph})", chunk)
            removed["judgments"] += jc.rowcount
            ec = c.execute(f"DELETE FROM events WHERE id IN ({ph})", chunk)
            removed["events"] += ec.rowcount

        # 每条笔记只保留最近 revisions_per_note 个版本
        rc = c.execute(
            """
            DELETE FROM personal_note_revisions
            WHERE id IN (
              SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                  PARTITION BY note_id ORDER BY created_ts DESC
                ) AS rn FROM personal_note_revisions
              ) WHERE rn > ?
            )
            """,
            (int(revisions_per_note),),
        )
        removed["revisions"] = rc.rowcount
    return removed


def vacuum() -> bool:
    """回收已删除行占用的磁盘空间（VACUUM 会短暂全库加锁，调用方应控制频率，别每天跑）。"""
    init_db()
    try:
        with conn() as c:
            c.execute("VACUUM")
        return True
    except Exception:
        return False
