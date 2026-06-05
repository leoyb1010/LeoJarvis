import { useEffect, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";

// 统一的悬浮详情卡片：扁平、克制、点击遮罩或 ESC 关闭。
// 资讯 / GitHub / 通知 / 服务等所有"点击查看详情"都复用它。
export function Modal({
  open,
  onClose,
  title,
  kicker,
  children,
  footer,
  width = 560,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  kicker?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          onClick={onClose}
        >
          <motion.div
            className="modal-card"
            style={{ maxWidth: width }}
            initial={{ opacity: 0, y: 18, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.985 }}
            transition={{ duration: 0.2, ease: [0.22, 0.61, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="modal-head">
              <div>
                {kicker ? <div className="modal-kicker">{kicker}</div> : null}
                {title ? <h3 className="modal-title">{title}</h3> : null}
              </div>
              <button className="modal-close" onClick={onClose} aria-label="关闭">✕</button>
            </div>
            <div className="modal-body">{children}</div>
            {footer ? <div className="modal-foot">{footer}</div> : null}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
