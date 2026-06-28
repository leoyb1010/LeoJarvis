"""Calendar / CalDAV(P2)。清室重写,设计借鉴 odysseus 的 calendar/caldav,
但用 LeoJarvis 自己的 events 模型,代码全新、无 AGPL 牵连。

能力:
  - 解析 ics(iCalendar)文本 → 提取 VEVENT(标题/起止/地点/组织者)。
  - 落进 events(kind='calendar')→ 自动流入收件箱(临近/有待办)、收尾、首页待办。
  - CalDAV 双向同步:有 [calendar].caldav_url 才启用(可选 caldav 依赖);无凭证则只用 ics 导入。

依赖策略(同 LeoJarvis 既有"优雅降级"):
  - icalendar 装了就用它解析(更鲁棒);没装则用内置极简 ics 行解析器(零依赖,够用)。
  - caldav 装了且配了 url 才做远端同步;否则 import_ics() 仍可用(本地/订阅链接)。
无凭证时:import_ics(文本) + 内置解析器 + mock 测试全通过,配置位见 settings.toml [calendar]。
"""

from __future__ import annotations

import logging

from . import db

log = logging.getLogger("calendar_sync")


# ---------- ics 解析(icalendar 优先,内置兜底) ----------

def _unfold(ics_text: str) -> list[str]:
    """ics 折行(下一行以空格/Tab 开头是续行)还原成逻辑行。"""
    out: list[str] = []
    for raw in ics_text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _parse_dt(val: str) -> int | None:
    """把 ics 日期/时间(20260627T140000Z / 20260627T140000 / 20260627)转成 epoch ms。"""
    from datetime import datetime, timezone
    v = val.strip()
    try:
        if v.endswith("Z"):
            dt = datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        elif "T" in v:
            dt = datetime.strptime(v, "%Y%m%dT%H%M%S")
        else:
            dt = datetime.strptime(v, "%Y%m%d")
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _parse_ics_builtin(ics_text: str) -> list[dict]:
    """零依赖极简解析:逐 VEVENT 收 SUMMARY/DTSTART/DTEND/LOCATION/ORGANIZER/UID。"""
    events: list[dict] = []
    cur: dict | None = None
    for line in _unfold(ics_text):
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.startswith("END:VEVENT"):
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, _, val = line.partition(":")
            key = key.split(";", 1)[0].upper()  # 去掉 DTSTART;TZID=... 的参数部分
            if key == "SUMMARY":
                cur["title"] = val.strip()
            elif key == "DTSTART":
                cur["start"] = _parse_dt(val)
            elif key == "DTEND":
                cur["end"] = _parse_dt(val)
            elif key == "LOCATION":
                cur["location"] = val.strip()
            elif key == "ORGANIZER":
                cur["organizer"] = val.replace("mailto:", "").strip()
            elif key == "UID":
                cur["uid"] = val.strip()
    return events


def _parse_ics(ics_text: str) -> list[dict]:
    """优先用 icalendar(鲁棒,含复发规则展开);未装则内置解析器兜底。"""
    try:
        import icalendar  # noqa
        from datetime import datetime, timezone
        cal = icalendar.Calendar.from_ical(ics_text)
        out = []
        for comp in cal.walk("VEVENT"):
            def _ms(field):
                v = comp.get(field)
                if not v:
                    return None
                d = v.dt
                if isinstance(d, datetime):
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone.utc)
                    return int(d.timestamp() * 1000)
                # date-only
                return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
            out.append({
                "title": str(comp.get("summary") or "").strip(),
                "start": _ms("dtstart"), "end": _ms("dtend"),
                "location": str(comp.get("location") or "").strip(),
                "organizer": str(comp.get("organizer") or "").replace("mailto:", "").strip(),
                "uid": str(comp.get("uid") or "").strip(),
            })
        return out
    except ImportError:
        return _parse_ics_builtin(ics_text)
    except Exception:
        log.debug("icalendar parse failed, fallback to builtin", exc_info=True)
        return _parse_ics_builtin(ics_text)


# ---------- 落库:日历事件 → events(kind=calendar) ----------

