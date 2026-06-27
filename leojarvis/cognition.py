"""主动认知（超级 Jarvis 方案 P4）：出主意 / 辅助决策 / 预判。

和「你问才答」的 agent 对话不同，这三件事是 Jarvis **主动**基于你的分层记忆产出：
  advise(topic)    —— 针对某情境给情境化建议（结合你的事实+习惯+相关历史）
  decide(question, options) —— 给每个选项的利弊 + 结合你偏好的推荐 + 打分（决策卡片）
  anticipate()     —— 从 pattern 记忆 + 近期上下文里识别「该提醒你的事/风险」

安全红线：这三者只产「建议/判断」，不替你执行。任何动钱/对外/删除仍走 agent 的行动闸门确认。
LLM 不可用时给规则兜底，绝不报错。所有产出可被 P5 的反馈闭环采纳/否决以回流校准。
"""

from __future__ import annotations

import json
from typing import Any

from . import db
from .memory.profile import profile_text
from .memory.store import recall


def _llm(system: str, user: str) -> str | None:
    try:
        from .models_router import chat
        return chat("agent", [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.3)
    except Exception:
        return None


def _parse_json(raw: str, kind: str):
    """从模型输出抠 JSON（数组或对象），失败返回 None。"""
    if not raw:
        return None
    try:
        if kind == "array":
            s, e = raw.find("["), raw.rfind("]")
        else:
            s, e = raw.find("{"), raw.rfind("}")
        if s < 0 or e <= s:
            return None
        return json.loads(raw[s:e + 1])
    except Exception:
        return None


def _personal_context(limit: int = 10) -> str:
    rows = db.list_memories_by_layer(["fact", "pattern"], limit=limit, status="active")
    facts = "\n".join(f"- {str(r['statement'])[:160]}" for r in rows) or "（暂无已确认的长期事实/习惯）"
    return facts


# ---------- 出主意 ----------

_ADVISE_SYSTEM = """你是 Leo 的私人参谋。结合 Leo 的长期事实/习惯和相关历史，针对他给的情境主动出主意。
要具体、可执行、贴合 Leo 的偏好；不要泛泛而谈、不要套话。
只输出 JSON：{"summary":"一句话核心建议","suggestions":["2-4 条具体可做的事"],"rationale":"为什么这么建议（点名依据的事实/习惯）"}"""


def advise(topic: str) -> dict[str, Any]:
    topic = (topic or "").strip()
    if not topic:
        return {"ok": False, "error": "topic required"}
    relevant = recall(topic, k=5)
    rel = "\n".join(f"- {r.get('text','')[:160]}" for r in relevant) or "（无）"
    user = f"## 关于 Leo\n{_personal_context()}\n\n## 相关历史\n{rel}\n\n## 情境\n{topic}"
    data = _parse_json(_llm(_ADVISE_SYSTEM, user) or "", "object")
    if not data:
        return {
            "ok": True, "used_llm": False, "topic": topic,
            "summary": "暂时只能给通用建议（模型不可用或未配置）。",
            "suggestions": ["把情境再说具体些", "先看相关历史记忆", "需要时让我跑工具核实现状"],
            "rationale": "LLM 不可用，已退回规则兜底。",
        }
    data.update({"ok": True, "used_llm": True, "topic": topic})
    return data


# ---------- 辅助决策 ----------

_DECIDE_SYSTEM = """你是 Leo 的私人决策参谋。针对一个决策问题和若干候选项，逐项给利弊，并结合 Leo 的偏好给推荐。
只输出 JSON：{"options":[{"name":"选项名","pros":["利"],"cons":["弊"],"score":0-100}],"recommendation":"推荐哪个","why":"结合 Leo 偏好的理由"}
score 越高越推荐。必须覆盖所有给定选项。"""


def decide(question: str, options: list[str]) -> dict[str, Any]:
    question = (question or "").strip()
    options = [str(o).strip() for o in (options or []) if str(o).strip()]
    if not question or len(options) < 2:
        return {"ok": False, "error": "need question and >=2 options"}
    relevant = recall(question, k=5)
    rel = "\n".join(f"- {r.get('text','')[:140]}" for r in relevant) or "（无）"
    user = (f"## 关于 Leo\n{_personal_context()}\n\n## 相关历史\n{rel}\n\n"
            f"## 决策问题\n{question}\n\n## 候选项\n" + "\n".join(f"- {o}" for o in options))
    data = _parse_json(_llm(_DECIDE_SYSTEM, user) or "", "object")
    if not data or not isinstance(data.get("options"), list):
        return {
            "ok": True, "used_llm": False, "question": question,
            "options": [{"name": o, "pros": [], "cons": [], "score": 50} for o in options],
            "recommendation": options[0],
            "why": "LLM 不可用，未做实质权衡，仅列出选项。",
        }
    data.update({"ok": True, "used_llm": True, "question": question})
    return data


# ---------- 预判 ----------

_ANTICIPATE_SYSTEM = """你是 Leo 的私人参谋。下面是 Leo 的行为规律(pattern)和近期上下文。
请预判「现在/接下来该提醒 Leo 的事或风险」——基于他的规律，提前一步。
只输出 JSON 数组，每条：{"headline":"一句话提醒","reason":"基于哪条规律/上下文","urgency":"low|medium|high"}
最多 5 条。没有值得提醒的就返回 []。不要编造没有依据的预测。"""


def anticipate(context_hint: str = "") -> dict[str, Any]:
    patterns = db.list_memories_by_layer(["pattern"], limit=20, status="active")
    if not patterns:
        return {"ok": True, "used_llm": False, "predictions": [],
                "note": "暂无行为规律可供预判（先投喂数据 + 跑 /memory/distill 提炼 pattern）。"}
    pat = "\n".join(f"- {str(r['statement'])[:160]}" for r in patterns)
    user = f"## 关于 Leo\n{_personal_context()}\n\n## 行为规律\n{pat}\n\n## 近期上下文\n{context_hint or '（无特别上下文）'}"
    arr = _parse_json(_llm(_ANTICIPATE_SYSTEM, user) or "", "array")
    if arr is None:
        return {"ok": True, "used_llm": False, "predictions": [],
                "note": "LLM 不可用，未做预判。"}
    preds = [p for p in arr if isinstance(p, dict) and str(p.get("headline", "")).strip()][:5]
    return {"ok": True, "used_llm": True, "predictions": preds}
