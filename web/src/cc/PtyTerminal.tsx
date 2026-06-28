// 真实交互终端：xterm.js ←→ 后端 PTY（/ws/term）。在这里跑的是 agent 的**原生 REPL**，
// 所以 claude 的 /model、/cost、/clear 这些原生斜杠命令会真实弹出、完整执行 —— 不是假壳。
//
// 独立成文件以便 React.lazy 懒加载：xterm（含 css）只有用户真正打开终端面板时才下载，
// 不再进首屏主 bundle（首屏体积显著下降）。
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

type Theme = "dark" | "light" | "auto";
const row = (g = 8): CSSProperties => ({ display: "flex", alignItems: "center", gap: g });
// 终端始终深底(和 --panel-3 恒深、<pre> 代码块一致)—— 深底读 ANSI 输出最稳,也消除两套终端色不一致。
// 配色对齐 theme.css 深色档:#0f141b = --panel-3,cursor 用酒红 accent-2。
const TERM_THEME = { background: "#0f141b", foreground: "#cdd6e2", cursor: "#d9536b", cursorAccent: "#0f141b", selectionBackground: "rgba(217,83,107,.32)", black: "#0f141b", brightBlack: "#5b6573" } as const;
const TERM_BG = "#0f141b";

// themeMode 仍接收(签名兼容),但终端恒深底,不随明暗切换 —— 故无"切主题卡住"问题。
export default function PtyTerminal({ agent, sessionKey, initialInput, cwd = "~", visible = true }: { agent: string; themeMode?: Theme; sessionKey: number; initialInput?: string; cwd?: string; visible?: boolean }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const fitRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState<"connecting" | "live" | "exited">("connecting");
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let booted = false;  // 首次收到输出后,把 initialInput 作为任务发进去(只发一次)
    const term = new XTerm({
      fontFamily: "'IBM Plex Mono','SFMono-Regular',monospace",
      fontSize: 12.5, lineHeight: 1.32, cursorBlink: true, scrollback: 5000,
      allowProposedApi: true,
      theme: { ...TERM_THEME },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host);
    const doFit = () => { try { fit.fit(); } catch { /* noop */ } };
    fitRef.current = doFit;
    setTimeout(doFit, 0);

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/ws/term`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      setStatus("live");
      ws.send(JSON.stringify({ type: "start", agent, cwd, cols: term.cols, rows: term.rows }));
      term.focus();
    };
    ws.onmessage = (e) => {
      if (typeof e.data === "string") {
        try {
          const o = JSON.parse(e.data);
          if (o.type === "exit") { setStatus("exited"); term.write("\r\n\x1b[2m─ 会话已结束 ─\x1b[0m\r\n"); }
          else if (o.type === "error") term.write(`\r\n\x1b[31m${o.msg}\x1b[0m\r\n`);
        } catch { /* ignore */ }
      } else {
        term.write(new Uint8Array(e.data as ArrayBuffer));
        // agent 的交互界面就绪(首次输出)后,把初始任务敲进去 —— 像在真终端里打字回车。
        if (!booted && initialInput && initialInput.trim()) {
          booted = true;
          setTimeout(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "input", data: initialInput.trim() + "\r" })); }, 350);
        }
      }
    };
    ws.onclose = () => setStatus((s) => (s === "exited" ? s : "exited"));
    ws.onerror = () => setStatus("exited");
    const onData = term.onData((d) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "input", data: d })); });
    const ro = new ResizeObserver(() => {
      doFit();
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    });
    ro.observe(host);

    return () => { onData.dispose(); ro.disconnect(); try { ws.close(); } catch { /* noop */ } term.dispose(); };
    // sessionKey 变化 = 用户点了「重启会话」，强制重建终端
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, sessionKey]);

  // 标签切换:面板从 display:none 重新显示时,xterm 量到的尺寸是 0,需要重新 fit。
  useEffect(() => { if (visible) setTimeout(() => fitRef.current?.(), 30); }, [visible]);

  return (
    <div style={{ position: "relative", height: "100%", minHeight: 0, background: TERM_BG }}>
      <div ref={hostRef} style={{ height: "100%", padding: "8px 4px 8px 12px" }} />
      <span style={{ position: "absolute", top: 9, right: 13, ...row(5), font: "600 9px 'IBM Plex Mono',monospace", color: status === "live" ? "var(--good)" : status === "connecting" ? "var(--warn)" : "var(--text-mute)", pointerEvents: "none" }}>
        <b style={{ width: 6, height: 6, borderRadius: "50%", background: status === "live" ? "var(--good)" : status === "connecting" ? "var(--warn)" : "var(--text-mute)", display: "inline-block", boxShadow: status === "live" ? "0 0 6px var(--good)" : "none", animation: status === "live" ? "cxBreathe 2.5s ease infinite" : "none" }} />
        {status === "live" ? "PTY 在线" : status === "connecting" ? "连接中…" : "已结束"}
      </span>
    </div>
  );
}
