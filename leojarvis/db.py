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

-- WorkDock 合并 M2：信息转任务收件箱。task 从 events+judgments 自动抽，带来源与置信度。
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  action TEXT,                       -- reply/review/create/follow_up/approve/prepare...
  object TEXT,                       -- 对象，如「活动复盘文档」
  owner TEXT,                        -- 默认本人
  due TEXT,                          -- ISO 日期（可空）
  priority TEXT DEFAULT 'P2',        -- P0/P1/P2
  confidence REAL DEFAULT 0.5,       -- AI 抽取置信度 0..1
  inbox_state TEXT DEFAULT 'unconfirmed',  -- unconfirmed/confirmed/done/ignored
  risk_level TEXT DEFAULT 'low',     -- low/medium/high
  origin TEXT,                       -- 来源类型 email/im/intel/manual...
  event_id TEXT,                     -- 关联事件（来源台账）
  context_preview TEXT,              -- 原文/上下文预览
  suggestion TEXT,                   -- 系统处理建议
  tags TEXT DEFAULT '[]',
  created_ts INTEGER,
  updated_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(inbox_state, priority, created_ts);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_event ON tasks(event_id);

-- P1 Email 腔理缓存：每封邮件的 AI 摘要/标签/actionable 判定，按 event_id 缓存避免重判。
CREATE TABLE IF NOT EXISTS email_triage (
  event_id TEXT PRIMARY KEY,
  summary TEXT,
  tags TEXT DEFAULT '[]',         -- ["紧急","财务",...]
  actionable INTEGER DEFAULT 0,   -- 0/1
  action TEXT,                    -- reply/review/...（actionable 时）
  object TEXT,
  due TEXT,
  task_title TEXT,                -- actionable 时抽出的待办标题
  reply_draft TEXT,              -- 可选回复草稿(只生成不自动发)
  model_used TEXT,
  created_ts INTEGER
);

-- P3 定时/事件触发的 agent 任务。trigger=interval(每 N 分)/cron(每天 HH:MM)/event(事件计数到阈值)。
CREATE TABLE IF NOT EXISTS scheduled_tasks (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  prompt TEXT NOT NULL,           -- 给 agent 的指令
  trigger TEXT NOT NULL,          -- interval / cron / event
  interval_minutes INTEGER,       -- trigger=interval
  cron_hour INTEGER, cron_minute INTEGER,  -- trigger=cron
  trigger_event TEXT,             -- trigger=event 的事件名(如 email_actionable)
  trigger_count INTEGER DEFAULT 1,-- 事件累计到几次才触发
  trigger_counter INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',    -- active / paused
  last_run INTEGER, next_run INTEGER,
  last_result TEXT,
  created_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sched_status ON scheduled_tasks(status, trigger);

-- 日程(问题1):真正的日程管理,区别于记事——有开始时间、可设提醒、独立存储、可重复。
CREATE TABLE IF NOT EXISTS schedule (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  note TEXT DEFAULT '',
  start_ts INTEGER NOT NULL,        -- 日程发生时间(毫秒)
  remind_ts INTEGER,                -- 提醒时间(毫秒);NULL=不提醒
  repeat TEXT DEFAULT 'none',       -- none / daily / weekly / monthly
  status TEXT DEFAULT 'pending',    -- pending / done
  reminded INTEGER DEFAULT 0,       -- 提醒是否已发(去重;repeat 滚动后清零)
  source TEXT DEFAULT 'manual',     -- manual / inbox / calendar
  event_id TEXT,                    -- 来源事件(从收件箱/日历转入时)
  cal_uid TEXT,                     -- CalDAV VEVENT 的稳定 UID(<id>@leojarvis),用于增改删round-trip
  remote_href TEXT,                 -- CalDAV 资源 href(写回成功后记录,便于诊断/未来冲突检测)
  remote_etag TEXT,                 -- CalDAV 资源 etag
  created_ts INTEGER, updated_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_schedule_start ON schedule(status, start_ts);
CREATE INDEX IF NOT EXISTS idx_schedule_remind ON schedule(reminded, remind_ts);

-- B 技能库:agent 从成功的多步运行里自动提炼可复用 SKILL,关键词检索后注入(像记忆 RAG)。
CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT 'general',
  when_to_use TEXT NOT NULL, body TEXT NOT NULL, keywords TEXT DEFAULT '[]',
  source TEXT DEFAULT 'distill',           -- distill | teacher | manual
  use_count INTEGER DEFAULT 0, success_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active', created_ts INTEGER, updated_ts INTEGER );
CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status, updated_ts);

-- D 版本化文档:每次 edit 把旧内容快照进 document_versions(仿 personal_note_revisions)。
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
  kind TEXT DEFAULT 'doc', tags TEXT DEFAULT '[]', created_ts INTEGER, updated_ts INTEGER );
CREATE TABLE IF NOT EXISTS document_versions (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, content TEXT NOT NULL,
  reason TEXT DEFAULT 'edit', created_ts INTEGER );
