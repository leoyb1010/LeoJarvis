import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { connectNotify } from "../api";

type Toast = { id: string; source?: string; title: string; take: string };

export function NotifyToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const ws = connectNotify((m) => {
      const t: Toast = { id: `${Date.now()}-${Math.random()}`, source: m.source, title: m.title, take: m.take };
      setToasts((items) => [t, ...items].slice(0, 4));
      setTimeout(() => setToasts((items) => items.filter((x) => x.id !== t.id)), 9000);
    });
    return () => ws.close();
  }, []);

  return (
    <div className="toasts" aria-live="polite">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div key={t.id} className="toast"
            initial={{ opacity: 0, x: 60, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 60, scale: 0.9 }}
            transition={{ ease: "easeOut" }}>
            <div className="t-src">{t.source || "通知"}</div>
            <b>{t.title}</b>
            <div>{t.take}</div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
