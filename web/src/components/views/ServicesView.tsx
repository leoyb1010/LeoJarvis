import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getServices, type ServiceRow } from "../../api";

export function ServicesView() {
  const [rows, setRows] = useState<ServiceRow[]>([]);
  const load = () => getServices().then(setRows).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);

  return (
    <div>
      <div className="page-head">
        <h1>⚙ 本地服务 <span className="gradient-text">ServiceOps</span></h1>
        <p>ollama / leonote / leomoney / leoapi 等本地服务的在线状态。重启等操作请在「中枢对话」里说，会先征求你确认。</p>
      </div>
      <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        {rows.length === 0 && <div className="empty">加载中…</div>}
        {rows.map((s, i) => (
          <motion.div className="svc-row" key={s.name}
            initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
            <span className={`dot ${s.online ? "on" : "off"}`} />
            <span className="nm">{s.name}</span>
            <span className="port">127.0.0.1:{s.port}{s.pid ? ` · pid ${s.pid}` : ""}</span>
            <div className="right">
              <span style={{ color: s.online ? "var(--good)" : "var(--text-faint)", fontWeight: 600, fontSize: 13 }}>
                {s.online ? "在线" : "离线"}
              </span>
              {s.can_restart && <span className="port" title="已配置 start 命令，可让中枢重启">· 可重启</span>}
            </div>
          </motion.div>
        ))}
      </motion.div>
    </div>
  );
}
