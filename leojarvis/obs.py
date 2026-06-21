"""轻量可观测：进程内计数器 + 计时，零新依赖。

目的：给「系统自身健康」一个可读快照——LLM 调用次数、批量 judge 规模、扫描耗时、
缓存命中等——通过 GET /metrics 暴露给驾驶舱，排障不再靠猜。

设计：纯进程内、线程安全、绝不抛异常（可观测代码自身不能拖垮主服务）。
重启清零（与现有进程内缓存一致）；需要跨重启留存可日后接落盘。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager

_LOCK = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
_timers_total_ms: dict[str, float] = defaultdict(float)
_timers_count: dict[str, int] = defaultdict(int)
_gauges: dict[str, float] = {}
_started_at = time.time()


def incr(name: str, by: int = 1) -> None:
    """累加一个计数器（如 llm.calls、llm.judge_batch.calls）。"""
    try:
        with _LOCK:
            _counters[name] += int(by)
    except Exception:
        pass


def gauge(name: str, value: float) -> None:
    """记录一个瞬时值（如最近一次扫描耗时秒数、DB 行数）。"""
    try:
        with _LOCK:
            _gauges[name] = float(value)
    except Exception:
        pass


def observe_ms(name: str, ms: float) -> None:
    """记录一次耗时样本（累计 + 次数，便于算均值）。"""
    try:
        with _LOCK:
            _timers_total_ms[name] += float(ms)
            _timers_count[name] += 1
    except Exception:
        pass


@contextmanager
def timed(name: str):
    """计时上下文：`with timed("scan.rss"): ...` 自动记录耗时（毫秒）。"""
    t0 = time.time()
    try:
        yield
    finally:
        observe_ms(name, (time.time() - t0) * 1000.0)


def snapshot() -> dict:
    """导出当前快照（供 /metrics）。计时项附均值。"""
    with _LOCK:
        timers = {
            name: {
                "count": _timers_count[name],
                "avg_ms": round(_timers_total_ms[name] / _timers_count[name], 1) if _timers_count[name] else 0.0,
                "total_ms": round(_timers_total_ms[name], 1),
            }
            for name in _timers_total_ms
        }
        return {
            "uptime_s": int(time.time() - _started_at),
            "counters": dict(_counters),
            "gauges": dict(_gauges),
            "timers": timers,
        }


def reset() -> None:
    """清零（测试用）。"""
    with _LOCK:
        _counters.clear()
        _timers_total_ms.clear()
        _timers_count.clear()
        _gauges.clear()
