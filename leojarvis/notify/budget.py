"""注意力预算（每日打断预算）—— 轻量、纯函数、进程内、线程安全。

动机：再有用的通知，一天打断你十几次也是噪音。给「即时 push」设一个每日上限，
超额后的**非紧急**通知降级为 digest（汇总稍后看），而不是即时弹。紧急通知不受限。

为什么独立成模块、不改 hub：
  现有 `NotifyHub.push` 是纯广播（把 payload 发给所有 WS 客户端），不区分紧急度、
  也没有计数概念。直接在 push 里塞预算逻辑有破坏现有通知的风险，所以按「安全第一」
  把预算做成一个**旁路纯函数模块**：调用方在决定「即时 push 还是入 digest」时先问
  `can_interrupt()`，push 成功后再 `record()`。hub 的 API 一行不动，完全向后兼容。

接入方式（调用方伪代码）：
    from leojarvis.notify import budget
    urgent = payload.get("priority") == "high"        # 你的紧急判定
    if urgent or budget.can_interrupt():
        await hub.push(payload)                        # 即时 push
        if not urgent:
            budget.record()                            # 只对受预算约束的即时 push 计数
    else:
        payload = {**payload, "delivery": "digest"}    # 降级：标记汇总，稍后合并推送
        enqueue_digest(payload)

对外函数（全部确定性、可单测）：
  limit()                  -> int     当天打断上限（settings 优先，缺省 5）
  count(date=None)         -> int     某天已用的即时打断次数
  remaining(date=None)     -> int     还剩多少次
  can_interrupt(date=None) -> bool    现在还能不能即时打断（count < limit）
  record(date=None)        -> int     记一次即时打断，返回记后的 count
  classify(payload, date)  -> dict    便捷：给一条通知判「即时/降级」并附预算快照
  reset(date=None)         -> None    清零（测试 / 手动重置用）
"""

from __future__ import annotations

import datetime as _dt
import threading

# 硬编码兜底上限：settings.toml 没配 [notify].daily_interrupt_budget 时用它。
_DEFAULT_LIMIT = 5

# 进程内当天计数：{ "YYYY-MM-DD": int }。只保留当天，跨天自然归零（按 key 隔离）。
_COUNTS: dict[str, int] = {}
_LOCK = threading.RLock()


def _today() -> str:
    return _dt.date.today().isoformat()


def _key(date: str | None) -> str:
    return (date or _today()).strip() or _today()


def limit() -> int:
    """当天即时打断上限：settings.toml [notify].daily_interrupt_budget 优先，缺省 5。

    读取/解析失败一律回落默认，绝不抛异常（通知路径不能因配置问题崩）。
    """
    try:
        from ..config import settings
        raw = (settings().get("notify", {}) or {}).get("daily_interrupt_budget")
        if raw is None:
            return _DEFAULT_LIMIT
        val = int(raw)
        return val if val >= 0 else _DEFAULT_LIMIT
    except Exception:
        return _DEFAULT_LIMIT


def count(date: str | None = None) -> int:
    """某天已用的即时打断次数（默认今天）。"""
    with _LOCK:
        return _COUNTS.get(_key(date), 0)


def remaining(date: str | None = None) -> int:
    """某天还剩多少次即时打断（不为负）。"""
    return max(0, limit() - count(date))


def can_interrupt(date: str | None = None) -> bool:
    """现在还能不能即时打断：当天已用次数 < 上限。

    上限为 0 表示「永远降级」（任何非紧急通知都进 digest）。
    """
    return count(date) < limit()


def record(date: str | None = None) -> int:
    """记一次即时打断，返回记后的当天计数。

    只应在「确实即时 push 了一条受预算约束的通知」之后调用。
    """
    k = _key(date)
    with _LOCK:
        _COUNTS[k] = _COUNTS.get(k, 0) + 1
        return _COUNTS[k]


def reset(date: str | None = None) -> None:
    """清零某天计数（默认今天）。手动重置或测试隔离用。"""
    with _LOCK:
        _COUNTS.pop(_key(date), None)


def classify(payload: dict | None = None, date: str | None = None) -> dict:
    """便捷判定：给一条通知决定「即时 push 还是降级 digest」，并附预算快照。

    紧急通知（payload.urgent 为真，或 payload.priority in {high, urgent, critical}）
    永远即时、且不消耗预算。非紧急按 can_interrupt() 决定。

    注意：本函数**不副作用**（不 record）—— 是否计数交给调用方在真正 push 后决定，
    这样「判定」和「记账」解耦，便于测试与复用。
    返回：{interrupt: bool, urgent: bool, delivery: 'push'|'digest', remaining, limit}
    """
    p = payload or {}
    urgent = bool(p.get("urgent")) or str(p.get("priority", "")).lower() in {"high", "urgent", "critical"}
    interrupt = urgent or can_interrupt(date)
    return {
        "interrupt": interrupt,
        "urgent": urgent,
        "delivery": "push" if interrupt else "digest",
        "remaining": remaining(date),
        "limit": limit(),
    }
