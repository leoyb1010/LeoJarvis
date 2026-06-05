import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  decideMemory,
  getMemories,
  getPendingMemories,
  runReflect,
  type MemoryRow,
} from "../api";

function scorePct(value: number) {
  return `${Math.round(Math.max(0, Math.min(1, value || 0)) * 100)}%`;
}

function fmtTime(ts?: number) {
  return ts ? new Date(ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "未知时间";
}

function memoryTypeLabel(value?: string | null) {
  return ({
    semantic: "语义记忆",
    episodic: "事件记忆",
    event_text: "事件文本",
  } as Record<string, string>)[value || ""] || value || "未分类";
}

function memorySubjectLabel(value?: string | null, type?: string | null) {
  if (!value) return memoryTypeLabel(type);
  if (value.startsWith("rss:")) return "RSS 资讯";
  if (value.startsWith("intel:")) return "情报中心";
  if (value === "reflection") return "记忆反思";
  return value;
}

function memoryStatementText(value: string) {
  return value
    .replace(/rss:[A-Za-z0-9_.-]+/g, "RSS 资讯")
    .replace(/\bagent\b/gi, "智能体");
}

export function MemoryView() {
  const [memories, setMemories] = useState<MemoryRow[]>([]);
  const [pending, setPending] = useState<MemoryRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  const load = async () => {
    const [activeRows, pendingRows] = await Promise.all([getMemories(), getPendingMemories()]);
    setMemories(activeRows);
    setPending(pendingRows);
  };

  useEffect(() => { load().catch(() => {}); }, []);

  async function reflect() {
    setBusy(true);
    setNote("");
    try {
      const r = await runReflect();
      setNote(r.note || `已生成 ${r.created} 条待确认记忆。`);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function decide(id: string, decision: "accept" | "reject" | "later") {
    await decideMemory(id, decision);
    await load();
  }

  const typeRows = useMemo(() => {
    const counts = memories.reduce<Record<string, number>>((acc, row) => {
      const key = memoryTypeLabel(row.type);
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts);
  }, [memories]);

  return (
    <div>
      <div className="page-head memory-head">
        <div>
          <div className="kicker">确认式长期记忆</div>
          <h1>长期记忆</h1>
          <p>先候选，再确认。系统只会生成待确认记忆，必须由你选择确认保存、拒绝保存或稍后处理，才会影响后续召回和个性化判断。</p>
        </div>
        <button className="btn primary" onClick={reflect} disabled={busy}>{busy ? "生成中" : "生成候选记忆"}</button>
      </div>

      {note ? <motion.div className="card glow memory-note" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>{note}</motion.div> : null}

      <div className="memory-layout">
        <section className="memory-queue">
          <div className="memory-stats">
            <div className="card"><span>待确认</span><b>{pending.filter((m) => m.status !== "later").length}</b></div>
            <div className="card"><span>稍后处理</span><b>{pending.filter((m) => m.status === "later").length}</b></div>
            <div className="card"><span>已确认</span><b>{memories.length}</b></div>
          </div>

          <div className="panel-title">待确认长期记忆</div>
          {pending.length === 0 ? <div className="empty">当前没有待确认记忆。资讯反馈或反思生成后会先出现在这里。</div> : pending.map((m, i) => (
            <motion.article className={`memory-candidate ${m.status === "later" ? "later" : ""}`} key={m.id}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <div className="memory-card-top">
                <span>{memorySubjectLabel(m.subject, m.type)}</span>
                <b>{m.status === "later" ? "稍后" : "待确认"}</b>
              </div>
              <p>{memoryStatementText(m.statement)}</p>
              <div className="memory-bars">
                <div><span>重要度</span><i><b style={{ width: scorePct(m.salience) }} /></i></div>
                <div><span>置信度</span><i><b style={{ width: scorePct(m.confidence) }} /></i></div>
              </div>
              <div className="actions">
                <button className="btn sm primary" onClick={() => decide(m.id, "accept")}>确认保存</button>
                <button className="btn sm ghost" onClick={() => decide(m.id, "later")}>稍后处理</button>
                <button className="btn sm danger" onClick={() => decide(m.id, "reject")}>拒绝保存</button>
              </div>
            </motion.article>
          ))}
        </section>

        <aside className="memory-active">
          <div className="card memory-map">
            <div className="panel-title">记忆分类</div>
            {typeRows.length === 0 ? <div className="empty">还没有已确认的长期记忆。</div> : typeRows.map(([type, count]) => (
              <div className="memory-type" key={type}>
                <span>{type}</span>
                <div><i style={{ width: `${Math.max(8, count * 12)}%` }} /></div>
                <b>{count}</b>
              </div>
            ))}
          </div>

          <div className="panel-title">已确认记忆</div>
          <div className="active-memory-list">
            {memories.length === 0 ? <div className="empty">确认候选后会出现在这里。</div> : memories.map((m, i) => (
              <motion.article className="active-memory" key={m.id}
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.025 }}>
                <div>
                  <span>{memorySubjectLabel(m.subject, m.type)}</span>
                  <em>{fmtTime(m.updated_ts)}</em>
                </div>
                <p>{memoryStatementText(m.statement)}</p>
              </motion.article>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
