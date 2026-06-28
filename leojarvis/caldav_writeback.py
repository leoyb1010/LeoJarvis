"""CalDAV 写回(问题1):把本地日程的增/改/删推到用户配置的 CalDAV 日历。

`calendar_sync.py` 是单向拉取(远端 → 本地)。这里补上写回(本地 → 远端):用户在
首页录入的日程,写到他自己的 CalDAV(iCloud / Google / Fastmail …)日历里,从而
自动同步到手机的「日历」和「提醒」App —— 不依赖 macOS EventKit/osascript,纯 CalDAV。

设计借鉴 odysseus 的 src/caldav_writeback.py,但精简为单用户 / 单 SQLite / 单 [calendar]
配置块:
  - build_event_ical(item)  : 纯函数,把日程 dict 序列化成 VCALENDAR/VEVENT(含 VALARM 提醒、
                              RRULE 重复)。可脱离网络单测。
  - push_event(calendars,…) : 注入 calendars 列表 → 按 uid 增/改/删。可用 fake client 单测。
  - writeback(item,…)       : 同步入口。无配置/无依赖 → 优雅跳过;否则后台线程 fire-and-forget。
                              本地 DB 永远是 source of truth,CalDAV 失败绝不影响本地写。
  - config_status()         : 给 UI 看的状态(是否已配置 / 依赖是否在),绝不回传密码。

安全:不把密码写进任何返回值;url 只回传 host 部分。
"""

from __future__ import annotations

import logging
import threading

from .calendar_sync import _caldav_cfg

log = logging.getLogger("leojarvis.caldav_writeback")

_DEFAULT_DURATION_MS = 30 * 60 * 1000  # 日程无结束时间 → 合成 +30min


def _ms_to_dt(ms: int):
    """epoch-ms → tz-aware UTC datetime(与 calendar_sync._parse_dt 的 UTC 约定一致,保证拉取往返)。"""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)


def _rrule_for(repeat: str):
    """日程 repeat → icalendar vRecur(None 表示不重复)。"""
    freq = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY"}.get((repeat or "").strip())
    if not freq:
        return None
    from icalendar.prop import vRecur
    return vRecur({"FREQ": [freq]})


def build_event_ical(item: dict) -> str:
    """把日程 dict 序列化成 VCALENDAR/VEVENT 字符串(纯函数,可单测)。

    item 需含:cal_uid、title、start_ts;可选:note、remind_ts、repeat。
    - 有 remind_ts → 加 VALARM(TRIGGER = remind_ts - start_ts,负值 = 提前,手机原生提醒)。
    - repeat 非 none → 加 RRULE。
    时间一律 UTC(emit `Z`)。
    """
    from datetime import timedelta
    from icalendar import Alarm, Calendar, Event as iEvent

    start_ts = int(item["start_ts"])
    cal = Calendar()
    cal.add("prodid", "-//LeoJarvis//schedule//CN")
    cal.add("version", "2.0")

    ve = iEvent()
    ve.add("uid", str(item.get("cal_uid") or f"{item.get('id', 'evt')}@leojarvis"))
    ve.add("summary", str(item.get("title") or "日程"))
    note = str(item.get("note") or "").strip()
    if note:
        ve.add("description", note)
    ve.add("dtstart", _ms_to_dt(start_ts))
    ve.add("dtend", _ms_to_dt(start_ts + _DEFAULT_DURATION_MS))

    rr = _rrule_for(item.get("repeat") or "none")
    if rr is not None:
        ve.add("rrule", rr)

    remind_ts = item.get("remind_ts")
    if remind_ts:
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", str(item.get("title") or "日程提醒"))
        # 负的 timedelta = 事件前 N(手机据此提前推送提醒)。
        alarm.add("trigger", timedelta(milliseconds=int(remind_ts) - start_ts))
        ve.add_component(alarm)

    cal.add_component(ve)
    return cal.to_ical().decode("utf-8")


def _resource_href(obj) -> str:
    for attr in ("url", "href", "canonical_url"):
        v = getattr(obj, attr, None)
        if v:
            return str(v)
    return ""


def _resource_etag(obj) -> str:
    for attr in ("etag",):
        v = getattr(obj, attr, None)
        if v:
            return str(v)
    return ""


