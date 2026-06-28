"""主动助理 + 早中晚 check-in(A)。清室重写,设计借鉴 odysseus 的 personal-assistant + 定时 check-in,
代码全新、无 AGPL 牵连。

一个第一类的助理身份(名字/人格,存 user_settings)+ 早/中/晚三次主动 check-in:
到点自动汇总「待办收件箱 + 临近日程 +(晚)今日收尾」,经 agent 用 persona 口吻输出,
落成一条 briefing 笔记,并推送提醒。check-in 复用现有 scheduled_tasks(cron)+ event_bus + scheduler,
不新增调度机制;按 `[check-in]` 名前缀认领,绝不碰用户自建任务。
"""

from __future__ import annotations

import logging

from . import db, user_settings

log = logging.getLogger("assistant")

_SLOTS = ("morning", "midday", "evening")
_SLOT_ZH = {"morning": "早间", "midday": "午间", "evening": "晚间"}
_NAME_PREFIX = "[check-in] "


def get_config() -> dict:
    return user_settings.load().get("assistant", user_settings.DEFAULTS["assistant"])


def update_config(partial: dict) -> dict:
    user_settings.patch({"assistant": partial})
    sync_checkins()
    return get_config()


def _checkin_name(slot: str) -> str:
    return f"{_NAME_PREFIX}{slot}"


def sync_checkins() -> dict:
    """把 user_settings 里的三个 check-in 配置幂等对账到 scheduled_tasks(cron)。
    只认领 `[check-in] <slot>` 名的任务,不动用户自建任务。返回统计。"""
    cfg = get_config()
    checkins = cfg.get("checkins", {})
    enabled_assistant = bool(cfg.get("enabled", True))
    existing = {t["name"]: t for t in db.list_scheduled_tasks() if str(t["name"]).startswith(_NAME_PREFIX)}
    created = updated = paused = 0
    for slot in _SLOTS:
        c = checkins.get(slot, {})
        want_on = enabled_assistant and bool(c.get("enabled", True))
        hour = int(c.get("hour", 8)); minute = int(c.get("minute", 0))
        name = _checkin_name(slot)
        row = existing.get(name)
        if row is None:
            tid = db.create_scheduled_task(name=name, prompt=f"@checkin:{slot}", trigger="cron",
                                           cron_hour=hour, cron_minute=minute)
            if not want_on:
                db.set_scheduled_task_status(tid, "paused")
            created += 1
        else:
            db.update_scheduled_task(row["id"], cron_hour=hour, cron_minute=minute,
                                     status="active" if want_on else "paused")
            if want_on:
                updated += 1
            else:
                paused += 1
    return {"ok": True, "created": created, "updated": updated, "paused": paused}


def _gather_context(slot: str) -> str:
    """确定性预取本地数据(LeoJarvis 自己的数据,非外部,无需护栏)。"""
    parts: list[str] = []
    try:
        from . import inbox
        tasks = inbox.list_inbox(states=["unconfirmed", "confirmed"], limit=20).get("tasks", [])
        if tasks:
            lines = [f"- [{t.get('priority', 'P2')}] {t.get('title', '')}" for t in tasks[:8]]
            parts.append("待办收件箱(需处理):\n" + "\n".join(lines))
        else:
            parts.append("待办收件箱:暂无需处理项。")
    except Exception:
        pass
    try:
        from . import calendar_sync
        ev = calendar_sync.upcoming(hours=24 if slot != "evening" else 36, limit=8)
        if ev:
            from datetime import datetime
            lines = []
            for e in ev:
                when = datetime.fromtimestamp(e["start"] / 1000).strftime("%m-%d %H:%M") if e.get("start") else ""
                lines.append(f"- {when} {e.get('title', '')}")
            parts.append("临近日程:\n" + "\n".join(lines))
    except Exception:
        pass
    if slot == "evening":
        try:
            from . import wrapup
            w = wrapup.build("today")
            c = w.get("counts", {})
            parts.append(f"今日收尾:完成 {c.get('completed', 0)} 项,未完成 {c.get('unfinished', 0)} 项。")
        except Exception:
            pass
    return "\n\n".join(parts) or "今天暂无可汇总的数据。"


_PROMPTS = {
    "morning": "现在是早间 check-in。基于下面的数据,给 Leo today 最该关注的 3 件事 + 一句开场鼓励。简洁。",
    "midday": "现在是午间 check-in。基于数据,提醒还没处理的要紧事 + 下午日程,一句话推动。简洁。",
    "evening": "现在是晚间 check-in。基于数据,总结今天完成与未完成,给明天一句准备建议。简洁。",
}


def run_checkin(slot: str) -> dict:
    """执行一次 check-in:预取数据 → agent(persona)→ 存 briefing 笔记 → 返回 push 载荷。
    同步函数(供调度线程调用);推送由异步侧用返回的载荷发(不在线程里碰 event loop)。"""
    if slot not in _SLOTS:
        return {"ok": False, "error": "bad slot"}
    cfg = get_config()
    ctx = _gather_context(slot)
    persona = cfg.get("persona", "")
    name = cfg.get("name", "Jarvis")
    body = ""
    try:
        from .agent.loop import run_agent
        out = run_agent([
            {"role": "system", "content": persona},
            {"role": "user", "content": _PROMPTS[slot] + "\n\n【数据】\n" + ctx},
        ])
        body = (out or {}).get("reply", "").strip()
    except Exception:
        log.exception("checkin agent failed")
    if not body:
        body = f"{_SLOT_ZH[slot]}汇总:\n{ctx}"   # 兜底:LLM 不可用也给数据

    title = f"{name} · {_SLOT_ZH[slot]} check-in"
    try:
        from . import personal_notes
        personal_notes.save_note({"title": title, "content": body, "tags": ["briefing", "check-in", slot],
                                  "source": "assistant"})
    except Exception:
        log.exception("checkin save_note failed")
    payload = {"kind": "checkin", "title": title, "body": body[:200], "slot": slot, "source": "assistant"}
    return {"ok": True, "slot": slot, "title": title, "reply": body, "push": payload}
