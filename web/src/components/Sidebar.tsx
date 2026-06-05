import { motion } from "framer-motion";

export type ViewId = "dashboard" | "system" | "intelligence" | "notes" | "memory";

const SECTIONS: { title: string; items: { id: ViewId; label: string }[] }[] = [
  {
    title: "核心",
    items: [
      { id: "dashboard", label: "全景驾驶舱" },
    ],
  },
  {
    title: "运维",
    items: [
      { id: "system", label: "系统状态" },
    ],
  },
  {
    title: "记录",
    items: [
      { id: "intelligence", label: "情报简报" },
      { id: "notes", label: "个人记事" },
    ],
  },
];

export function Sidebar({
  active, onNavigate, theme, onToggleTheme, collapsed, onToggleCollapsed,
}: {
  active: ViewId;
  onNavigate: (v: ViewId) => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <button
        className="sidebar-toggle"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "展开侧边栏" : "隐藏侧边栏"}
        title={collapsed ? "展开侧边栏" : "隐藏侧边栏"}
      >
        {collapsed ? "›" : "‹"}
      </button>
      <div className="brand">
          <div className="logo leo-logo">Leo</div>
        <div>
          <div className="name">Cortex</div>
          <div className="sub">本地个人系统</div>
        </div>
      </div>

      <button
        className={`memory-quick ${active === "memory" ? "active" : ""}`}
        onClick={() => onNavigate("memory")}
        title="待确认长期记忆"
      >
        <span>记忆</span>
        <b>待确认</b>
      </button>

      <nav className="nav">
        {SECTIONS.map((sec) => (
          <div key={sec.title}>
            <div className="nav-section">{sec.title}</div>
            {sec.items.map((n) => (
              <motion.div
                key={n.id}
                className={`nav-item ${active === n.id ? "active" : ""}`}
                onClick={() => onNavigate(n.id)}
                whileTap={{ scale: 0.98 }}
                title={n.label}
              >
                <span className="ico" />
                <span>{n.label}</span>
              </motion.div>
            ))}
          </div>
        ))}
      </nav>

      <div className="spacer" />

      <div className="theme-toggle" onClick={onToggleTheme}>
        <span>{theme === "dark" ? "Dark" : "Light"}</span>
        <span className="tt-hint">{theme === "dark" ? "Night" : "Day"}</span>
      </div>
    </aside>
  );
}
