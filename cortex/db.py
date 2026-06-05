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

CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  event_id TEXT,
  ts INTEGER,
  signal TEXT CHECK(signal IN ('important','useless')),
  FOREIGN KEY(event_id) REFERENCES events(id)
);
"""


@contextmanager
def conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


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
                    reasons: list[str] | None = None) -> str:
    init_db()
    jid = uuid.uuid4().hex
    with conn() as c:
        c.execute(
            """INSERT INTO judgments(id,event_id,ts,score,take,triage,reasons)
               VALUES(?,?,?,?,?,?,?)""",
            (jid, event_id, now_ms(), score, take, triage,
             json.dumps(reasons or [], ensure_ascii=False)),
        )
    return jid


def insert_memory(statement: str, *, memory_type: str = "semantic", subject: str | None = None,
                  confidence: float = 0.7, salience: float = 0.5,
                  source_events: list[str] | None = None) -> str:
    init_db()
    mid = uuid.uuid4().hex
    ts = now_ms()
    with conn() as c:
        c.execute(
            """INSERT INTO memories(id,type,subject,statement,confidence,salience,created_ts,updated_ts,source_events,status)
               VALUES(?,?,?,?,?,?,?,?,?, 'active')""",
            (mid, memory_type, subject, statement, confidence, salience, ts, ts,
             json.dumps(source_events or [], ensure_ascii=False)),
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
