"""后台维护：日志瘦身 + 数据库保留窗口。

launchd 把 stdout/stderr 直接重定向到 data/*.log，append 模式无限增长（uvicorn
访问日志为主），几天就上 MB。这里在启动时和每天定时把日志裁到尾部 N KB，并对
会无限增长的表做保留清理。所有操作都吞掉异常，绝不影响主服务。
"""
from __future__ import annotations

import os

from .config import DATA_DIR

# 单个日志超过 _LOG_MAX_BYTES 时，只保留最后 _LOG_KEEP_BYTES。
_LOG_MAX_BYTES = 4 * 1024 * 1024
_LOG_KEEP_BYTES = 1 * 1024 * 1024
_LOG_FILES = ("stdout.log", "stderr.log", "cortex.log")


def trim_logs() -> dict[str, int]:
    """把过大的日志裁到尾部。launchd 的 fd 是 O_APPEND，截断后下次写入仍从新 EOF 追加，
    不会留空洞。"""
    trimmed: dict[str, int] = {}
    for name in _LOG_FILES:
        path = DATA_DIR / name
        try:
            if not path.exists():
                continue
            size = path.stat().st_size
            if size <= _LOG_MAX_BYTES:
                continue
            with path.open("rb") as f:
                f.seek(-_LOG_KEEP_BYTES, os.SEEK_END)
                tail = f.read()
            # 从第一个换行后切，避免把一行日志拦腰截断。
            nl = tail.find(b"\n")
            if 0 <= nl < len(tail) - 1:
                tail = tail[nl + 1:]
            with path.open("r+b") as f:
                f.seek(0)
                f.write(tail)
                f.truncate()
            trimmed[name] = size - len(tail)
        except Exception:
            continue
    return trimmed


def run_maintenance() -> dict:
    """定时维护一轮：裁日志 + 清旧快照。供调度器调用。"""
    from . import db

    result: dict = {"ok": True}
    try:
        result["logs_trimmed"] = trim_logs()
    except Exception as exc:  # noqa: BLE001
        result["logs_error"] = str(exc)
    try:
        pruned = db.prune_old_data()
        result["pruned"] = pruned
        # 只有删了足够多行才 VACUUM（VACUUM 会全库加锁，不值得每天为几行跑一次）。
        if sum(int(v) for v in pruned.values()) >= 200:
            result["vacuumed"] = db.vacuum()
    except Exception as exc:  # noqa: BLE001
        result["prune_error"] = str(exc)
    try:
        # 超级 Jarvis P5：记忆体检 —— 低置信/久未更新的活跃记忆归档，防止「自信地记错」。
        result["memory_sweep"] = db.memory_health_sweep()
    except Exception as exc:  # noqa: BLE001
        result["memory_sweep_error"] = str(exc)
    print(f"[maintenance] {result}")
    return result
