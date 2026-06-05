import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getMemories, runReflect, type MemoryRow } from "../api";

export function MemoryView() {
  const [memories, setMemories] = useState<MemoryRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  const load = () => getMemories().then(setMemories).catch(() => {});
  useEffect(() => { load(); }, []);

  async function reflect() {
    setBusy(true); setNote("");
    try {
      const r = await runReflect();
      setNote(r.note ? r.note : `归纳出 ${r.created} 条记忆（${r.used_llm ? "LLM" : "规则"}反思 ${r.events ?? 0} 条事件）`);
      await load();
    } finally { setBusy(false); }
  }

  return (
    <div>
      <div className="page-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h1>🧬 长期记忆 <span className="gradient-text">Reflection</span></h1>
          <p>Cortex 每晚把零散事件归纳成"值得长期记住"的偏好与结论。越用越懂你。</p>
        </div>
        <button className="btn primary" onClick={reflect} disabled={busy}>{busy ? "反思中…" : "立即反思"}</button>
      </div>

      {note && <motion.div className="card glow" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ marginBottom: 16 }}>✨ {note}</motion.div>}

      {memories.length === 0 && <div className="empty">还没有沉淀的记忆。先用一阵子，或点「立即反思」。</div>}

      <div className="grid cols-2">
        {memories.map((m, i) => (
          <motion.div className="card" key={m.id}
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span className="tile-label" style={{ textTransform: "none" }}>{m.subject || m.type}</span>
              <span className="port" style={{ marginLeft: "auto" }}>★ {m.salience.toFixed(2)}</span>
            </div>
            <div style={{ lineHeight: 1.6 }}>{m.statement}</div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