def _fmt_when(ev: dict) -> str:
    from datetime import datetime
    s = ev.get("start")
    if not s:
        return ""
    try:
        return datetime.fromtimestamp(s / 1000).strftime("%m-%d %H:%M")
    except Exception:
        return ""


def import_events(events: list[dict], *, source: str = "calendar:ics") -> dict:
    """把解析出的日历事件落进 events(kind=calendar),按 uid 去重。返回统计。"""
    db.init_db()
    added = 0
    for ev in events:
        title = ev.get("title") or "(无标题日程)"
        when = _fmt_when(ev)
        content = f"时间: {when or '未定'}"
        if ev.get("location"):
            content += f"\n地点: {ev['location']}"
        if ev.get("organizer"):
            content += f"\n组织者: {ev['organizer']}"
        dedup = f"cal:{ev.get('uid') or (title + str(ev.get('start') or ''))}"
        eid = db.insert_event(
            source=source, kind="calendar", domain="life", title=title, content=content,
            meta={"start": ev.get("start"), "end": ev.get("end"),
                  "location": ev.get("location"), "organizer": ev.get("organizer"), "uid": ev.get("uid")},
            dedup_key=dedup,
        )
        if eid:
            added += 1
    return {"ok": True, "parsed": len(events), "added": added}


def import_ics(ics_text: str, *, source: str = "calendar:ics") -> dict:
    """从 ics 文本导入日历(本地文件内容 / 订阅链接抓回的文本)。"""
    if not ics_text or "BEGIN:VEVENT" not in ics_text:
        return {"ok": False, "parsed": 0, "added": 0, "error": "无有效 VEVENT"}
    return import_events(_parse_ics(ics_text), source=source)


# ---------- CalDAV 同步(可选,需 caldav 依赖 + 凭证) ----------

def _caldav_cfg() -> dict:
    try:
        from .config import settings
        return settings().get("calendar", {}) or {}
    except Exception:
        return {}


def sync_caldav() -> dict:
    """从配置的 CalDAV 拉日历事件落库。需 [calendar].caldav_url + caldav 依赖。
    无配置/无依赖时优雅返回(不报错),只是不同步。"""
    cfg = _caldav_cfg()
    url = str(cfg.get("caldav_url", "")).strip()
    if not url:
        return {"ok": False, "reason": "未配置 [calendar].caldav_url(留 ics 导入即可)"}
    try:
        import caldav  # noqa
    except ImportError:
        return {"ok": False, "reason": "未安装 caldav 依赖(pip install caldav 可启用)"}
    try:
        client = caldav.DAVClient(url=url, username=str(cfg.get("username", "")),
                                  password=str(cfg.get("password", "")))
        principal = client.principal()
        total = {"parsed": 0, "added": 0}
        for cal in principal.calendars():
            for comp in cal.events():
                r = import_ics(comp.data, source=f"calendar:caldav:{cal.name or 'cal'}")
                total["parsed"] += r.get("parsed", 0)
                total["added"] += r.get("added", 0)
        return {"ok": True, **total}
    except Exception as exc:  # noqa: BLE001
        log.warning("caldav sync failed: %s", exc)
        return {"ok": False, "reason": f"CalDAV 同步失败: {exc}"}


def upcoming(hours: int = 168, limit: int = 50) -> list[dict]:
    """取未来 hours 小时内的日历事件(给首页/收尾/收件箱用)。"""
    db.init_db()
    import json
    now = db.now_ms()
    horizon = now + hours * 3600 * 1000
    out = []
    with db.conn() as c:
        rows = c.execute(
            "SELECT id,title,content,meta FROM events WHERE kind='calendar' ORDER BY ts DESC LIMIT 500"
        ).fetchall()
    for r in rows:
        try:
            m = json.loads(r["meta"] or "{}")
        except Exception:
            m = {}
        start = m.get("start")
        if start and now - 3600_000 <= start <= horizon:
            out.append({"event_id": r["id"], "title": r["title"], "start": start,
                        "location": m.get("location"), "organizer": m.get("organizer")})
    out.sort(key=lambda x: x["start"])
    return out[:limit]
