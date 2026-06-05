import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getAgents, type AgentRow } from "../../api";

export function AgentsView() {
  const [rows, setRows] = useState<AgentRow[]>([]);
  const load = () => getAgents().then(setRows).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, []);

  return (
    <div>
      <div className="page-head">
        <h1>🛰 遥控 Agent <span className="gradient-text">AgentControl</span></h1>
        <p>把任务作为后台子 agent 派发出去，随时看状态和输出。派发/停止请在「中枢对话」里说，例如「派个 agent 跑 npm run build」。</p>
      </div>
      {rows.length === 0 && <div className="empty">当前没有在管的子 agent。</div>}
      <div className="grid cols-2">
        {rows.map((a, i) => (
          <motion.div className="card" key={a.id}
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className={`dot ${a.status === "running" ? "on" : "off"}`} />
              <span className="nm" style={{ fontWeight: 700 }}>{a.name}</span>
              <span className="port" style={{ marginLeft: "auto" }}>[{a.id}] pid {a.pid}</span>
            </div>
            <pre className="toolResult" style={{ maxWidth: "100%", marginTop: 12 }}>{a.command}</pre>
            <div className="tile-foot">
              {a.status === "running" ? "🟢 运行中" : "⚪️ 已停止"} · 启动于 {new Date(a.started * 1000).toLocaleTimeString("zh-CN")}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
