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

const VIEWS: Record<ViewId, ComponentType> = {
  dashboard: Dashboard,
  system: SystemView,
  intelligence: IntelligenceView,
  memory: MemoryView,
  notes: PersonalNotesView,
  settings: SettingsView,
};

export default function App() {
  const [view, setView] = useState<ViewId>("dashboard");
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("cortex-theme") as "dark" | "light") || "light",
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("cortex-theme", theme);
  }, [theme]);

  const View = VIEWS[view];

  return (
    <div className={`app ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <NotifyToast />
      <Sidebar
        active={view}
        onNavigate={setView}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
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
