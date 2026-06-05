import { motion } from "framer-motion";

export type ViewId = "chat" | "dashboard" | "system" | "services" | "agents" | "journal" | "feeds" | "memory";

const NAV: { id: ViewId; ico: string; label: string }[] = [
  { id: "dashboard", ico: "◇", label: "仪表盘" },
  { id: "chat", ico: "🧠", label: "中枢对话" },
  { id: "system", ico: "🖥", label: "系统状态" },
  { id: "services", ico: "⚙", label: "本地服务" },
  { id: "agents", ico: "🛰", label: "遥控 Agent" },
  { id: "memory", ico: "🧬", label: "长期记忆" },
  { id: "journal", ico: "📓", label: "日记" },
  { id: "feeds", ico: "📰", label: "资讯简报" },
];

export function Sidebar({
  active, onNavigate, theme, onToggleTheme,
}: {
  active: ViewId;
  onNavigate: (v: ViewId) => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo">C</div>
        <div>
          <div className="name">Cortex</div>
          <div className="sub">Personal Agent OS</div>
        </div>
      </div>

      {NAV.map((n) => (
        <motion.div
          key={n.id}
          className={`nav-item ${active === n.id ? "active" : ""}`}
          onClick={() => onNavigate(n.id)}
          whileTap={{ scale: 0.97 }}
        >
          <span className="ico">{n.ico}</span>
          <span>{n.label}</span>
        </motion.div>
      ))}

      <div className="spacer" />

      <div className="theme-toggle" onClick={onToggleTheme}>
        <span>{theme === "dark" ? "🌙 暗色" : "☀️ 亮色"}</span>
        <span style={{ color: "var(--text-faint)" }}>切换</span>
      </div>
    </aside>
  );
}
