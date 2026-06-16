import { useEffect, useRef, useState, type ReactNode } from "react";
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
  "诊断磁盘和 RAM 压力",
  "检查本地服务在线率",
  "刷新本机健康报告",
  "扫描今天的高价值情报",
  "把这个想法写入个人记事",
];

const enter = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { ease: "easeOut" as const } };

function cleanLLMText(value: string) {
  return String(value || "")
    .replace(/\r/g, "")
    .replace(/```[a-zA-Z0-9_-]*\n?/g, "")
    .replace(/```/g, "")
    .split("\n")
    .map((line) => line
      .replace(/^\s*(assistant|final|analysis|commentary)\s*[:：]\s*/i, "")
      .replace(/^\s{0,3}#{1,6}\s+/, "")
      .replace(/^\s*>\s?/, "")
      .replace(/^\s*[-*]\s+/, "• ")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .trimEnd())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function tryJson(value: string) {
  const text = value.trim();
  if (!/^[\[{]/.test(text)) return null;
  try { return JSON.parse(text); } catch { return null; }
}

function valuePreview(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "string") return cleanLLMText(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(valuePreview).join("，");
  return JSON.stringify(value, null, 2);
}

function JsonSummary({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <div className="agent-json-summary">
        {value.slice(0, 8).map((item, i) => (
          <div className="agent-json-row" key={i}>
            <b>{String(i + 1).padStart(2, "0")}</b>
            <span>{valuePreview(item)}</span>
          </div>
        ))}
      </div>
    );
  }
  if (!isPlainObject(value)) return <p>{valuePreview(value)}</p>;
  return (
    <div className="agent-json-summary">
      {Object.entries(value).slice(0, 12).map(([key, raw]) => (
        <div className="agent-json-row" key={key}>
          <b>{key}</b>
          <span>{valuePreview(raw)}</span>
        </div>
      ))}
    </div>
  );
}

function Pill({ text, tone = "neutral" }: { text: string; tone?: "ok" | "off" | "info" | "warn" | "neutral" }) {
  const map: Record<string, [string, string]> = {
    ok: ["rgba(40,167,69,0.16)", "#2ea043"],
    off: ["rgba(225,75,75,0.14)", "#e14b4b"],
    info: ["rgba(55,138,221,0.14)", "#378add"],
    warn: ["rgba(186,117,23,0.16)", "#ba7517"],
    neutral: ["rgba(127,127,127,0.14)", "var(--muted)"],
  };
  const [bg, color] = map[tone] || map.neutral;
  return <span style={{ fontSize: 11, padding: "1px 7px", borderRadius: 6, background: bg, color, whiteSpace: "nowrap" }}>{text}</span>;
}

function CardGrid({ children }: { children: ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>{children}</div>;
}

function Cell({ children }: { children: ReactNode }) {
  return <div style={{ background: "rgba(127,127,127,0.08)", borderRadius: 8, padding: "9px 11px" }}>{children}</div>;
}

function AgentRosterCard({ agents }: { agents: any[] }) {
  return (
    <CardGrid>
      {agents.map((a) => (
        <Cell key={a.name}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{a.display || a.name}</div>
          <div style={{ display: "flex", gap: 5, marginTop: 5, flexWrap: "wrap" }}>
            <Pill text={a.installed ? "已装" : "未装"} tone={a.installed ? "ok" : "neutral"} />
            <Pill text={a.run_supported === "confirmed" ? "驱动✓" : a.run_supported || "—"} tone={a.run_supported === "confirmed" ? "info" : "warn"} />
          </div>
          {a.version && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 5 }}>{String(a.version).slice(0, 30)}</div>}
        </Cell>
      ))}
    </CardGrid>
  );
}

function ServicesCard({ rows }: { rows: any[] }) {
  return (
    <CardGrid>
      {rows.slice(0, 12).map((s, i) => (
        <Cell key={s.name + i}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{s.display || s.name}{s.port ? <span style={{ color: "var(--muted)", fontWeight: 400 }}> :{s.port}</span> : null}</div>
          <div style={{ display: "flex", gap: 5, marginTop: 5, flexWrap: "wrap" }}>
            <Pill text={s.health === "online" ? "在线" : s.health === "offline" ? "离线" : "未知"} tone={s.health === "online" ? "ok" : s.health === "offline" ? "off" : "neutral"} />
            {s.exposed && <Pill text="对外暴露" tone="warn" />}
            {s.managed === false && <Pill text="待纳管" tone="neutral" />}
          </div>
        </Cell>
      ))}
    </CardGrid>
  );
}

function CapsulesCard({ caps }: { caps: any[] }) {
  return (
    <CardGrid>
      {caps.map((c) => (
        <Cell key={c.key}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{c.flagship ? "🚩 " : ""}{c.name}</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>{c.desc}</div>
          <div style={{ marginTop: 5 }}><Pill text={`${c.tool_count} 工具`} tone={c.installed ? "info" : "neutral"} /></div>
        </Cell>
      ))}
    </CardGrid>
  );
}

function HoroscopeCard({ h }: { h: any }) {
  return (
    <div style={{ background: "rgba(127,127,127,0.08)", borderRadius: 10, padding: "12px 14px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 15 }}>{h.title || `今日星座 · ${h.sign || ""}`}</div>
        {typeof h.score === "number" && <Pill text={`${h.score} 分 · ${h.level || ""}`} tone={h.score >= 60 ? "ok" : h.score >= 40 ? "info" : "warn"} />}
      </div>
      {h.advice && <p style={{ margin: "8px 0 0", fontSize: 13 }}>{h.advice}</p>}
      <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 12, color: "var(--muted)", flexWrap: "wrap" }}>
        {h.lucky_color && <span>幸运色 {h.lucky_color}</span>}
        {h.lucky_number != null && <span>幸运数 {h.lucky_number}</span>}
        {Array.isArray(h.yi) && h.yi.length > 0 && <span>宜 {h.yi.join("、")}</span>}
        {Array.isArray(h.ji) && h.ji.length > 0 && <span>忌 {h.ji.join("、")}</span>}
      </div>
    </div>
  );
}

// 生成式卡片：按工具输出的结构渲染成类型化卡片，识别不到就回退裸 JSON。
function TypedCard({ value }: { value: unknown }) {
  const arr = Array.isArray(value) ? (value as any[]) : null;
  const obj = isPlainObject(value) ? (value as Record<string, any>) : null;
  if (arr && arr.length && isPlainObject(arr[0]) && "run_supported" in arr[0] && "installed" in arr[0])
    return <AgentRosterCard agents={arr} />;
  if (obj && Array.isArray(obj.agents) && obj.agents[0] && "run_supported" in obj.agents[0])
    return <AgentRosterCard agents={obj.agents} />;
  if (arr && arr.length && isPlainObject(arr[0]) && "exposed" in arr[0] && "health" in arr[0])
    return <ServicesCard rows={arr} />;
  if (obj && Array.isArray(obj.capsules))
    return <CapsulesCard caps={obj.capsules} />;
  if (obj && obj.kind === "horoscope")
    return <HoroscopeCard h={obj} />;
  return <JsonSummary value={value} />;
}

function RichMessage({ text }: { text: string }) {
  const cleaned = cleanLLMText(text);
  if (!cleaned) return null;
  const json = tryJson(cleaned);
  if (json) return <TypedCard value={json} />;
  const blocks = cleaned.split(/\n{2,}/).map((x) => x.trim()).filter(Boolean);
  return (
    <div className="rich-message">
      {blocks.map((block, i) => {
        const lines = block.split("\n").map((x) => x.trim()).filter(Boolean);
        const bulletLines = lines.filter((line) => /^(•|\d+[.)])\s+/.test(line));
        const kvLines = lines
          .map((line) => line.match(/^([^：:\n]{2,22})[：:]\s*(.+)$/))
          .filter(Boolean) as RegExpMatchArray[];
        const blockJson = tryJson(block);
        if (blockJson) return <JsonSummary value={blockJson} key={i} />;
        if (lines.length > 1 && bulletLines.length === lines.length) {
          return (
            <ul key={i}>
              {lines.map((line, idx) => <li key={idx}>{line.replace(/^(•|\d+[.)])\s+/, "")}</li>)}
            </ul>
          );
        }
        if (lines.length > 1 && kvLines.length >= Math.max(2, lines.length - 1)) {
          return (
            <div className="agent-kv" key={i}>
              {kvLines.map((m, idx) => (
                <div key={idx}><b>{m[1]}</b><span>{m[2]}</span></div>
              ))}
            </div>
          );
        }
        return <p key={i}>{block}</p>;
      })}
    </div>
  );
}

