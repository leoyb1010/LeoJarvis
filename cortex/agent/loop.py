"""Agent 对话循环：Plan → Act → Observe，受行动闸门约束。

无状态：每次请求传入完整对话历史。内部多步调用工具，返回最终答复 + 步骤 + 待批准动作。
高风险动作不在本轮执行，而是登记成 pending，等用户通过 /agent/approve 批准后再执行。
"""
from __future__ import annotations

import json
import re
import uuid

from .. import db
from ..memory.store import recall
from ..models_router import chat
from . import gate
from .prompts import build_system_prompt
from .tools import TOOLBUS

MAX_STEPS = 8

# 进程内待批准动作表（V1：daemon 单进程，重启后清空，可接受）
_PENDING: dict[str, dict] = {}


def _parse_action(raw: str) -> dict:
    """从模型输出里抽取 JSON 动作，容错。"""
    raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        chunk = raw[start:end + 1]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            # 去掉可能的尾随逗号再试
            try:
                return json.loads(re.sub(r",\s*}", "}", chunk))
            except json.JSONDecodeError:
                pass
    return {"final": raw or "（我没有产生有效回复）"}


def _log_action(tool: str, args: dict, result: str, status: str) -> None:
    db.insert_event(
        source="agent", kind="action", domain="business",
        title=f"{tool} [{status}]",
        content=f"args={json.dumps(args, ensure_ascii=False)}\n-> {result[:1000]}",
        meta={"tool": tool, "status": status},
    )


def run_agent(messages: list[dict]) -> dict:
    """messages: [{role: 'user'|'assistant', content: str}]，至少含一条 user。"""
    user_last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    recalled = recall(user_last, k=5)
    convo = [{"role": "system", "content": build_system_prompt(recalled)}]
    convo += [{"role": m["role"], "content": m["content"]} for m in messages]

    steps: list[dict] = []

    for _ in range(MAX_STEPS):
        try:
            raw = chat("agent", convo, temperature=0.2)
        except Exception as ex:  # noqa: BLE001
            return {
                "reply": f"⚠️ 还没法思考：{ex}\n请在 config/models.toml 配置一个可用的 LLM 接口"
                         f"（routing.agent 或 routing.default）。",
                "steps": steps, "pending_actions": [],
            }

        action = _parse_action(raw)

        if "final" in action and "action" not in action:
            return {"reply": action.get("final", ""), "steps": steps, "pending_actions": []}

        act = action.get("action") or {}
        tool = act.get("tool", "")
        args = act.get("args", {}) or {}
        if not tool:
            return {"reply": action.get("final") or action.get("thought") or raw,
                    "steps": steps, "pending_actions": []}

        decision = gate.evaluate(tool, args)

        if decision == "deny":
            obs = "⛔ 该操作被安全策略拒绝，未执行。"
            _log_action(tool, args, obs, "denied")
            steps.append({"tool": tool, "args": args, "status": "denied"})
        elif decision == "confirm":
            pid = uuid.uuid4().hex[:12]
            _PENDING[pid] = {"tool": tool, "args": args, "thought": action.get("thought", "")}
            steps.append({"tool": tool, "args": args, "status": "pending", "id": pid})
            note = action.get("thought") or f"我准备执行 {tool}，属于高风险操作。"
            return {
                "reply": f"{note}\n\n这一步需要你确认后才会执行。",
                "steps": steps,
                "pending_actions": [{
                    "id": pid, "tool": tool, "args": args,
                    "reason": "不可逆 / 对外 / 触碰系统，按策略需你点头",
                }],
            }
        else:  # auto
            obs = TOOLBUS.invoke(tool, args)
            _log_action(tool, args, obs, "auto")
            steps.append({"tool": tool, "args": args, "status": "done",
                          "result": obs[:600]})

        convo.append({"role": "assistant", "content": raw})
        convo.append({"role": "user", "content": f"[工具 {tool} 的结果]\n{obs}"})

    return {"reply": "（已达到最大步数，先停下。你可以让我继续。）",
            "steps": steps, "pending_actions": []}


def approve_action(pid: str, decision: str) -> dict:
    """批准或拒绝一个待执行动作。decision: 'approve' | 'reject'。"""
    pending = _PENDING.pop(pid, None)
    if not pending:
        return {"ok": False, "error": "该待批准动作不存在或已处理"}
    if decision != "approve":
        _log_action(pending["tool"], pending["args"], "用户拒绝", "rejected")
        return {"ok": True, "executed": False, "result": "已拒绝，未执行。"}
    result = TOOLBUS.invoke(pending["tool"], pending["args"])
    _log_action(pending["tool"], pending["args"], result, "approved")
    return {"ok": True, "executed": True, "tool": pending["tool"], "result": result}
