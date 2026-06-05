import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  agentChat, approveAction,
  type AgentStep, type ChatMsg, type PendingAction,
} from "../api";

type Turn =
  | { kind: "msg"; role: "user" | "assistant"; content: string }
  | { kind: "steps"; steps: AgentStep[] }
  | { kind: "pending"; actions: PendingAction[] }
  | { kind: "result"; text: string };

const SUGGESTIONS = [
  "看看我磁盘为什么快满了",
  "本地服务都还活着吗",
  "扫描一下当前电脑状态",
  "列出在管的子 agent",
];

const enter = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { ease: "easeOut" as const } };

export function Agent() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useRef<ChatMsg[]>([]);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    setInput(""); setBusy(true);
    setTurns((t) => [...t, { kind: "msg", role: "user", content }]);
    history.current.push({ role: "user", content });
    try {
      const res = await agentChat(history.current);
      if (res.steps.length) setTurns((t) => [...t, { kind: "steps", steps: res.steps }]);
      setTurns((t) => [...t, { kind: "msg", role: "assistant", content: res.reply }]);
      history.current.push({ role: "assistant", content: res.reply });
      if (res.pending_actions.length) setTurns((t) => [...t, { kind: "pending", actions: res.pending_actions }]);
    } catch (e: any) {
      setTurns((t) => [...t, { kind: "msg", role: "assistant", content: `出错了：${e.message}` }]);
    } finally { setBusy(false); }
  }

  async function decide(a: PendingAction, decision: "approve" | "reject") {
    const res = await approveAction(a.id, decision);
    const text = decision === "reject" ? "已拒绝，未执行。" : `已执行 ${res.tool ?? a.tool}：\n${res.result ?? ""}`;
    setTurns((t) => [...t, { kind: "result", text }]);
    if (res.executed) history.current.push({ role: "user", content: `[已批准执行 ${a.tool}]\n${res.result}` });
  }

  return (
    <div>
      <div className="page-head">
        <h1>🧠 中枢对话 <span className="gradient-text">对话即指挥</span></h1>
        <p>直接吩咐它，它会调工具在你机器上动手。低风险自动执行，高风险弹卡片等你点头。</p>
      </div>

      <div className="chat-wrap">
        <div className="chat" ref={scroller}>
          {turns.length === 0 && (
            <motion.div className="empty" {...enter}>对 Cortex 说点什么，或点下面的快捷指令试试。</motion.div>
          )}
          <AnimatePresence initial={false}>
            {turns.map((turn, i) => {
              if (turn.kind === "msg")
                return (
                  <motion.div key={i} className={`bubble ${turn.role}`} {...enter}>{turn.content}</motion.div>
                );
              if (turn.kind === "steps")
                return (
                  <motion.div key={i} className="steps" {...enter}>
                    {turn.steps.map((s, j) => (
                      <motion.div key={j} className={`step ${s.status}`}
                        initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: j * 0.06 }}>
                        <code>{s.tool}</code><span className="stepStatus">{s.status}</span>
                        {s.result && <pre>{s.result}</pre>}
                      </motion.div>
                    ))}
                  </motion.div>
                );
              if (turn.kind === "result")
                return <motion.pre key={i} className="toolResult" {...enter}>{turn.text}</motion.pre>;
              return (
                <motion.div key={i} className="card approve-card" {...enter}>
                  <div style={{ fontWeight: 700, marginBottom: 8 }}>⚠️ 待你确认</div>
                  {turn.actions.map((a) => (
                    <div key={a.id}>
                      <div className="meta" style={{ color: "var(--text-dim)", fontSize: 13 }}>
                        工具 <code style={{ color: "var(--accent-3)" }}>{a.tool}</code> · {a.reason}
                      </div>
                      <pre>{JSON.stringify(a.args, null, 2)}</pre>
                      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                        <button className="btn primary sm" onClick={() => decide(a, "approve")}>批准执行</button>
                        <button className="btn danger sm" onClick={() => decide(a, "reject")}>拒绝</button>
                      </div>
                    </div>
                  ))}
                </motion.div>
              );
            })}
          </AnimatePresence>
          {busy && <motion.div className="typing" {...enter}><i /><i /><i /></motion.div>}
        </div>

        <div className="suggest">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>{s}</button>
          ))}
        </div>

        <div className="composer">
          <input value={input} placeholder="对 Cortex 说点什么…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(input)} />
          <button className="btn primary" onClick={() => send(input)} disabled={busy}>发送</button>
        </div>
      </div>
    </div>
  );
}
