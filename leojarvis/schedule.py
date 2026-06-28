"""日程管理(问题1)。

区别于个人记事:日程是有时间、可提醒、可重复、独立存储的"日程表"。
- create/list/get/update/set_done/delete:基础 CRUD。
- due_reminders():调度器每分钟调,挑出到点该提醒的日程 → 标记已提醒 → 返回给推送层
  (桌面通知 + 应内 + iOS push 都复用这批载荷)。重复日程提醒后滚动到下一次发生时间。

存储在单一 SQLite 的 schedule 表(见 db.py SCHEMA)。零额外依赖。
"""

from __future__ import annotations

import uuid

from . import db

_DAY_MS = 86_400_000
_REPEATS = {"none", "daily", "weekly", "monthly"}


def _row(r) -> dict:
    d = dict(r)
    d["overdue"] = bool(d.get("start_ts") and d["start_ts"] < db.now_ms() and d.get("status") != "done")
    return d


def _writeback_after(sid: str, *, delete: bool = False) -> None:
    """日程增/改/删后,把这条写回 CalDAV(配了才写)。best-effort,绝不影响本地。

    已完成(status=done)的日程视作要从远端撤掉提醒 → 走 delete 分支。
    写回成功时把 remote_href/remote_etag 落库(便于诊断)。"""
    try:
        from . import caldav_writeback
        row = get(sid) if not delete else None
        if delete:
            # 删除场景:调用方已读过行并传 sid 对应内容;这里仅用 cal_uid 占位。
            row = {"cal_uid": f"{sid}@leojarvis", "id": sid}
            caldav_writeback.writeback(row, delete=True)
            return
        if not row:
            return
        do_delete = (row.get("status") == "done")
        r = caldav_writeback.writeback(row, delete=do_delete)
        # 同步写(block 路径)才有 ok;线程路径返回 queued,href 由后续诊断不强求。
        if r.get("ok") and (r.get("remote_href") or r.get("remote_etag")):
            with db.conn() as c:
                c.execute("UPDATE schedule SET remote_href=?, remote_etag=? WHERE id=?",
                          (r.get("remote_href") or "", r.get("remote_etag") or "", sid))
    except Exception:
        pass  # CalDAV 永远不能让本地写失败


def create(*, title: str, start_ts: int, remind_ts: int | None = None, note: str = "",
           repeat: str = "none", source: str = "manual", event_id: str | None = None) -> str | None:
    title = str(title or "").strip()
    if not title or not start_ts:
        return None
    repeat = repeat if repeat in _REPEATS else "none"
    db.init_db()
    now = db.now_ms()
    sid = uuid.uuid4().hex
    cal_uid = f"{sid}@leojarvis"
    with db.conn() as c:
        c.execute(
            """INSERT INTO schedule(id,title,note,start_ts,remind_ts,repeat,status,reminded,source,event_id,cal_uid,created_ts,updated_ts)
               VALUES(?,?,?,?,?,?,'pending',0,?,?,?,?,?)""",
            (sid, title, str(note or ""), int(start_ts), (int(remind_ts) if remind_ts else None),
             repeat, source, event_id, cal_uid, now, now),
        )
    _writeback_after(sid)
    return sid


def list_items(*, status: str = "", upcoming_hours: int = 0, limit: int = 200) -> list[dict]:
    db.init_db()
    q = "SELECT * FROM schedule WHERE 1=1"
    args: list = []
    if status:
        q += " AND status=?"; args.append(status)
    if upcoming_hours > 0:
        q += " AND start_ts <= ?"; args.append(db.now_ms() + upcoming_hours * 3_600_000)
    q += " ORDER BY start_ts ASC LIMIT ?"; args.append(limit)
    with db.conn() as c:
        return [_row(r) for r in c.execute(q, tuple(args)).fetchall()]


def get(sid: str) -> dict | None:
    db.init_db()
    with db.conn() as c:
        r = c.execute("SELECT * FROM schedule WHERE id=?", (sid,)).fetchone()
    return _row(r) if r else None


def update(sid: str, **fields) -> bool:
    allowed = {"title", "note", "start_ts", "remind_ts", "repeat", "status"}
    sets, args = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "repeat" and v not in _REPEATS:
            continue
        sets.append(f"{k}=?"); args.append(v)
    if not sets:
        return False
    # 改了时间/提醒 → 允许重新提醒。
    if "start_ts" in fields or "remind_ts" in fields:
        sets.append("reminded=0")
    sets.append("updated_ts=?"); args.append(db.now_ms())
    args.append(sid)
    db.init_db()
    with db.conn() as c:
        cur = c.execute(f"UPDATE schedule SET {', '.join(sets)} WHERE id=?", tuple(args))
    ok = cur.rowcount > 0
    if ok:
        _writeback_after(sid)  # 改时间/提醒/标题/完成态 → 同步到远端(done 会撤掉远端提醒)
    return ok


def set_done(sid: str, done: bool = True) -> bool:
    return update(sid, status="done" if done else "pending")


def delete(sid: str) -> bool:
    db.init_db()
    with db.conn() as c:
        cur = c.execute("DELETE FROM schedule WHERE id=?", (sid,))
    ok = cur.rowcount > 0
    if ok:
        _writeback_after(sid, delete=True)  # 本地删了 → 远端也删
    return ok


def _next_occurrence(start_ts: int, repeat: str) -> int | None:
    if repeat == "daily":
        return start_ts + _DAY_MS
    if repeat == "weekly":
        return start_ts + 7 * _DAY_MS
    if repeat == "monthly":
        return start_ts + 30 * _DAY_MS
    return None


def due_reminders(now_ms: int | None = None) -> list[dict]:
    """到点该提醒的日程:remind_ts 已过 + 未提醒 + 未完成。
    标记已提醒;重复日程滚动到下一次(start_ts/remind_ts 前移、reminded 清零)。
    返回提醒载荷列表,供 hub.push_event + iOS push 使用。"""
    db.init_db()
    now = now_ms if now_ms is not None else db.now_ms()
    out: list[dict] = []
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM schedule WHERE reminded=0 AND status!='done' AND remind_ts IS NOT NULL AND remind_ts<=?",
            (now,),
        ).fetchall()
        for r in rows:
            d = dict(r)
            out.append({
                "type": "notify", "source": "日程", "urgent": True,
                "title": d["title"], "schedule_id": d["id"],
                "start_ts": d["start_ts"], "note": d.get("note") or "",
                "body": f"日程提醒:{d['title']}",
            })
            nxt = _next_occurrence(int(d["start_ts"]), d.get("repeat") or "none")
            if nxt:
                # 重复日程:滚动到下一次,提醒间隔保持一致。
                gap = (int(d["remind_ts"]) - int(d["start_ts"])) if d.get("remind_ts") else 0
                c.execute("UPDATE schedule SET start_ts=?, remind_ts=?, reminded=0, updated_ts=? WHERE id=?",
                          (nxt, nxt + gap, now, d["id"]))
            else:
                c.execute("UPDATE schedule SET reminded=1, updated_ts=? WHERE id=?", (now, d["id"]))
    return out


def stats() -> dict:
    db.init_db()
    with db.conn() as c:
        pending = c.execute("SELECT COUNT(*) n FROM schedule WHERE status='pending'").fetchone()["n"]
        today_end = db.now_ms() + _DAY_MS
        today = c.execute("SELECT COUNT(*) n FROM schedule WHERE status='pending' AND start_ts<=?", (today_end,)).fetchone()["n"]
    return {"pending": pending, "today": today}
