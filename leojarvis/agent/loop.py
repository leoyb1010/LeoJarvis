"""Agent 对话循环：Plan → Act → Observe，受行动闸门约束。

无状态：每次请求传入完整对话历史。内部多步调用工具，返回最终答复 + 步骤 + 待批准动作。
高风险动作不在本轮执行，而是登记成 pending，等用户通过 /agent/approve 批准后再执行。
"""
from __future__ import annotations

import json
import re
import uuid

from collections.abc import Iterator

from .. import db
from ..memory.store import recall
from ..models_router import chat, chat_stream
from . import gate
from .prompts import build_memory_prompt, build_static_system_prompt
from .tools import TOOLBUS

MAX_STEPS = 8

# 喂回模型的工具结果上限：避免多步累积把每一步的 prompt 撑大（read_file 8000 / run_shell 6000
# 全量喂回会让后续每次 LLM 调用都更慢更贵）。截断后提示模型可用更精确命令拿完整内容。
_OBS_FEEDBACK_LIMIT = 2000

# 进程内待批准动作表（V1：daemon 单进程，重启后清空，可接受）
_PENDING: dict[str, dict] = {}


def _record_gate(decision: str) -> None:
    """闸门决策埋点：让 /metrics 能看到「拒绝/待确认/自动」各多少，暴露安全事件维度。"""
    from .. import obs
    obs.incr(f"gate.{decision}")


def _escape_ctrl_in_strings(s: str) -> str:
    """把 JSON 字符串值里的裸换行/制表符转义，修复模型在 final 里直接换行导致的解析失败。"""
    out: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            continue
        if in_str and ch == "\n":
            out.append("\\n")
        elif in_str and ch == "\r":
            out.append("\\r")
        elif in_str and ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    return "".join(out)


def _parse_action(raw: str) -> dict:
    """从模型输出里抽取 JSON 动作，容错。"""
    raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        chunk = raw[start:end + 1]
        for candidate in (chunk, _escape_ctrl_in_strings(chunk),
                          re.sub(r",\s*}", "}", _escape_ctrl_in_strings(chunk))):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        # 正则兜底：直接抠出 final 文本
        m = re.search(r'"final"\s*:\s*"(.+?)"\s*}\s*$', chunk, re.S)
        if m:
            return {"final": m.group(1).replace("\\n", "\n").replace('\\"', '"')}
    return {"final": raw or "（我没有产生有效回复）"}


