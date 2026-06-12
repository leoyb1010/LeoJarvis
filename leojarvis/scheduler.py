from __future__ import annotations

import asyncio
import threading

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import db, user_settings
from .config import settings
from .ingest.calendar_ingest import CalendarCollector
from .ingest.email_ingest import EmailCollector
from .ingest.rss import RSSCollector
from .judge.engine import judge_and_store
from .memory.store import remember_event
from .notify.hub import hub

COLLECTORS = [EmailCollector(), CalendarCollector(), RSSCollector()]
_INGEST_LOCK = threading.Lock()
_INTELLIGENCE_LOCK = threading.Lock()
_GUARD_LOCK = threading.Lock()


def _run_ingest_cycle_sync() -> tuple[dict, list[dict]]:
    if not _INGEST_LOCK.acquire(blocking=False):
        return {"seen": 0, "inserted": 0, "notify": 0, "errors": [], "skipped": "already_running"}, []
    stats = {"seen": 0, "inserted": 0, "notify": 0, "errors": []}
    notifications: list[dict] = []
    try:
        for collector in COLLECTORS:
            try:
                for item in collector.collect():
                    stats["seen"] += 1
                    event_id = db.insert_event(
                        source=item.source,
                        domain=item.domain,
                        kind=item.kind,
                        title=item.title,
                        content=item.content,
                        url=item.url,
                        meta=item.meta,
                        dedup_key=item.dedup_key,
                    )
                    if event_id is None:
                        continue
                    stats["inserted"] += 1
                    # 本地 Apple Mail 只读取标题/发件人/邮箱，不让首次导入几十封旧邮件阻塞手动采集。
                    # 这里同时跳过向量记忆与 LLM judge：两者都会在首次导入历史邮件时拖慢 /ingest/run。
                    # 真正需要推送的 IMAP 未读邮件仍会走 remember + judge。
                    if str(item.source).startswith("email:Apple Mail"):
                        db.insert_judgment(
                            event_id=event_id,
                            score=0.52,
                            take=f"邮件：{item.title}。{item.content.splitlines()[0] if item.content else ''}",
                            triage="digest",
                            reasons=["Apple Mail 本地邮箱记录"],
                        )
                        continue
                    remember_event(event_id, f"{item.title}\n{item.content[:700]}")
                    judgment = judge_and_store(event_id, item)
                    if judgment.triage == "notify":
                        stats["notify"] += 1
                        notifications.append({
                            "type": "notify",
                            "event_id": event_id,
                            "title": item.title,
                            "take": judgment.take,
                            "url": item.url,
                            "score": judgment.score,
                        })
            except Exception as exc:
                stats["errors"].append({"collector": collector.name, "error": str(exc)})
                print(f"[ingest] {collector.name} failed: {exc}")
        return stats, notifications
    finally:
        _INGEST_LOCK.release()


async def run_ingest_cycle() -> dict:
    stats, notifications = await asyncio.to_thread(_run_ingest_cycle_sync)
    for payload in notifications:
        await hub.push(payload)
    return stats


async def run_intelligence_cycle() -> dict:
    """Personal Intelligence Hub：RSS / 网页变化 / GitHub 项目雷达。"""
    if not _INTELLIGENCE_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": "already_running"}
    try:
        from .intelligence.scanner import run_intelligence_scan

        result = await run_intelligence_scan()
    finally:
        _INTELLIGENCE_LOCK.release()
    print(f"[intelligence] {result}")
    return result


_GUARD_STATE: dict[str, float] = {}


def _run_system_guard_sync() -> tuple[dict, list[dict]]:
    if not _GUARD_LOCK.acquire(blocking=False):
        return {"alerts": 0, "skipped": "already_running"}, []
    import shutil
    import os
    from .agent import services

    try:
        cfg = user_settings.effective("guard")
        disk_warn = float(cfg.get("disk_used_pct", 90))
        load_warn = float(cfg.get("load_per_core", 2.5))
        alerts = []

        total, used, _ = shutil.disk_usage("/")
        disk_pct = used / total * 100
        if disk_pct >= disk_warn and _GUARD_STATE.get("disk", 0) < disk_warn:
            alerts.append({"title": "磁盘空间紧张", "take": f"/ 已用 {disk_pct:.0f}%，建议清理。问我「磁盘为什么满了」。"})
        _GUARD_STATE["disk"] = disk_pct

        try:
            l1 = os.getloadavg()[0]
            per_core = l1 / (os.cpu_count() or 1)
            if per_core >= load_warn and _GUARD_STATE.get("load", 0) < load_warn:
                alerts.append({"title": "CPU 负载偏高", "take": f"每核负载 {per_core:.1f}。问我「现在哪个进程最吃 CPU」。"})
            _GUARD_STATE["load"] = per_core
        except OSError:
            _GUARD_STATE["load_unavailable"] = 1.0

        for s in services.status_all():
            key = f"svc:{s['name']}"
            was_online = _GUARD_STATE.get(key, 1)
            if not s["online"] and was_online and s["name"] != "leojarvis":
                alerts.append({"title": f"服务掉线：{s['name']}", "take": f"{s['name']} (:{s['port']}) 离线了。"})
            _GUARD_STATE[key] = 1.0 if s["online"] else 0.0

        return {"alerts": len(alerts), "disk_pct": round(disk_pct, 1)}, alerts
    finally:
        _GUARD_LOCK.release()


