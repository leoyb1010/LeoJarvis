import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getSystemStatus } from "../../api";

export function SystemView() {
  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    getSystemStatus().then((s) => setRaw(s.raw)).finally(() => setLoading(false));
  };
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);

  return (
    <div>
      <div className="page-head">
        <h1>🖥 系统状态 <span className="gradient-text">SystemGuard</span></h1>
        <p>磁盘、CPU 负载、内存压力与吃资源的进程。后台每 5 分钟自动巡检，异常会实时推送。</p>
      </div>
      <motion.div className="card glow" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div className="tile-label">实时快照</div>
          <button className="btn sm" onClick={load} disabled={loading}>{loading ? "刷新中…" : "刷新"}</button>
        </div>
        <pre className="toolResult" style={{ maxWidth: "100%", maxHeight: "none" }}>{raw || "加载中…"}</pre>
      </motion.div>
    </div>
  );
}