export function AgentConsole({ compact = false, onClose, hideHead = false }: { compact?: boolean; onClose?: () => void; hideHead?: boolean }) {
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
    <div className={compact ? "agent-console compact" : "agent-console"}>
      {compact ? (
        <div className="floating-agent-head">
          <div>
            <b>Jarvis</b>
            <span>本机行动中枢 · 高风险动作会等待确认</span>
          </div>
          <button className="icon-btn" onClick={onClose}>关闭</button>
        </div>
      ) : hideHead ? null : (
        <div className="page-head">
          <h1>Command Center</h1>
          <p>直接交代任务，它会调用本机工具执行。低风险自动完成，高风险动作先停在确认卡片里。</p>
        </div>
      )}

      <div className={compact ? "chat-wrap floating-chat-wrap" : "chat-wrap"}>
        <div className="chat" ref={scroller}>
          {turns.length === 0 && (
            <motion.div className="empty" {...enter}>输入任务，或选择下方快捷动作。</motion.div>
          )}
          <AnimatePresence initial={false}>
            {turns.map((turn, i) => {
              if (turn.kind === "msg")
                return (
                  <motion.div key={i} className={`bubble ${turn.role}`} {...enter}>
                    {turn.role === "assistant" ? <RichMessage text={turn.content} /> : turn.content}
                  </motion.div>
                );
              if (turn.kind === "steps")
                return (
                  <motion.div key={i} className="steps" {...enter}>
                    {turn.steps.map((s, j) => (
                      <motion.div key={j} className={`step ${s.status}`}
                        initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: j * 0.06 }}>
                        <code>{s.tool}</code><span className="stepStatus">{s.status}</span>
                        {s.result && <div className="step-output"><RichMessage text={s.result} /></div>}
                      </motion.div>
                    ))}
                  </motion.div>
                );
              if (turn.kind === "result")
                return <motion.div key={i} className="toolResult" {...enter}><RichMessage text={turn.text} /></motion.div>;
              return (
                <motion.div key={i} className="card approve-card" {...enter}>
                  <div style={{ fontWeight: 700, marginBottom: 8 }}>待你确认</div>
                  {turn.actions.map((a) => (
                    <div key={a.id}>
                      <div className="meta" style={{ color: "var(--muted)", fontSize: 13 }}>
                        工具 <code style={{ color: "var(--accent)" }}>{a.tool}</code> · {a.reason}
                      </div>
                      <div className="approve-args"><JsonSummary value={a.args} /></div>
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
          <input value={input} placeholder="输入任务或问题…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(input)} />
          <button className="btn primary" onClick={() => send(input)} disabled={busy}>发送</button>
        </div>
      </div>
    </div>
  );
}

export function Agent() {
  return <AgentConsole />;
}

export function FloatingAgent() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const openCommand = () => setOpen(true);
    window.addEventListener("leojarvis:open-command", openCommand);
    return () => window.removeEventListener("leojarvis:open-command", openCommand);
  }, []);

  return (
    <div className={`floating-agent ${open ? "open" : ""}`}>
      <AnimatePresence>
        {open ? (
          <motion.div
            className="floating-agent-panel"
            initial={{ opacity: 0, y: 18, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 18, scale: 0.98 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
          >
            <AgentConsole compact onClose={() => setOpen(false)} />
          </motion.div>
        ) : null}
      </AnimatePresence>
      <button
        className="agent-fab"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "关闭 Jarvis 助手" : "打开 Jarvis 助手"}
      >
        <img src="/brand-mark.png" alt="" />
        <span>{open ? "Close" : "Jarvis"}</span>
      </button>
    </div>
  );
}
