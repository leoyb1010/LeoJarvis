import { useEffect, useState } from "react";
import { motion, type Variants } from "framer-motion";
import {
  getAgents, getJournal, getServices, getSystemStatus,
  type AgentRow, type JournalRow, type ServiceRow,
} from "../api";

function parseSystem(raw: string) {
  const disk = raw.match(/已用[^()]*\((\d+)%\)/);
  const load = raw.match(/负载\(1\/5\/15min\):\s*([\d.]+)/);
  return { diskPct: disk ? Number(disk[1]) : null, load: load ? Number(load[1]) : null };
}

const card: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.06, ease: "easeOut" } }),
};

export function Dashboard() {
  const [sys, setSys] = useState<{ diskPct: number | null; load: number | null }>({ diskPct: null, load: null });
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [journal, setJournal] = useState<JournalRow[]>([]);

  useEffect(() => {
    const load = () => {
      getSystemStatus().then((s) => setSys(parseSystem(s.raw))).catch(() => {});
      getServices().then(setServices).catch(() => {});
      getAgents().then(setAgents).catch(() => {});
      getJournal().then(setJournal).catch(() => {});
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const online = services.filter((s) => s.online).length;
  const running = agents.filter((a) => a.status === "running").length;

  const tiles = [
    {
      label: "磁盘占用", value: sys.diskPct != null ? `${sys.diskPct}%` : "—",
      foot: sys.diskPct != null && sys.diskPct >= 90 ? "⚠️ 紧张" : "健康", bar: sys.diskPct ?? 0,
    },
    {
      label: "CPU 负载(1min)", value: sys.load != null ? sys.load.toFixed(2) : "—",
      foot: "实时", mono: true,
    },
    {
      label: "本地服务", value: `${online}/${services.length}`,
      foot: `${online} 个在线`,
    },
    {
      label: "运行中 Agent", value: `${running}`,
      foot: `${agents.length} 个在管`,
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h1>早安，这是你的 <span className="gradient-text">指挥台</span></h1>
        <p>Cortex 在后台替你盯着机器、服务、子 agent 和资讯。有需要直接去「中枢对话」吩咐它。</p>
      </div>

      <div className="grid cols-3" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        {tiles.map((t, i) => (
          <motion.div className="card glow" key={t.label} custom={i} variants={card} initial="hidden" animate="show">
            <div className="tile-label">{t.label}</div>
            <div className={`tile-value ${t.mono ? "mono" : ""}`}>{t.value}</div>
            {"bar" in t && t.bar != null ? (
              <div className="bar"><span style={{ width: `${Math.min(t.bar as number, 100)}%` }} /></div>
            ) : null}
            <div className="tile-foot">{t.foot}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid cols-2" style={{ marginTop: 18 }}>
        <motion.div className="card" custom={4} variants={card} initial="hidden" animate="show">
          <div className="tile-label" style={{ marginBottom: 12 }}>服务概览</div>
          {services.length === 0 && <div className="empty">暂无数据</div>}
          {services.map((s) => (
            <div className="svc-row" key={s.name}>
              <span className={`dot ${s.online ? "on" : "off"}`} />
              <span className="nm">{s.name}</span>
              <span className="port">:{s.port}</span>
              <span className="right" style={{ color: s.online ? "var(--good)" : "var(--text-faint)" }}>
                {s.online ? "在线" : "离线"}
              </span>
            </div>
          ))}
        </motion.div>

        <motion.div className="card" custom={5} variants={card} initial="hidden" animate="show">
          <div className="tile-label" style={{ marginBottom: 12 }}>最近日记</div>
          {journal.length === 0 && <div className="empty">还没有日记。去「中枢对话」说「把…记进日记」。</div>}
          {journal.slice(0, 4).map((j) => (
            <div className="svc-row" key={j.id} style={{ display: "block" }}>
              <div className="port">{new Date(j.ts).toLocaleString("zh-CN")}</div>
              <div style={{ marginTop: 4 }}>{j.content.slice(0, 80)}</div>
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
