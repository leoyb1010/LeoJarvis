import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { addJournal, getJournal, type JournalRow } from "../../api";

export function JournalView() {
  const [rows, setRows] = useState<JournalRow[]>([]);
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState("");

  const load = (query = "") => getJournal(query).then(setRows).catch(() => {});
  useEffect(() => { load(); }, []);

  async function save() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    await addJournal(text);
    load(q);
  }

  return (
    <div>
      <div className="page-head">
        <h1>📓 日记 <span className="gradient-text">Journal</span></h1>
        <p>随手记，沉淀成可检索的长期记忆。在「中枢对话」里说「把…记进日记」也会进这里。</p>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <textarea
          value={draft}
          placeholder="此刻在想什么…"
          onChange={(e) => setDraft(e.target.value)}
          style={{
            width: "100%", minHeight: 80, resize: "vertical", background: "var(--bg-2)",
            border: "1px solid var(--border)", borderRadius: 12, padding: 14, color: "var(--text)",
            fontFamily: "inherit", fontSize: 15,
          }}
        />
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <button className="btn primary" onClick={save} disabled={!draft.trim()}>记一笔</button>
        </div>
      </div>

      <div className="composer" style={{ marginBottom: 18 }}>
        <input value={q} placeholder="检索日记…"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load(q)} />
        <button className="btn" onClick={() => load(q)}>检索</button>
      </div>

      <AnimatePresence>
        {rows.length === 0 && <div className="empty">还没有日记。</div>}
        {rows.map((j, i) => (
          <motion.div className="journal-entry" key={j.id}
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ delay: i * 0.03 }}>
            <div className="when">{new Date(j.ts).toLocaleString("zh-CN")}</div>
            <div className="body">{j.content}</div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
