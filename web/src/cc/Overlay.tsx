// 统一弹出层(Phase 0)。一套 Drawer/Modal/Sheet,全部 portal 到 document.body —— 逃出任何
// 父容器的 overflow:hidden(根治右下气泡被裁切),并用统一 z-index 分层(根治抽屉叠抽屉重叠)。
//
// 设计:
//   <Drawer>  右侧主抽屉(情报流/记事/收件箱详情)。z=DRAWER。
//   <Sheet>   叠在主抽屉之上的次级抽屉(从抽屉里点开的详情)—— 更窄、z 更高、左侧留更多边距错开,
//             不再和主抽屉完全重叠。
//   <Modal>   居中卡(对话/确认类)。z=MODAL。
//   <Popover> 锚定某个元素的小气泡(邮件应用列表),也 portal 出去不被裁。z=MODAL。
// 都带:backdrop 点击关 / Esc 关 / × 按钮 / 入场动画(theme.css,尊重 reduced-motion)。

import { useEffect, type ReactNode, type CSSProperties } from "react";
import { createPortal } from "react-dom";

// 统一 z-index 分层,取代散落的 20/30/40/45/50/60/90。
export const Z = { drawer: 1000, sheet: 1100, modal: 1200, toast: 1300 } as const;

function useEsc(onClose: () => void) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
}

const titleBar = (title: ReactNode, onClose: () => void, eyebrow?: string): ReactNode => (
  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "15px 18px", borderBottom: "1px solid var(--border-soft)", flex: "none" }}>
    {eyebrow && <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>{eyebrow}</span>}
    <span style={{ font: "600 14px 'Space Grotesk',sans-serif", color: "var(--text)", flex: 1, minWidth: 0 }}>{title}</span>
    <button onClick={onClose} aria-label="关闭" style={{ border: 0, background: "transparent", cursor: "pointer", color: "var(--text-mute)", font: "600 18px 'Space Grotesk'", lineHeight: 1, flex: "none" }}>×</button>
  </div>
);

type DrawerProps = {
  open: boolean; onClose: () => void; title?: ReactNode; eyebrow?: string;
  children: ReactNode; footer?: ReactNode; width?: number; level?: "drawer" | "sheet";
};

/** 右侧抽屉。level="sheet" 时更窄、z 更高、左留边距(叠在主抽屉上不重叠)。 */
export function Drawer({ open, onClose, title, eyebrow, children, footer, width, level = "drawer" }: DrawerProps) {
  useEsc(onClose);
  if (!open) return null;
  const isSheet = level === "sheet";
  const z = isSheet ? Z.sheet : Z.drawer;
  const w = width ?? (isSheet ? 460 : 540);
  return createPortal(
    <div className="cx-ov-backdrop" onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: z, background: isSheet ? "rgba(4,6,9,.35)" : "rgba(4,6,9,.5)", backdropFilter: "blur(3px)", display: "flex", justifyContent: "flex-end" }}>
      <div className="cx-ov-drawer" onClick={(e) => e.stopPropagation()}
        style={{ width: `min(${w}px, ${isSheet ? 88 : 94}vw)`, height: "100%", background: "var(--panel)", borderLeft: "1px solid var(--border)", boxShadow: "var(--shadow)", display: "grid", gridTemplateRows: footer ? "auto minmax(0,1fr) auto" : "auto minmax(0,1fr)", minHeight: 0 }}>
        {title !== undefined ? titleBar(title, onClose, eyebrow) : null}
        <div style={{ overflowY: "auto", minHeight: 0 }}>{children}</div>
        {footer ? <div style={{ borderTop: "1px solid var(--border-soft)", padding: "10px 16px", flex: "none" }}>{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}

type ModalProps = { open: boolean; onClose: () => void; title?: ReactNode; eyebrow?: string; children: ReactNode; width?: number; maxHeight?: number };

/** 居中弹卡。 */
export function Modal({ open, onClose, title, eyebrow, children, width = 560, maxHeight }: ModalProps) {
  useEsc(onClose);
  if (!open) return null;
  return createPortal(
    <div className="cx-ov-backdrop" onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: Z.modal, background: "rgba(0,0,0,.42)", backdropFilter: "blur(2px)", display: "grid", placeItems: "center", padding: 24 }}>
      <div className="cx-ov-modal" onClick={(e) => e.stopPropagation()}
        style={{ width: `min(${width}px, 94vw)`, maxHeight: maxHeight ? `min(${maxHeight}px, 88vh)` : "88vh", background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 14, boxShadow: "var(--shadow)", display: "grid", gridTemplateRows: title !== undefined ? "auto minmax(0,1fr)" : "minmax(0,1fr)", minHeight: 0, overflow: "hidden" }}>
        {title !== undefined ? titleBar(title, onClose, eyebrow) : null}
        <div style={{ overflowY: "auto", minHeight: 0 }}>{children}</div>
      </div>
    </div>,
    document.body,
  );
}

type PopoverProps = { open: boolean; onClose: () => void; anchor: DOMRect | null; children: ReactNode; width?: number };

/** 锚定气泡:portal 到 body,定位在 anchor 元素下方(不被父 overflow 裁切)。 */
export function Popover({ open, onClose, anchor, children, width = 280 }: PopoverProps) {
  useEsc(onClose);
  if (!open || !anchor) return null;
  // 右对齐 anchor;若靠近右边缘则贴右。
  const left = Math.max(8, Math.min(anchor.right - width, window.innerWidth - width - 8));
  const top = Math.min(anchor.bottom + 6, window.innerHeight - 80);
  const style: CSSProperties = {
    position: "fixed", left, top, width, zIndex: Z.modal, background: "var(--panel)",
    border: "1px solid var(--accent)", borderRadius: 12, boxShadow: "var(--shadow)",
    padding: 8, maxHeight: 320, overflowY: "auto",
  };
  return createPortal(
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: Z.modal - 1, background: "transparent" }} />
      <div className="cx-pop-in" style={style} onClick={(e) => e.stopPropagation()}>{children}</div>
    </>,
    document.body,
  );
}