class _FinalStreamer:
    """增量提取流式 JSON 里 "final" 字段的字符串值，边解析边吐出解码后的文本。

    用于让最终答复（通常是最长的一段）逐字流给用户，而不必等整段 JSON 收完。
    只关心 "final"：在看到 `"final"` 键并进入其字符串值后，逐字符解码（处理 \\n、\\" 等转义），
    遇到未转义的结束引号即停止。无法可靠判定时保持沉默（由调用方在 step 结束时用完整 parse 兜底）。
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_value = False
        self._done = False
        self._esc = False
        self._scan_pos = 0

    def feed(self, chunk: str) -> str:
        if self._done:
            return ""
        self._buf += chunk
        out: list[str] = []
        if not self._in_value:
            # 找到 "final" 键后的冒号与起始引号
            m = re.search(r'"final"\s*:\s*"', self._buf)
            if not m:
                return ""
            self._in_value = True
            self._scan_pos = m.end()
        i = self._scan_pos
        while i < len(self._buf):
            ch = self._buf[i]
            if self._esc:
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(ch, ch))
                self._esc = False
            elif ch == "\\":
                self._esc = True
            elif ch == '"':
                self._done = True
                i += 1
                break
            else:
                out.append(ch)
            i += 1
        self._scan_pos = i
        return "".join(out)


def _log_action(tool: str, args: dict, result: str, status: str) -> None:
    db.insert_event(
        source="agent", kind="action", domain="business",
        title=f"{tool} [{status}]",
        content=f"args={json.dumps(args, ensure_ascii=False)}\n-> {result[:1000]}",
        meta={"tool": tool, "status": status},
    )


def _build_convo(messages: list[dict]) -> list[dict]:
    """组装对话：稳定前缀(可缓存) + 分层 RAG 记忆 + 历史。两条 system 分开放，最大化 prompt 缓存命中。

    超级 Jarvis P4：检索不只取「和这句话相关」的记忆，还**始终**带上高重要性的
    fact/pattern（你是谁、你的习惯），让每次回答都有你的个人上下文。
    """
    user_last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    recalled = recall(user_last, k=5)
    convo = [
        {"role": "system", "content": build_static_system_prompt()},
        {"role": "system", "content": build_memory_prompt(recalled, context=_personal_context())},
    ]
    # B：注入相关「技能」(以前从类似任务总结的可复用步骤),像记忆 RAG。
    try:
        from .. import skills
        retrieved = skills.retrieve(user_last, k=3)
        if retrieved:
            convo.append({"role": "system", "content": skills.skills_prompt(retrieved)})
            for s in retrieved:
                skills._bump_use(s["id"], success=True)
    except Exception:
        pass
    convo += [{"role": m["role"], "content": m["content"]} for m in messages]
    return convo


def _post_run(messages: list[dict], steps: list[dict], reply: str) -> str:
    """B：每轮跑完的单一收尾钩子(不进 per-step 循环):
       1) 多步成功 → 自动提炼 SKILL;2) 失败 → 教师升级(可能替换 reply);3) 抽 ≤2 条用户事实进待确认记忆。
    全部 try 包裹,任何失败都不影响主回复。返回(可能被教师修正过的)reply。"""
    try:
        from .. import skills
        # 教师升级:失败时用强模型纠正 + 写技能(过 eval)。仅 run_agent 用(stream 已吐字,不回炉)。
        if skills.looks_failed(steps, reply):
            rescue = skills.teacher_rescue(messages, steps, reply)
            if rescue and rescue.get("corrective_reply"):
                reply = rescue["corrective_reply"]
        else:
            skills.maybe_distill(messages, steps, reply)
    except Exception:
        pass
    try:
        from ..memory import reflect
        reflect.extract_turn_facts(messages, reply)
    except Exception:
        pass
    return reply


def _personal_context(limit: int = 8) -> list[str]:
    """高重要性的已确认 fact/pattern 记忆——「关于你」的稳定上下文，每轮都带。"""
    try:
        from .. import db
        rows = db.list_memories_by_layer(["fact", "pattern"], limit=limit, status="active")
        return [str(r["statement"])[:160] for r in rows if str(r["statement"] or "").strip()]
    except Exception:
        return []


def run_agent(messages: list[dict]) -> dict:
    """messages: [{role: 'user'|'assistant', content: str}]，至少含一条 user。"""
    convo = _build_convo(messages)

    steps: list[dict] = []

    for _ in range(MAX_STEPS):
        try:
            raw = chat("agent", convo, temperature=0.2)
        except Exception as ex:  # noqa: BLE001
            from .. import obs
            obs.incr("llm.error")
            return {
                "reply": f"还没法思考：{ex}\n请在 config/models.toml 配置一个可用的模型接口"
                         f"（routing.agent 或 routing.default）。",
                "steps": steps, "pending_actions": [],
            }

        action = _parse_action(raw)

        if "final" in action and "action" not in action:
            reply = _post_run(messages, steps, action.get("final", ""))
            return {"reply": reply, "steps": steps, "pending_actions": []}

        act = action.get("action") or {}
        tool = act.get("tool", "")
        args = act.get("args", {}) or {}
        if not tool:
            reply = _post_run(messages, steps, action.get("final") or action.get("thought") or raw)
            return {"reply": reply, "steps": steps, "pending_actions": []}

        decision = gate.evaluate(tool, args)
        _record_gate(decision)

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
        convo.append({"role": "user", "content": _feedback_msg(tool, obs)})

    return {"reply": "（已达到最大步数，先停下。你可以让我继续。）",
            "steps": steps, "pending_actions": []}


def _feedback_msg(tool: str, obs: str) -> str:
    """把工具结果截断后喂回模型，避免跨步 prompt 膨胀。
    工具结果是不可信外部内容(read_file 读到的攻击文件、run_shell 跑到的爬取脚本、
    recall 出的被污染记忆)→ 用防注入护栏包裹(C1),避免 prompt injection。"""
    body = obs if len(obs) <= _OBS_FEEDBACK_LIMIT else (
        obs[:_OBS_FEEDBACK_LIMIT] + "\n…（结果较长已截断；如需完整内容请用更精确的命令/参数再查）"
    )
    from ..prompt_security import wrap_untrusted
    return f"[工具 {tool} 的结果]\n" + wrap_untrusted(body, source=f"tool:{tool}")


def run_agent_stream(messages: list[dict]) -> Iterator[dict]:
    """流式版 run_agent：逐步 yield 事件，让前端边产边渲染（核心提速项）。

    事件形态（每个都是 dict，由路由层序列化成 SSE）：
      {"type":"thought","text":...}          模型这一步的简短思考
      {"type":"tool_start","tool":...,"args":...}
      {"type":"tool_result","tool":...,"status":"done|denied","result":...}
      {"type":"token","text":...}            最终答复的增量文本（逐字流）
      {"type":"final","reply":...,"steps":[...]}            收尾
      {"type":"pending","reply":...,"pending_actions":[...],"steps":[...]}  需确认
      {"type":"error","message":...}
    复用 run_agent 的全部决策逻辑（_parse_action / gate / TOOLBUS / _PENDING），只是改成事件流。
    """
    convo = _build_convo(messages)

    steps: list[dict] = []

    for _ in range(MAX_STEPS):
        raw_parts: list[str] = []
        final_streamer = _FinalStreamer()
        streamed_final = False
        try:
            for piece in chat_stream("agent", convo, temperature=0.2):
                raw_parts.append(piece)
                # 边流边尝试提取 final 文本逐字下发（仅当这一步确实是 final）
                out = final_streamer.feed(piece)
                if out:
                    streamed_final = True
                    yield {"type": "token", "text": out}
        except Exception as ex:  # noqa: BLE001
            from .. import obs
            obs.incr("llm.error")
            yield {"type": "error",
                   "message": f"还没法思考：{ex}\n请在 config/models.toml 配置可用的模型接口。"}
            return

        raw = "".join(raw_parts)
        action = _parse_action(raw)

        # ---- 终止：最终答复 ----
        if "final" in action and "action" not in action:
            reply = action.get("final", "")
            if not streamed_final and reply:
                # 没能在流中增量吐出（如 JSON 结构特殊），收尾时补一次完整文本
                yield {"type": "token", "text": reply}
            yield {"type": "final", "reply": reply, "steps": steps}
            return

        act = action.get("action") or {}
        tool = act.get("tool", "")
        args = act.get("args", {}) or {}
        if not tool:
            reply = action.get("final") or action.get("thought") or raw
            if not streamed_final and reply:
                yield {"type": "token", "text": reply}
            yield {"type": "final", "reply": reply, "steps": steps}
            return

        thought = action.get("thought", "")
        if thought:
            yield {"type": "thought", "text": thought}
        yield {"type": "tool_start", "tool": tool, "args": args}

        decision = gate.evaluate(tool, args)
        _record_gate(decision)
        if decision == "deny":
            obs = "⛔ 该操作被安全策略拒绝，未执行。"
            _log_action(tool, args, obs, "denied")
            steps.append({"tool": tool, "args": args, "status": "denied"})
            yield {"type": "tool_result", "tool": tool, "status": "denied", "result": obs}
        elif decision == "confirm":
            pid = uuid.uuid4().hex[:12]
            _PENDING[pid] = {"tool": tool, "args": args, "thought": thought}
            steps.append({"tool": tool, "args": args, "status": "pending", "id": pid})
            note = thought or f"我准备执行 {tool}，属于高风险操作。"
            yield {
                "type": "pending",
                "reply": f"{note}\n\n这一步需要你确认后才会执行。",
                "steps": steps,
                "pending_actions": [{
                    "id": pid, "tool": tool, "args": args,
                    "reason": "不可逆 / 对外 / 触碰系统，按策略需你点头",
                }],
            }
            return
        else:  # auto
            obs = TOOLBUS.invoke(tool, args)
            _log_action(tool, args, obs, "auto")
            steps.append({"tool": tool, "args": args, "status": "done", "result": obs[:600]})
            yield {"type": "tool_result", "tool": tool, "status": "done", "result": obs[:600]}

        convo.append({"role": "assistant", "content": raw})
        convo.append({"role": "user", "content": _feedback_msg(tool, obs)})

    yield {"type": "final", "reply": "（已达到最大步数，先停下。你可以让我继续。）", "steps": steps}


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
