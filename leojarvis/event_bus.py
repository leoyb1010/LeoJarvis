"""事件总线 + 定时/事件触发的 agent 任务执行(P3)。

清室重写,设计借鉴 odysseus 的 event_bus(fire_event→计数→阈值→触发 scheduled task),
但用 LeoJarvis 自己的 db / agent loop / 行动闸门,代码全新、无 AGPL 牵连。

两类触发:
  - 事件触发:fire_event("email_actionable") 累计到任务设定的阈值 → 跑该任务的 prompt。
  - 定时触发:调度器周期调 run_due_scheduled() 跑到点的 interval 任务(cron 在调度器粗判)。

执行 = 把任务 prompt 喂给现有 agent loop(run_agent),**沿用行动闸门**:不可逆/对外/触系统的动作
仍需人确认(pending),不会因为是"自动触发"就绕过 gate。这让 Jarvis 从被动变主动,但不失控。
"""

from __future__ import annotations

import logging

from . import db

log = logging.getLogger("event_bus")


def fire_event(event_name: str) -> list[str]:
    """触发一个事件:相关 event 任务计数 +1,到阈值的立即执行。返回被触发任务的 id 列表。
    同步安全(内部跑 agent 是同步的);调用方在异步上下文可用 asyncio.to_thread 包一层。"""
    try:
        fired = db.bump_event_counter(event_name)
    except Exception:
        log.exception("bump_event_counter failed for %s", event_name)
        return []
    ran = []
    for task in fired:
        try:
            _run_task_row(task)
            ran.append(task["id"])
        except Exception:
            log.exception("event task %s failed", task["id"])
    return ran


# check-in 跑完攒下的 push 载荷,由异步调度侧取走再 await 推送(不在线程里碰 event loop)。
_PENDING_PUSHES: list[dict] = []


def drain_pushes() -> list[dict]:
    out = list(_PENDING_PUSHES)
    _PENDING_PUSHES.clear()
    return out


def _run_task_row(task) -> dict:
    """跑一个 scheduled_task:把 prompt 交给 agent loop(经行动闸门),记审计。
    check-in 任务(prompt=@checkin:slot)走主动助理,产出 briefing 笔记 + 攒 push 载荷。"""
    prompt = task["prompt"]
    if isinstance(prompt, str) and prompt.startswith("@checkin:"):
        from . import assistant
        slot = prompt.split(":", 1)[1]
        res = assistant.run_checkin(slot)
        db.mark_scheduled_run(task["id"], (res.get("title") or "check-in"))
        if res.get("push"):
            _PENDING_PUSHES.append(res["push"])
        return res
    from .agent.loop import run_agent
    out = run_agent([{"role": "user", "content": prompt}])
    reply = (out or {}).get("reply", "")
    pending = (out or {}).get("pending_actions") or []
    summary = f"{reply[:300]}" + (f"  [待确认动作 {len(pending)}]" if pending else "")
    db.mark_scheduled_run(task["id"], summary)
    # 落一条事件做审计(执行台/收尾能看到)。
    try:
        db.insert_event(source="scheduler", kind="action", domain="business",
                        title=f"定时任务 [{task['name']}]",
                        content=f"prompt={prompt[:200]}\n-> {summary}",
                        meta={"tool": "scheduled_task", "status": "pending" if pending else "ok",
                              "task_id": task["id"]})
    except Exception:
        pass
    return {"task_id": task["id"], "reply": reply, "pending": len(pending)}


def run_due_scheduled() -> dict:
    """调度器周期调用:跑到点的 interval 任务,并重排其 next_run。返回统计。"""
    due = db.due_interval_tasks()
    ran = 0
    for task in due:
        try:
            _run_task_row(task)  # 已写入本轮 summary 到 last_result
            mins = int(task["interval_minutes"] or 60)
            # 只补 next_run 重排下次；不要用执行前快照的 task["last_result"] 覆盖刚写的结果。
            db.reschedule_task(task["id"], db.now_ms() + mins * 60_000)
            ran += 1
        except Exception:
            log.exception("interval task %s failed", task["id"])
    return {"ok": True, "due": len(due), "ran": ran}


def run_due_cron(hour: int, minute: int) -> dict:
    """调度器每分钟调用,跑匹配当前 HH:MM 的 cron 任务(粗粒度,误差 ≤1 分钟)。"""
    ran = 0
    for task in db.list_scheduled_tasks(status="active"):
        if task["trigger"] != "cron":
            continue
        if int(task["cron_hour"] or -1) == hour and int(task["cron_minute"] or -1) == minute:
            try:
                _run_task_row(task)
                ran += 1
            except Exception:
                log.exception("cron task %s failed", task["id"])
    return {"ok": True, "ran": ran}
