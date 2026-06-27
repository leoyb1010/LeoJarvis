"""下班收尾 / 日报周报（WorkDock 合并 M3）。

把今天(或本周)的碎片汇总成一份可交付的收尾:
  - 已完成: done 状态的任务 + agent 执行的动作(events kind=action, status 成功)
  - 未完成: 仍在 unconfirmed/confirmed 的任务(自动进明日驾驶舱)
每行都带**来源**(task.event_id 或 action event),不凭空生成。
最后用一段 LLM 总结生成日报/周报正文(复用 models_router.chat,不可用则规则兜底)。

数据全部来自 LeoJarvis 自己的引擎(tasks 表 + events 动作日志),
比 WorkDock 生成「外部新闻简报」数据更全——这是简报能力的自然延伸。
"""

from __future__ import annotations

import json

from . import db

_DAY_MS = 86_400_000

_SUMMARY_SYSTEM = """你是 Leo 的私人助理,正在帮他写工作{period}。下面是结构化的已完成项与未完成项。
请输出 JSON: {"headline":"一句话概述今天/本周的主轴","report":"3-6 行的{period}正文(自然中文,陈述完成了什么、还差什么),不要复述清单格式","next":"给明天/下周的一句话建议"}
只陈述给定数据里的事,不要编造。"""


def _action_ok(meta_raw: str | None) -> tuple[bool, str]:
    """从 action event 的 meta 取 (是否成功执行, tool 名)。"""
    try:
        m = json.loads(meta_raw or "{}")
    except Exception:
        m = {}
    status = str(m.get("status", ""))
    # 成功执行(非 denied/pending/error)才算「完成」。
    ok = status in {"ok", "done", "success", ""} and status not in {"denied", "pending", "error"}
    return ok, str(m.get("tool", ""))


def _collect(hours: int) -> dict:
    since = db.now_ms() - hours * 3_600_000
    completed: list[dict] = []
    unfinished: list[dict] = []

    # 1) 任务(M2)：done = 完成；unconfirmed/confirmed = 未完成。
    for r in db.list_tasks(states=["done", "confirmed", "unconfirmed"], limit=200):
        d = dict(r)
        if int(d.get("updated_ts") or 0) < since and d.get("inbox_state") == "done":
            continue
        item = {
            "title": d.get("title"),
            "detail": d.get("suggestion") or d.get("context_preview") or "",
            "source": {"kind": "task", "origin": d.get("origin"), "event_id": d.get("event_id")},
        }
        (completed if d.get("inbox_state") == "done" else unfinished).append(item)

    # 2) agent 动作日志(events kind=action)：成功执行的算完成项,带来源。
    for e in db.query_events(since, limit=300):
        if e["kind"] != "action":
            continue
        ok, tool = _action_ok(e["meta"])
        if not ok:
            continue
        completed.append({
            "title": (e["title"] or tool or "执行动作").replace(" [ok]", "").replace(" []", ""),
            "detail": "Agent 执行 · 已记录审计",
            "source": {"kind": "action", "tool": tool, "event_id": e["id"]},
        })

    return {"completed": completed, "unfinished": unfinished}


def _summarize(period_label: str, data: dict) -> dict:
    comp = data["completed"]
    unf = data["unfinished"]
    if not comp and not unf:
        return {"headline": f"今天没有可汇总的{period_label}记录。", "report": "", "next": ""}
    lines = ["已完成:"] + [f"- {c['title']}" for c in comp[:20]]
    lines += ["", "未完成:"] + [f"- {u['title']}" for u in unf[:20]]
    try:
        from .models_router import chat
        raw = chat("agent", [
            {"role": "system", "content": _SUMMARY_SYSTEM.replace("{period}", period_label)},
            {"role": "user", "content": "\n".join(lines)},
        ], temperature=0.3)
        s, e = raw.find("{"), raw.rfind("}")
        obj = json.loads(raw[s:e + 1]) if s >= 0 else {}
        if isinstance(obj, dict) and obj.get("report"):
            return {"headline": obj.get("headline", ""), "report": obj.get("report", ""),
                    "next": obj.get("next", "")}
    except Exception:
        pass
    # 规则兜底：不调 LLM 也能出一份体面的收尾。
    return {
        "headline": f"今天完成 {len(comp)} 项，{len(unf)} 项待续。",
        "report": f"已完成 {len(comp)} 项工作；仍有 {len(unf)} 项进行中，将自动进入明日驾驶舱。",
        "next": (unf[0]["title"] if unf else "保持节奏，明天继续。"),
    }


def build(period: str = "today") -> dict:
    """生成收尾。period: today(当天) / week(近 7 天)。"""
    hours = 24 if period == "today" else 24 * 7
    label = "日报" if period == "today" else "周报"
    data = _collect(hours)
    summary = _summarize(label, data)
    return {
        "ok": True,
        "period": period,
        "label": label,
        "completed": data["completed"],
        "unfinished": data["unfinished"],
        "counts": {"completed": len(data["completed"]), "unfinished": len(data["unfinished"])},
        "summary": summary,
    }
