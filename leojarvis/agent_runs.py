"""受控执行台数据（WorkDock 合并 M4）。

WorkDock 的 AgentRun 概念是「计划→读→写→权限→预览→人确认→审计」的可视化。
LeoJarvis 的 agent 循环**已经有**真实的执行数据,但**没有** goal/understanding/plan/rollback 这些元数据。

原则:**只暴露真实存在的数据,绝不编造假 plan**。
真实可用的:
  - 待确认动作: loop._PENDING(内存,本进程) —— 每条带 tool/args/thought + gate 风险判定
  - 历史执行: events kind=action —— 每条带 tool/status(ok/denied/...) + 时间(即审计日志)
  - 风险三态: gate.evaluate(tool,args) → auto/confirm/deny

这本质是给现有「行动闸门」一个更好的前端,而不是新引擎。前端按这些字段渲染执行台;
WorkDock 里没数据支撑的字段(plan 分步/reads/writes/rollback)不返回,前端也不显示。
"""

from __future__ import annotations

import json

from . import db

_RISK_LABEL = {"auto": "自动", "confirm": "需确认", "deny": "已拦截"}


def _gate_verdict(tool: str, args: dict) -> dict:
    try:
        from .agent.gate import evaluate
        v = evaluate(tool, args or {})
    except Exception:
        v = "confirm"
    return {"verdict": v, "label": _RISK_LABEL.get(v, v)}


def pending_runs() -> list[dict]:
    """当前待人工确认的动作(内存态)。每条即一个等待中的 run。"""
    try:
        from .agent.loop import _PENDING
        items = list(_PENDING.items())
    except Exception:
        items = []
    out = []
    for pid, p in items:
        tool = p.get("tool", "")
        args = p.get("args", {})
        out.append({
            "id": pid,
            "status": "awaiting_approval",
            "tool": tool,
            "args": args,
            "thought": p.get("thought", ""),
            "gate": _gate_verdict(tool, args),
            "reason": "不可逆 / 对外 / 触碰系统，按策略需你点头",
        })
    return out


def recent_runs(hours: int = 48, limit: int = 40) -> list[dict]:
    """历史执行(已落库的 action 事件,即审计日志)。"""
    since = db.now_ms() - hours * 3_600_000
    out = []
    for e in db.query_events(since, limit=300):
        if e["kind"] != "action":
            continue
        try:
            meta = json.loads(e["meta"] or "{}")
        except Exception:
            meta = {}
        status = str(meta.get("status", "")) or "done"
        out.append({
            "id": e["id"],
            "status": status,            # ok / denied / error / pending(历史快照)
            "tool": str(meta.get("tool", "")),
            "title": e["title"],
            "detail": (e["content"] or "")[:400],
            "ts": e["ts"],
        })
        if len(out) >= limit:
            break
    return out


def overview(hours: int = 48) -> dict:
    pend = pending_runs()
    recent = recent_runs(hours=hours)
    done = sum(1 for r in recent if r["status"] in {"ok", "done", "success"})
    denied = sum(1 for r in recent if r["status"] == "denied")
    return {
        "ok": True,
        "pending": pend,
        "recent": recent,
        "counts": {
            "awaiting": len(pend),
            "executed": done,
            "blocked": denied,
            "total_recent": len(recent),
        },
    }
