"""CalDAV 写回测试(问题1)。

- build_event_ical:纯函数,验 VEVENT/VALARM/RRULE/UTC 往返(无网络)。
- push_event:对 fake calendar 验增/改/删/已删(无网络)。
- schedule hook:验 create 设 cal_uid、增改删会调 writeback、writeback 抛错不影响本地 CRUD。
"""

import pytest

pytest.importorskip("icalendar")
pytest.importorskip("caldav")

from leojarvis import caldav_writeback as cw  # noqa: E402
from leojarvis import schedule as sch  # noqa: E402


# ---------- build_event_ical ----------

def test_build_event_ical_has_core_fields():
    item = {"cal_uid": "u1@leojarvis", "title": "评审会", "note": "备料",
            "start_ts": 1782723600000, "remind_ts": 1782722700000, "repeat": "weekly"}
    ical = cw.build_event_ical(item)
    assert "BEGIN:VEVENT" in ical and "END:VEVENT" in ical
    assert "UID:u1@leojarvis" in ical
    assert "SUMMARY:评审会" in ical
    assert "DESCRIPTION:备料" in ical
    # UTC Z 输出(与 calendar_sync._parse_dt 的 UTC 约定一致)
    assert "DTSTART:20260629T090000Z" in ical
    # 提醒 → VALARM,提前 15 分钟
    assert "BEGIN:VALARM" in ical and "TRIGGER:-PT15M" in ical
    # 重复 → RRULE
    assert "FREQ=WEEKLY" in ical


def test_build_event_ical_no_reminder_no_repeat():
    item = {"cal_uid": "u2@leojarvis", "title": "无提醒事项", "start_ts": 1782723600000}
    ical = cw.build_event_ical(item)
    assert "BEGIN:VALARM" not in ical
    assert "RRULE" not in ical
    assert "SUMMARY:无提醒事项" in ical


@pytest.mark.parametrize("repeat,expect", [
    ("daily", "FREQ=DAILY"), ("weekly", "FREQ=WEEKLY"),
    ("monthly", "FREQ=MONTHLY"), ("none", None),
])
def test_build_event_ical_rrule(repeat, expect):
    item = {"cal_uid": "u@leojarvis", "title": "x", "start_ts": 1782723600000, "repeat": repeat}
    ical = cw.build_event_ical(item)
    if expect:
        assert expect in ical
    else:
        assert "RRULE" not in ical


# ---------- push_event with fakes (no network) ----------

class _FakeEvent:
    def __init__(self, data=""):
        self.data = data
        self.saved = False
        self.deleted = False
        self.url = "https://dav.example/cal/evt.ics"
        self.etag = "etag-123"

    def save(self):
        self.saved = True

    def delete(self):
        self.deleted = True


class _FakeCalendar:
    def __init__(self, name="主日历", existing=None):
        self.name = name
        self._existing = existing  # _FakeEvent or None
        self.saved_ical = None

    def event_by_uid(self, uid):
        if self._existing is None:
            raise Exception("not found")
        return self._existing

    def save_event(self, ical):
        self.saved_ical = ical
        return _FakeEvent(data=ical)


def test_push_event_create_when_absent():
    cal = _FakeCalendar(existing=None)
    item = {"cal_uid": "new@leojarvis", "title": "新建", "start_ts": 1782723600000}
    r = cw.push_event([cal], item)
    assert r["ok"] and r.get("created")
    assert cal.saved_ical is not None and "SUMMARY:新建" in cal.saved_ical
    assert r["remote_href"] and r["remote_etag"]


def test_push_event_update_when_present():
    ev = _FakeEvent(data="OLD")
    cal = _FakeCalendar(existing=ev)
    item = {"cal_uid": "exist@leojarvis", "title": "改过", "start_ts": 1782723600000}
    r = cw.push_event([cal], item)
    assert r["ok"] and r.get("updated")
    assert ev.saved and "SUMMARY:改过" in ev.data


def test_push_event_delete_when_present():
    ev = _FakeEvent()
    cal = _FakeCalendar(existing=ev)
    item = {"cal_uid": "del@leojarvis", "title": "删", "start_ts": 1782723600000}
    r = cw.push_event([cal], item, delete=True)
    assert r["ok"] and r.get("deleted")
    assert ev.deleted


def test_push_event_delete_when_absent_is_ok():
    cal = _FakeCalendar(existing=None)
    item = {"cal_uid": "gone@leojarvis", "title": "已删", "start_ts": 1782723600000}
    r = cw.push_event([cal], item, delete=True)
    assert r["ok"] and r.get("deleted")  # 找不到也视作成功


def test_push_event_no_calendar():
    r = cw.push_event([], {"cal_uid": "x@leojarvis", "title": "x", "start_ts": 1})
    assert not r["ok"]


# ---------- writeback unconfigured degrades gracefully ----------

def test_writeback_unconfigured_skips(monkeypatch):
    monkeypatch.setattr(cw, "_caldav_cfg", lambda: {})
    r = cw.writeback({"cal_uid": "x@leojarvis", "title": "x", "start_ts": 1}, block=True)
    assert r.get("skipped")


def test_config_status_never_leaks_password(monkeypatch):
    monkeypatch.setattr(cw, "_caldav_cfg",
                        lambda: {"caldav_url": "https://caldav.icloud.com/x", "username": "u", "password": "SECRET"})
    st = cw.config_status()
    assert "SECRET" not in str(st)
    assert st["url_host"] == "caldav.icloud.com"
    assert st["has_url"] is True


# ---------- schedule hook integration ----------

def test_schedule_create_sets_cal_uid_and_calls_writeback(monkeypatch):
    calls = []
    monkeypatch.setattr("leojarvis.caldav_writeback.writeback",
                        lambda item, **kw: calls.append((item.get("cal_uid"), kw.get("delete", False))) or {"queued": True})
    sid = sch.create(title="hook测试", start_ts=1782723600000, remind_ts=1782722700000, repeat="daily")
    try:
        item = sch.get(sid)
        assert item["cal_uid"] == f"{sid}@leojarvis"
        # create 触发一次 writeback(非删)
        assert any(uid == f"{sid}@leojarvis" and not d for uid, d in calls)
    finally:
        sch.delete(sid)


def test_schedule_delete_calls_writeback_delete(monkeypatch):
    calls = []
    monkeypatch.setattr("leojarvis.caldav_writeback.writeback",
                        lambda item, **kw: calls.append(kw.get("delete", False)) or {"queued": True})
    sid = sch.create(title="删除hook", start_ts=1782723600000)
    sch.delete(sid)
    assert True in calls  # delete 分支被调


def test_schedule_crud_survives_writeback_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("caldav down")
    monkeypatch.setattr("leojarvis.caldav_writeback.writeback", boom)
    # writeback 抛错绝不能让本地 CRUD 失败
    sid = sch.create(title="抗错", start_ts=1782723600000)
    assert sid is not None
    assert sch.get(sid) is not None
    assert sch.update(sid, title="抗错改名") is True
    assert sch.delete(sid) is True