async def run_system_guard() -> dict:
    """SystemGuard 主动传感器：磁盘紧张 / 负载过高 / 已知服务掉线 → 实时推送。"""
    result, alerts = await asyncio.to_thread(_run_system_guard_sync)
    for alert in alerts:
        await hub.push({"type": "notify", "source": "SystemGuard", **alert})
    return result


def run_reflection() -> dict:
    """每晚把近期事件归纳成长期记忆。"""
    from .memory.reflect import reflect
    result = reflect(hours=int(user_settings.effective("schedule").get("reflect_hours", 24)))
    print(f"[reflect] {result}")
    return result


def run_ssh_probe() -> dict:
    """定时探测已配置的 SSH 设备，把健康摘要写进设备库。
    同步函数：APScheduler 会在线程池里跑，subprocess(ssh) 不会阻塞事件循环。"""
    from . import remote_status
    try:
        res = remote_status.probe_all()
        print(f"[ssh-probe] probed {res.get('count', 0)} device(s)")
        return res
    except Exception as exc:  # 永不让一次探测失败影响调度器
        print(f"[ssh-probe] error: {exc}")
        return {"ok": False, "error": str(exc)}


def run_maintenance() -> dict:
    """定时维护：裁日志 + 清旧快照。在线程里跑，避免文件/DB 操作阻塞事件循环。"""
    from .maintenance import run_maintenance as _do
    try:
        return _do()
    except Exception as exc:  # 维护失败绝不影响调度器
        print(f"[maintenance] error: {exc}")
        return {"ok": False, "error": str(exc)}


def run_remote_cortex_maintain() -> dict:
    """远程 LeoJarvis 隧道保活：周期做真实 HTTP 健康校验，断了就后台重连。
    之前断线只有打开设备页才触发重连；现在睡眠唤醒/网络切换后约一分钟内自愈。"""
    from . import remote_cortex
    try:
        res = remote_cortex.maintain()
        offline = [r for r in res.get("results", []) if not r.get("connected")]
        if offline:
            print(f"[remote-cortex] {len(offline)} connection(s) reconnecting: "
                  + ", ".join(str(r.get("name") or r.get("id")) for r in offline))
        return res
    except Exception as exc:
        print(f"[remote-cortex] maintain error: {exc}")
        return {"ok": False, "error": str(exc)}


def setup_scheduler() -> AsyncIOScheduler:
    cfg = user_settings.effective("schedule")
    intel_cfg = user_settings.effective("intelligence")
    # misfire_grace_time 放宽到 5 分钟：笔记本短暂睡眠/卡顿造成的 miss 直接补跑、不刷
    # 警告；coalesce 保证只补跑一次。更长的睡眠才会留下「missed」日志（确实值得知道）。
    job_defaults = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 300}
    sched = AsyncIOScheduler(job_defaults=job_defaults)
    sched.add_job(run_ingest_cycle, "interval", minutes=int(cfg.get("ingest_minutes", 30)), id="ingest", replace_existing=True)
    sched.add_job(
        run_intelligence_cycle,
        "interval",
        minutes=int(intel_cfg.get("scan_minutes", 60)),
        id="intelligence",
        replace_existing=True,
    )
    sched.add_job(run_system_guard, "interval", minutes=int(cfg.get("guard_minutes", 5)), id="guard", replace_existing=True)
    # SSH 设备健康探测：定时刷新远程设备状态；启动后 ~15s 先跑一次，让设备页尽快有数据。
    # misfire_grace_time 放宽：Mac 睡眠会让 interval 任务大面积 miss，唤醒后补跑一次即可。
    from datetime import datetime, timedelta
    sched.add_job(run_ssh_probe, "interval", minutes=int(cfg.get("ssh_probe_minutes", 5)),
                  id="ssh_probe", replace_existing=True,
                  misfire_grace_time=300, coalesce=True,
                  next_run_time=datetime.now() + timedelta(seconds=15))
    # 远程 LeoJarvis 隧道保活：每分钟校验真实 HTTP 健康，断线自动后台重连。
    sched.add_job(run_remote_cortex_maintain, "interval",
                  seconds=int(cfg.get("remote_cortex_maintain_seconds", 60)),
                  id="remote_cortex_maintain", replace_existing=True,
                  misfire_grace_time=120, coalesce=True,
                  next_run_time=datetime.now() + timedelta(seconds=25))
    sched.add_job(run_reflection, "cron", hour=int(cfg.get("reflect_hour", 23)), minute=0, id="reflect", replace_existing=True)
    sched.add_job(lambda: print("[briefing] ready"), "cron",
                  hour=int(cfg.get("briefing_hour", 8)),
                  minute=int(cfg.get("briefing_minute", 0)),
                  id="briefing", replace_existing=True)
    # 维护：裁日志 + 清旧 GitHub 快照。每天凌晨跑，外加启动后 ~60s 先跑一次，
    # 避免日志/快照表在两次定时之间无限增长。
    sched.add_job(run_maintenance, "cron", hour=4, minute=30, id="maintenance",
                  replace_existing=True, misfire_grace_time=3600, coalesce=True)
    sched.add_job(run_maintenance, "date", id="maintenance_boot",
                  run_date=datetime.now() + timedelta(seconds=60), replace_existing=True)
    return sched