CREATE INDEX IF NOT EXISTS idx_docver_doc ON document_versions(document_id, created_ts);

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
        # 日程 CalDAV 写回:记录远端 VEVENT 标识,支持增改删 round-trip。
        sched_cols = {r["name"] for r in c.execute("PRAGMA table_info(schedule)").fetchall()}
        for col, ddl in {
            "cal_uid": "ALTER TABLE schedule ADD COLUMN cal_uid TEXT",
            "remote_href": "ALTER TABLE schedule ADD COLUMN remote_href TEXT",
            "remote_etag": "ALTER TABLE schedule ADD COLUMN remote_etag TEXT",
        }.items():
            if col not in sched_cols:
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


# ---------- WorkDock 合并 M2：任务收件箱 ----------

def upsert_task(*, event_id: str | None, title: str, action: str | None = None,
                object: str | None = None, owner: str | None = None, due: str | None = None,
                priority: str = "P2", confidence: float = 0.5, risk_level: str = "low",
                origin: str | None = None, context_preview: str | None = None,
                suggestion: str | None = None, tags: list[str] | None = None,
                inbox_state: str = "unconfirmed") -> str | None:
    """插入或更新一条任务。按 event_id 去重（同一事件不重复建任务）。
    已被用户处理过(confirmed/done/ignored)的任务不被自动重建覆盖。返回 task id 或 None(跳过)。"""
    init_db()
    ts = now_ms()
    with conn() as c:
        if event_id:
            existing = c.execute("SELECT id, inbox_state FROM tasks WHERE event_id=?", (event_id,)).fetchone()
            if existing:
                # 用户已表态的不动；仍是 unconfirmed 的可刷新内容。
                if str(existing["inbox_state"]) != "unconfirmed":
                    return None
                c.execute(
                    """UPDATE tasks SET title=?,action=?,object=?,owner=?,due=?,priority=?,
                       confidence=?,risk_level=?,origin=?,context_preview=?,suggestion=?,tags=?,updated_ts=?
                       WHERE id=?""",
                    (title, action, object, owner, due, priority, confidence, risk_level, origin,
                     context_preview, suggestion, json.dumps(tags or [], ensure_ascii=False), ts, existing["id"]),
                )
                return existing["id"]
        tid = uuid.uuid4().hex
        c.execute(
            """INSERT INTO tasks(id,title,action,object,owner,due,priority,confidence,inbox_state,
               risk_level,origin,event_id,context_preview,suggestion,tags,created_ts,updated_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, title, action, object, owner, due, priority, confidence, inbox_state, risk_level,
             origin, event_id, context_preview, suggestion, json.dumps(tags or [], ensure_ascii=False), ts, ts),
        )
        return tid


def list_tasks(states: list[str] | None = None, limit: int = 100) -> list[sqlite3.Row]:
    init_db()
    with conn() as c:
        if states:
            ph = ",".join("?" for _ in states)
            return c.execute(
                f"SELECT * FROM tasks WHERE inbox_state IN ({ph}) "
                f"ORDER BY (priority='P0') DESC,(priority='P1') DESC, created_ts DESC LIMIT ?",
                (*states, limit),
            ).fetchall()
        return c.execute(
            "SELECT * FROM tasks ORDER BY created_ts DESC LIMIT ?", (limit,),
        ).fetchall()


def get_task(task_id: str) -> sqlite3.Row | None:
    init_db()
    with conn() as c:
        return c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()


def set_task_state(task_id: str, inbox_state: str) -> bool:
    if inbox_state not in {"unconfirmed", "confirmed", "done", "ignored"}:
        raise ValueError("invalid inbox_state")
    init_db()
    with conn() as c:
        cur = c.execute("UPDATE tasks SET inbox_state=?, updated_ts=? WHERE id=?",
                        (inbox_state, now_ms(), task_id))
    return cur.rowcount > 0


def task_state_counts() -> dict[str, int]:
    init_db()
    with conn() as c:
        rows = c.execute("SELECT inbox_state, COUNT(*) AS n FROM tasks GROUP BY inbox_state").fetchall()
    return {str(r["inbox_state"]): int(r["n"]) for r in rows}


# ---------- P1 Email 腔理缓存 ----------

def get_email_triage(event_id: str) -> sqlite3.Row | None:
    init_db()
    with conn() as c:
        return c.execute("SELECT * FROM email_triage WHERE event_id=?", (event_id,)).fetchone()


def upsert_email_triage(*, event_id: str, summary: str = "", tags: list[str] | None = None,
                        actionable: bool = False, action: str | None = None, object: str | None = None,
                        due: str | None = None, task_title: str | None = None,
                        reply_draft: str | None = None, model_used: str = "") -> None:
    init_db()
    with conn() as c:
        c.execute(
            """INSERT INTO email_triage(event_id,summary,tags,actionable,action,object,due,task_title,reply_draft,model_used,created_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                 summary=excluded.summary, tags=excluded.tags, actionable=excluded.actionable,
                 action=excluded.action, object=excluded.object, due=excluded.due,
                 task_title=excluded.task_title, reply_draft=excluded.reply_draft,
                 model_used=excluded.model_used, created_ts=excluded.created_ts""",
            (event_id, summary, json.dumps(tags or [], ensure_ascii=False), 1 if actionable else 0,
             action, object, due, task_title, reply_draft, model_used, now_ms()),
        )


# ---------- P3 定时/事件触发 agent 任务 ----------

def create_scheduled_task(*, name: str, prompt: str, trigger: str, interval_minutes: int | None = None,
                          cron_hour: int | None = None, cron_minute: int | None = None,
                          trigger_event: str | None = None, trigger_count: int = 1) -> str:
    if trigger not in {"interval", "cron", "event"}:
        raise ValueError("trigger must be interval/cron/event")
    init_db()
    tid = uuid.uuid4().hex
    nxt = None
    if trigger == "interval" and interval_minutes:
        nxt = now_ms() + int(interval_minutes) * 60_000
    with conn() as c:
        c.execute(
            """INSERT INTO scheduled_tasks(id,name,prompt,trigger,interval_minutes,cron_hour,cron_minute,
               trigger_event,trigger_count,trigger_counter,status,next_run,created_ts)
               VALUES(?,?,?,?,?,?,?,?,?,0,'active',?,?)""",
            (tid, name, prompt, trigger, interval_minutes, cron_hour, cron_minute,
             trigger_event, max(1, int(trigger_count)), nxt, now_ms()),
        )
    return tid


def list_scheduled_tasks(status: str | None = None) -> list[sqlite3.Row]:
    init_db()
    with conn() as c:
        if status:
            return c.execute("SELECT * FROM scheduled_tasks WHERE status=? ORDER BY created_ts DESC", (status,)).fetchall()
        return c.execute("SELECT * FROM scheduled_tasks ORDER BY created_ts DESC").fetchall()


def get_scheduled_task(task_id: str) -> sqlite3.Row | None:
    init_db()
    with conn() as c:
        return c.execute("SELECT * FROM scheduled_tasks WHERE id=?", (task_id,)).fetchone()


def set_scheduled_task_status(task_id: str, status: str) -> bool:
    if status not in {"active", "paused", "deleted"}:
        raise ValueError("bad status")
    init_db()
    with conn() as c:
        if status == "deleted":
            cur = c.execute("DELETE FROM scheduled_tasks WHERE id=?", (task_id,))
        else:
            cur = c.execute("UPDATE scheduled_tasks SET status=? WHERE id=?", (status, task_id))
    return cur.rowcount > 0


def update_scheduled_task(task_id: str, **fields) -> bool:
    """更新定时任务字段(name/prompt/cron_hour/cron_minute/interval_minutes/status/trigger_event/trigger_count)。"""
    allowed = {"name", "prompt", "cron_hour", "cron_minute", "interval_minutes",
               "status", "trigger_event", "trigger_count", "next_run"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return False
    init_db()
    cols = ", ".join(f"{k}=?" for k in sets)
    with conn() as c:
        cur = c.execute(f"UPDATE scheduled_tasks SET {cols} WHERE id=?", (*sets.values(), task_id))
    return cur.rowcount > 0


def mark_scheduled_run(task_id: str, result: str, *, next_run: int | None = None) -> None:
    init_db()
    with conn() as c:
        c.execute("UPDATE scheduled_tasks SET last_run=?, next_run=?, last_result=?, trigger_counter=0 WHERE id=?",
                  (now_ms(), next_run, (result or "")[:1000], task_id))


def reschedule_task(task_id: str, next_run: int) -> None:
    """只重排下次执行时间，不动 last_result/last_run。
    interval 任务跑完后由调度器调用：_run_task_row 已写入本轮 summary，这里只补 next_run，
    避免用执行前的旧快照 last_result 覆盖掉刚写的结果。"""
    init_db()
    with conn() as c:
        c.execute("UPDATE scheduled_tasks SET next_run=? WHERE id=?", (next_run, task_id))


def due_interval_tasks() -> list[sqlite3.Row]:
    """到点的 interval/cron 任务(cron 的到点判断在调度器里做粗粒度)。"""
    init_db()
    now = now_ms()
    with conn() as c:
        return c.execute(
            "SELECT * FROM scheduled_tasks WHERE status='active' AND trigger='interval' "
            "AND next_run IS NOT NULL AND next_run<=?", (now,),
        ).fetchall()


def bump_event_counter(event_name: str) -> list[sqlite3.Row]:
    """事件计数 +1;返回**刚好到阈值、应触发**的任务(并已重置计数)。"""
    init_db()
    fired: list[sqlite3.Row] = []
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM scheduled_tasks WHERE status='active' AND trigger='event' AND trigger_event=?",
            (event_name,),
        ).fetchall()
        for r in rows:
            cnt = int(r["trigger_counter"] or 0) + 1
            if cnt >= int(r["trigger_count"] or 1):
                c.execute("UPDATE scheduled_tasks SET trigger_counter=0 WHERE id=?", (r["id"],))
                fired.append(r)
            else:
                c.execute("UPDATE scheduled_tasks SET trigger_counter=? WHERE id=?", (cnt, r["id"]))
    return fired


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
