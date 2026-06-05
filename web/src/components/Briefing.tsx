import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BriefingData, BriefingItem, getBriefing, runIngest, sendFeedback } from "../api";

function Section({ title, items, onRefresh }: { title: string; items: BriefingItem[]; onRefresh: () => void }) {
  return (
    <section className="section">
      <h2>{title}<span className="tag">{items.length}</span></h2>
      {items.length === 0 && <div className="empty">目前没有通过过滤的条目。</div>}
      {items.map((it, i) => (
        <motion.article key={it.event_id} className={`news-card ${it.triage}`}
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
          <div className="row">
            <div className="title">{it.url ? <a href={it.url} target="_blank" rel="noreferrer">{it.title}</a> : it.title}</div>
            <div className="score">{it.score.toFixed(2)}</div>
          </div>
          <p className="take">💡 {it.take}</p>
          <div className="meta">{it.source} · {it.kind} · {it.triage}</div>
          <div className="actions">
            <button className="btn sm" onClick={() => sendFeedback(it.event_id, "important").then(onRefresh)}>重要</button>
            <button className="btn sm ghost" onClick={() => sendFeedback(it.event_id, "useless").then(onRefresh)}>没用</button>
          </div>
        </motion.article>
      ))}
    </section>
  );
}

export function Briefing() {
  const [data, setData] = useState<BriefingData | null>(null);
  const [error, setError] = useState<string>("");
  const refresh = () => getBriefing().then(setData).catch((err) => setError(String(err)));
  useEffect(() => { refresh(); }, []);

  return (
    <div>
      <div className="page-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h1>📰 资讯简报 <span className="gradient-text">Feeds</span></h1>
          <p>过滤噪音，保留判断。业务与生活分开看，重要信息会实时弹窗。</p>
        </div>
        <button className="btn primary" onClick={() => runIngest().then(refresh)}>手动采集</button>
      </div>
      {error && <div className="error">{error}</div>}
      {!data && !error && <div className="loading">加载 Cortex 简报…</div>}
      {data && (
        <div className="grid cols-2">
          <Section title="🏢 业务" items={data.business} onRefresh={refresh} />
          <Section title="🏠 生活" items={data.life} onRefresh={refresh} />
        </div>
      )}
    </div>
  );
}
