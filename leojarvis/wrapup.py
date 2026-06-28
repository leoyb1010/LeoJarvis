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
请输出 JSON,字段如下(全部用自然简体中文,陈述给定数据里的事,不要编造、不要复述清单格式):
{
  "headline": "一句话概述今天/本周的主轴",
  "highlights": ["3-6 条今天/本周最值得记的进展或成果,每条一句,具体到做了什么"],
  "by_area": {"领域名": "这个领域今天/本周的情况(1-2 句)"},
  "report": "一段连贯的{period}正文(可 4-8 行,讲清完成了什么、推进到哪、还差什么)",
  "unfinished_focus": "还没完成、明天/下周要优先盯的一两件事(一句)",
  "next": "给明天/下周的一句话建议"
}
by_area 的领域名按内容自拟(如「工作」「沟通」「学习」「系统」「调研」),只放有内容的领域,没有就给空对象 {}。
内容要详尽但不啰嗦,宁可具体不要套话。"""


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


def _empty_summary(period_label: str) -> dict:
    return {"headline": f"今天没有可汇总的{period_label}记录。", "highlights": [],
            "by_area": {}, "report": "", "unfinished_focus": "", "next": ""}


def _summarize(period_label: str, data: dict) -> dict:
    comp = data["completed"]
    unf = data["unfinished"]
    if not comp and not unf:
        return _empty_summary(period_label)
    lines = ["已完成:"] + [f"- {c['title']}" + (f"（{c['detail']}）" if c.get("detail") else "") for c in comp[:24]]
    lines += ["", "未完成:"] + [f"- {u['title']}" for u in unf[:24]]
    try:
        from .models_router import chat
        raw = chat("agent", [
            {"role": "system", "content": _SUMMARY_SYSTEM.replace("{period}", period_label)},
            {"role": "user", "content": "\n".join(lines)},
        ], temperature=0.3)
        s, e = raw.find("{"), raw.rfind("}")
        obj = json.loads(raw[s:e + 1]) if s >= 0 else {}
        if isinstance(obj, dict) and (obj.get("report") or obj.get("highlights")):
            by_area = obj.get("by_area") if isinstance(obj.get("by_area"), dict) else {}
            highlights = obj.get("highlights") if isinstance(obj.get("highlights"), list) else []
            return {
                "headline": str(obj.get("headline", "")),
                "highlights": [str(h) for h in highlights][:6],
                "by_area": {str(k): str(v) for k, v in by_area.items() if v},
                "report": str(obj.get("report", "")),
                "unfinished_focus": str(obj.get("unfinished_focus", "")),
                "next": str(obj.get("next", "")),
            }
    except Exception:
        pass
    # 规则兜底:不调 LLM 也能出一份分版块的体面收尾。
    return {
        "headline": f"今天完成 {len(comp)} 项,{len(unf)} 项待续。",
        "highlights": [c["title"] for c in comp[:6]],
        "by_area": {},
        "report": f"已完成 {len(comp)} 项工作;仍有 {len(unf)} 项进行中,将自动进入明日驾驶舱。",
        "unfinished_focus": (unf[0]["title"] if unf else ""),
        "next": (unf[0]["title"] if unf else "保持节奏,明天继续。"),
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