def push_event(calendars, item: dict, *, delete: bool = False) -> dict:
    """对注入的 calendars 列表按 uid 增/改/删(纯逻辑,可用 fake client 单测)。

    - delete=True:按 uid 找到则删;找不到视作已删,返回 ok。
    - 存在 → 覆盖保存(existing.save());不存在 → 新建(cal.save_event(ical))。
    返回 {"ok":True, "remote_href":…, "remote_etag":…} 或 {"ok":False,"error":…}。
    """
    uid = str(item.get("cal_uid") or f"{item.get('id', 'evt')}@leojarvis")
    cals = list(calendars or [])
    if not cals:
        return {"ok": False, "error": "no calendar"}

    # 在所有日历里按 uid 找已存在的 VEVENT(改/删时定位)。
    existing = None
    for cal in cals:
        try:
            existing = cal.event_by_uid(uid)
            if existing is not None:
                break
        except Exception:
            existing = None

    if delete:
        if existing is not None:
            try:
                existing.delete()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"delete failed: {exc}"}
        return {"ok": True, "deleted": True, "uid": uid}

    ical = build_event_ical(item)
    try:
        if existing is not None:
            existing.data = ical
            existing.save()
            return {"ok": True, "updated": True, "uid": uid,
                    "remote_href": _resource_href(existing), "remote_etag": _resource_etag(existing)}
        created = cals[0].save_event(ical)
        return {"ok": True, "created": True, "uid": uid,
                "remote_href": _resource_href(created), "remote_etag": _resource_etag(created)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"save failed: {exc}"}


def _discover_calendars(client):
    """优先 principal().calendars();失败则退回直接用配置的 url 当一个日历。"""
    try:
        return client.principal().calendars()
    except Exception:
        try:
            return [client.calendar(url=str(_caldav_cfg().get("caldav_url", "")))]
        except Exception:
            return []


def _pick_write_calendars(calendars, cfg):
    """若配了 [calendar].write_calendar,优先写到同名日历;否则用全部(push_event 写第一个)。"""
    want = str(cfg.get("write_calendar", "")).strip()
    if not want:
        return calendars
    named = [c for c in calendars if str(getattr(c, "name", "") or "") == want]
    return named or calendars


def _writeback_blocking(item: dict, delete: bool, cfg: dict) -> dict:
    """实际开 DAVClient 写。任何异常都吞掉返回 {"ok":False},绝不抛。"""
    try:
        import caldav
    except ImportError:
        return {"ok": False, "skipped": "未安装 caldav/icalendar"}
    try:
        client = caldav.DAVClient(
            url=str(cfg.get("caldav_url", "")),
            username=str(cfg.get("username", "")),
            password=str(cfg.get("password", "")),
        )
        calendars = _pick_write_calendars(_discover_calendars(client), cfg)
        return push_event(calendars, item, delete=delete)
    except Exception as exc:  # noqa: BLE001
        log.debug("caldav writeback failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def writeback(item: dict, *, delete: bool = False, block: bool = False) -> dict:
    """同步入口。无 caldav_url → 跳过;缺依赖 → 跳过;否则后台线程写(默认不阻塞)。

    block=True(单测用)时同步执行并返回结果;否则返回 {"queued":True} 并在后台线程里写,
    本地写永远不被 CalDAV 拖慢/拖挂。
    """
    cfg = _caldav_cfg()
    if not str(cfg.get("caldav_url", "")).strip():
        return {"skipped": "caldav 未配置"}
    if block:
        return _writeback_blocking(item, delete, cfg)
    threading.Thread(target=_writeback_blocking, args=(item, delete, cfg), daemon=True).start()
    return {"queued": True}


def config_status() -> dict:
    """给 UI 的状态:是否已配置 + 依赖是否在 + url 的 host(绝不回传密码/完整 url)。"""
    cfg = _caldav_cfg()
    url = str(cfg.get("caldav_url", "")).strip()
    lib_present = True
    try:
        import caldav  # noqa
        import icalendar  # noqa
    except ImportError:
        lib_present = False
    host = ""
    if url:
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
        except Exception:
            host = ""
    return {"configured": bool(url) and lib_present, "lib_present": lib_present,
            "url_host": host, "has_url": bool(url)}
