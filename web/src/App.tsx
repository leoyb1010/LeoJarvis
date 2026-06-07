import { useEffect, useState, type ComponentType } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar, type ViewId } from "./components/Sidebar";
import { NotifyToast } from "./components/NotifyToast";
import { FloatingAgent } from "./components/Agent";
import { Dashboard } from "./components/Dashboard";
import { StatusBar } from "./components/StatusBar";
import { SystemView } from "./components/views/SystemView";
import { PersonalNotesView } from "./components/views/PersonalNotesView";
import { IntelligenceView } from "./components/views/IntelligenceView";
import { SettingsView } from "./components/views/SettingsView";
import { MemoryView } from "./components/MemoryView";

type ThemeMode = "auto" | "dark" | "light";

const VIEWS: Record<ViewId, ComponentType> = {
  dashboard: Dashboard,
  system: SystemView,
  intelligence: IntelligenceView,
  memory: MemoryView,
  notes: PersonalNotesView,
  settings: SettingsView,
};

function viewFromHash(): ViewId {
  const raw = window.location.hash.replace(/^#\/?/, "").trim();
  return (raw in VIEWS ? raw : "dashboard") as ViewId;
}

export default function App() {
  const [view, setView] = useState<ViewId>(() => viewFromHash());
  const [theme, setTheme] = useState<ThemeMode>(
    () => (localStorage.getItem("cortex-theme-mode") as ThemeMode) || "auto",
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const resolved = theme === "auto" ? (mq.matches ? "dark" : "light") : theme;
      document.documentElement.setAttribute("data-theme", resolved);
      document.documentElement.setAttribute("data-theme-mode", theme);
    };
    apply();
    mq.addEventListener("change", apply);
    localStorage.setItem("cortex-theme-mode", theme);
    localStorage.setItem("cortex-theme", theme === "auto" ? (mq.matches ? "dark" : "light") : theme);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function navigate(next: ViewId) {
    setView(next);
    if (window.location.hash.replace(/^#\/?/, "") !== next) {
      window.history.replaceState(null, "", `#${next}`);
    }
  }

  const View = VIEWS[view];

  return (
    <div className={`app ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <NotifyToast />
      <Sidebar
        active={view}
        onNavigate={navigate}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "auto" ? "dark" : t === "dark" ? "light" : "auto"))}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((v) => !v)}
      />
      <div className="main-col">
        <StatusBar />
        <main className="main">
          <AnimatePresence mode="wait">
            <motion.div
              key={view}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.28, ease: "easeOut" }}
            >
              <View />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <FloatingAgent />
    </div>
  );
}
