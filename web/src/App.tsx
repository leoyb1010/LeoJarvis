import { useEffect, useState, type ComponentType } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar, type ViewId } from "./components/Sidebar";
import { NotifyToast } from "./components/NotifyToast";
import { Agent } from "./components/Agent";
import { Dashboard } from "./components/Dashboard";
import { SystemView } from "./components/views/SystemView";
import { ServicesView } from "./components/views/ServicesView";
import { AgentsView } from "./components/views/AgentsView";
import { JournalView } from "./components/views/JournalView";
import { Briefing } from "./components/Briefing";
import { MemoryView } from "./components/MemoryView";

const VIEWS: Record<ViewId, ComponentType> = {
  chat: Agent,
  dashboard: Dashboard,
  system: SystemView,
  services: ServicesView,
  agents: AgentsView,
  memory: MemoryView,
  journal: JournalView,
  feeds: Briefing,
};

export default function App() {
  const [view, setView] = useState<ViewId>("dashboard");
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("cortex-theme") as "dark" | "light") || "dark",
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("cortex-theme", theme);
  }, [theme]);

  const View = VIEWS[view];

  return (
    <div className="app">
      <NotifyToast />
      <Sidebar
        active={view}
        onNavigate={setView}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      />
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
  );
}
