import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import {
  getCliAgents, getCliCommands, getCliSessions, runCliAgent, stopCliSession, clearFinishedSessions, openApp, fmtAgo,
  type CliCommand,
  getVitals, getServices, getSystemOverview, getBriefing, getNotes, getNotifications,
  agentChat, approveAction, getIntelligence, getBriefingItem,
  getAmapConfig, getAmapWeather, getSettings, patchSettings,
  getNote, createNote, updateNote, deleteNote, importNoteUrl, importNoteAttachment, attachmentUrl, getHoroscope,
  getNotebooks, getNotebookWorkspace, addNotebookText, notebookChat, notebookStudio,
  type NbSource, type NbCitation, type StudioTpl, type NotebookMeta,
  getDevices, deleteDevice, type FleetDevice,
  type CliAgent, type CliSession, type ExternalAgent, type Vitals, type Service, type SystemOverview,
  type Briefing, type BriefItem, type PersonalNote, type NotifApp, type ChatMsg, type ChatStep, type PendingAction, type ChatReply,
  type Intelligence, type IntelRepo, type IntelSource, type IntelTarget, type BriefDetailItem,
  type AmapConfig, type AmapWeather, type Settings as SettingsData, type Horoscope,
} from "./live";

// Cortex · 指挥台 — 深/浅双主题 + 酒红强调色。颜色一律走 theme.css 的 CSS 变量。
const TAG: Record<string, [string, string]> = {
  claude: ["CC", "#d9536b"], codex: ["CX", "#36d39a"], cursor: ["CU", "#4da3ff"],
  grok: ["GK", "#b69cff"], gemini: ["GM", "#ffb454"], opencode: ["OC", "#9aa6b2"],
  hermes: ["HM", "#ff8f5a"], openclaw: ["OW", "#5ad1c0"],
};
const A = (f: string) => `/cc/${f}`;

type Page = "cockpit" | "agents" | "intel" | "notes" | "devices" | "settings";
type Theme = "dark" | "light";

const panel: CSSProperties = { background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 15, padding: 16 };
const sub: CSSProperties = { background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 13 };
const lbl: CSSProperties = { font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".18em", color: "var(--text-mute)" };
const mono = (s = 10, c = "var(--text-mute)"): CSSProperties => ({ font: `500 ${s}px 'IBM Plex Mono',monospace`, color: c });
const row = (g = 8): CSSProperties => ({ display: "flex", alignItems: "center", gap: g });
const flex1: CSSProperties = { flex: 1 };

// 极轻的 live 波形（P5：细线、低幅、慢相位，仅作氛围，不刺眼）。
function useWave(id: string, freq: number) {
  useEffect(() => {
    let phase = 1.3;
    let raf = 0;
    const run = () => {
      raf = requestAnimationFrame(run);
      const c = document.getElementById(id) as HTMLCanvasElement | null;
      if (!c || !c.offsetParent) return;
      const ctx = c.getContext("2d");
      if (!ctx) return;
      const w = (c.width = c.clientWidth);
      const h = (c.height = c.clientHeight);
      ctx.clearRect(0, 0, w, h);
      phase += 0.022;
      const accent = (getComputedStyle(document.documentElement).getPropertyValue("--accent") || "#c23b54").trim();
      const draw = (alpha: number, lw: number) => {
        ctx.globalAlpha = alpha; ctx.lineWidth = lw; ctx.strokeStyle = accent; ctx.beginPath();
        for (let x = 0; x <= w; x += 2) {
          const env = 0.4 + 0.6 * Math.sin((x / w) * Math.PI);
          const y = h / 2 + Math.sin((x / w) * Math.PI * freq + phase) * (h * 0.2) * env;
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      };
      draw(0.12, 0.7); draw(0.7, 1.1); ctx.globalAlpha = 1;
    };
    run();
    return () => cancelAnimationFrame(raf);
  }, [id, freq]);
}

// Gmail 图标（P8：后端不返回 gmail 图标 → 用品牌 SVG 兜底）。
// 仅 Gmail 的 M 标志（不含外框）—— 外框由 AppIcon 的统一 tile 提供，保证和其它图标同款边缘。
function GmailMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" style={{ display: "block" }}>
      <path fill="#4285F4" d="M6 38V14l6 4v20z" /><path fill="#34A853" d="M42 38V14l-6 4v20z" />
      <path fill="#FBBC05" d="M6 14l18 13L42 14v-2a4 4 0 0 0-6.4-3.2L24 17 12.4 8.8A4 4 0 0 0 6 12z" />
      <path fill="#C5221F" d="M6 14v-2a4 4 0 0 1 6.4-3.2L24 17 6 14z" /><path fill="#C5221F" d="M42 14v-2a4 4 0 0 0-6.4-3.2L24 17 42 14z" />
    </svg>
  );
}

const PAGES: Page[] = ["cockpit", "agents", "intel", "notes", "devices", "settings"];
const pageFromHash = (): Page => { try { const h = location.hash.replace(/^#\/?/, "") as Page; return PAGES.includes(h) ? h : "cockpit"; } catch { return "cockpit"; } };

export default function CommandCenter() {
  const [page, _setPage] = useState<Page>(pageFromHash);
  // 浏览器历史路由：切页 push 一条历史，后退键在页面间回退（不再直接退出网页）。
  const setPage = (p: Page) => { try { if (pageFromHash() !== p) history.pushState({ page: p }, "", "#" + p); } catch { /* ignore */ } _setPage(p); };
  useEffect(() => {
    try { history.replaceState({ page: pageFromHash() }, "", "#" + pageFromHash()); } catch { /* ignore */ }
    const onPop = () => _setPage(pageFromHash());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const [now, setNow] = useState(new Date());
  const [scan, setScan] = useState(true);
  const [notesOpenId, setNotesOpenId] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(() => {
    try { return localStorage.getItem("cx-theme") === "light" ? "light" : "dark"; } catch { return "dark"; }
  });
  const [vitals, setVitals] = useState<Vitals>({ health: null, cpu: null, online: 0, total: 0 });

  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem("cx-theme", theme); } catch { /* ignore */ } }, [theme]);

  useEffect(() => {
    let live = true;
    const clock = setInterval(() => setNow(new Date()), 1000);
    const pull = () => getVitals().then((v) => { if (live) setVitals(v); }).catch(() => {});
    pull();
    const t = setInterval(pull, 10000);
    return () => { live = false; clearInterval(clock); clearInterval(t); };
  }, []);

  const pad = (n: number) => String(n).padStart(2, "0");
  const clock = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  const META: Record<Page, [string, string]> = {
    cockpit: ["全景驾驶舱", "COCKPIT"], agents: ["智能体编排", "AGENTS"],
    intel: ["情报中心", "INTELLIGENCE"], notes: ["个人记事", "NOTES"], devices: ["设备舰队", "DEVICES"], settings: ["设置台", "SETTINGS"],
  };
  const nav = (p: Page) => ({ fg: page === p ? "var(--accent)" : "var(--text-mute)", bg: page === p ? "var(--accent-soft)" : "transparent", bar: page === p ? "var(--accent)" : "transparent" });
  const navBtn = (p: Page, title: string, icon: ReactNode) => {
    const n = nav(p);
    return (
      <button className="cx-nav" onClick={() => setPage(p)} title={title} style={{ position: "relative", width: 46, height: 46, border: 0, cursor: "pointer", borderRadius: 13, background: n.bg, color: n.fg, display: "grid", placeContent: "center" }}>
        <span style={{ position: "absolute", left: -14, top: "50%", transform: "translateY(-50%)", width: 3, height: 20, borderRadius: 3, background: n.bar }} />
        {icon}
      </button>
    );
  };

  return (
    <div style={{ height: "100vh", display: "grid", gridTemplateColumns: "68px 1fr", background: "var(--bg)", color: "var(--text)", fontFamily: "'Space Grotesk','PingFang SC','Microsoft YaHei',sans-serif", overflow: "hidden" }}>
      <nav style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "14px 0", background: "var(--bg-2)", borderRight: "1px solid var(--border-soft)" }}>
        <img src={A("brand-mark.png")} alt="" style={{ width: 40, height: 40, borderRadius: 11, objectFit: "cover", boxShadow: "0 0 0 1px var(--border),0 0 18px var(--accent-soft)", marginBottom: 10 }} />
        {navBtn("cockpit", "驾驶舱", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="2" /><rect x="3" y="13.5" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" /></svg>)}
        {navBtn("agents", "智能体", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="5" r="2.4" /><circle cx="5.5" cy="18" r="2.4" /><circle cx="18.5" cy="18" r="2.4" /><path d="M12 7.4v3M11 12l-4 4M13 12l4 4" /></svg>)}
        {navBtn("intel", "情报", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12l6-6" /></svg>)}
        {navBtn("notes", "记事", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 3h11l3 3v15a0 0 0 0 1 0 0H5a0 0 0 0 1 0 0z" /><path d="M8.5 8.5h7M8.5 12h7M8.5 15.5h4" /></svg>)}
        {navBtn("devices", "设备", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M2 20h20M9 16v4M15 16v4" /></svg>)}
        <span style={flex1} />
        <button onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} title={theme === "dark" ? "切到浅色" : "切到深色"} className="cx-nav" style={{ width: 46, height: 46, border: 0, cursor: "pointer", borderRadius: 13, background: "transparent", color: "var(--text-mute)", display: "grid", placeContent: "center" }}>
          {theme === "dark"
            ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" /></svg>
            : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8z" /></svg>}
        </button>
        {navBtn("settings", "设置台", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></svg>)}
      </nav>

      <div style={{ display: "grid", gridTemplateRows: page === "cockpit" ? "1fr" : "58px 1fr", minWidth: 0, minHeight: 0 }}>
        {page !== "cockpit" && <header style={{ ...row(16), padding: "0 18px", borderBottom: "1px solid var(--border-soft)", background: "var(--bg-2)" }}>
          <div style={{ flex: "none", minWidth: 128 }}>
            <div style={{ font: "600 14.5px 'Space Grotesk',sans-serif", color: "var(--text)", lineHeight: 1.1 }}>{META[page][0]}</div>
            <div style={{ font: "500 9px 'IBM Plex Mono',monospace", letterSpacing: ".2em", color: "var(--text-mute)", marginTop: 2 }}>{META[page][1]}</div>
          </div>
          <span style={flex1} />
          <div style={{ flex: "none", ...row(9), font: "600 11px 'IBM Plex Mono',monospace" }}>
            <span style={{ ...row(5), background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 9px", color: "var(--text-dim)" }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 4s ease infinite" }} />健康 <b style={{ color: "var(--text)" }}>{vitals.health ?? "—"}</b></span>
            <span style={{ ...row(5), background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 9px", color: "var(--text-dim)" }}>CPU <b style={{ color: "var(--text)" }}>{vitals.cpu != null ? `${vitals.cpu}%` : "—"}</b></span>
            <span style={{ ...row(5), background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 9px", color: "var(--text-dim)" }}>服务 <b style={{ color: "var(--good)" }}>{vitals.online}/{vitals.total}</b></span>
            <span style={{ width: 1, height: 20, background: "var(--border)" }} />
            <span style={{ color: "var(--text)", letterSpacing: ".04em" }}>{clock}</span>
          </div>
        </header>}

        <div style={{ position: "relative", minHeight: 0, overflow: "hidden", backgroundImage: "linear-gradient(var(--border-soft) 1px,transparent 1px),linear-gradient(90deg,var(--border-soft) 1px,transparent 1px)", backgroundSize: "38px 38px", backgroundBlendMode: "overlay", opacity: 1 }}>
          {scan && <div className="cx-scanline" style={{ top: 0 }} />}
          {page === "cockpit" && <Cockpit goIntel={() => setPage("intel")} goNotes={(id) => { setNotesOpenId(id ?? null); setPage("notes"); }} goAgents={() => setPage("agents")} />}
          {page === "agents" && <Agents themeMode={theme} />}
          {page === "intel" && <Intel />}
          {page === "notes" && <Notes openId={notesOpenId} />}
          {page === "devices" && <Devices />}
          {page === "settings" && <Settings theme={theme} setTheme={setTheme} scan={scan} toggleScan={() => setScan((v) => !v)} />}
        </div>
      </div>
    </div>
  );
}

// ============ 共享：优先级 / 步骤 / 时间 ============
const PRI: Record<string, [string, string]> = { 高优先: ["#fff", "var(--bad)"], 中优先: ["#fff", "var(--accent)"], 简报: ["#fff", "var(--accent)"], 观察: ["var(--text-dim)", "var(--panel-2)"] };
const priStyle = (p?: string): [string, string] => PRI[p || "观察"] || PRI["观察"];
function stepTone(status?: string): { bar: string; label: string } {
  const s = (status || "").toLowerCase();
  if (s === "done" || s === "ok" || s === "success" || s === "完成") return { bar: "var(--good)", label: "完成" };
  if (s === "error" || s === "failed" || s === "失败") return { bar: "var(--bad)", label: "失败" };
  if (s.includes("pend") || s.includes("await") || s === "待确认") return { bar: "var(--warn)", label: "待确认" };
  return { bar: "var(--good)", label: status || "完成" };
}
function tsToTime(ts?: number): string {
  if (!ts) return "";
  const ms = ts > 1e12 ? ts : ts * 1000;
  const d = new Date(ms);
  if (isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

type Turn =
  | { kind: "user"; text: string }
  | { kind: "steps"; steps: ChatStep[] }
  | { kind: "assistant"; text: string }
  | { kind: "pending"; actions: PendingAction[] }
  | { kind: "system"; text: string };

// ============ 顶部对话坞（P10：对话置顶，输入后下拉对话框）============
function ChatDock() {
  const greeting = "我是你的中枢。问本机服务、系统状态、今日情报、天气路线，或让我跑个 agent、记一笔都行。";
  const [turns, setTurns] = useState<Turn[]>([{ kind: "assistant", text: greeting }]);
  const [history, setHistory] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [approving, setApproving] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const suggestions = ["本地服务都还活着吗", "北京今天天气怎么样", "今天有什么高优先情报", "让 codex 看看这个项目"];

  useEffect(() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight; }, [turns, busy, open]);

  function appendReply(res: ChatReply | null | undefined) {
    const add: Turn[] = [];
    if (res?.steps && res.steps.length) add.push({ kind: "steps", steps: res.steps });
    if (res?.reply) add.push({ kind: "assistant", text: String(res.reply) });
    if (res?.pending_actions && res.pending_actions.length) add.push({ kind: "pending", actions: res.pending_actions });
    if (add.length) setTurns((t) => [...t, ...add]);
    if (res?.reply) setHistory((h) => [...h, { role: "assistant", content: String(res.reply) }]);
  }
  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy) return;
    setDraft(""); setOpen(true);
    setTurns((t) => [...t, { kind: "user", text: msg }]);
    const next: ChatMsg[] = [...history, { role: "user", content: msg }];
    setHistory(next); setBusy(true);
    try { appendReply(await agentChat(next)); }
    catch { setTurns((t) => [...t, { kind: "system", text: "中枢暂时无法连接，请稍后再试。" }]); }
    finally { setBusy(false); }
  }
  async function approve(id: string) {
    if (approving) return;
    setApproving(id);
    try {
      const res = await approveAction(id, "approve");
      setTurns((t) => t.map((tn) => tn.kind === "pending" ? { ...tn, actions: tn.actions.filter((a) => a.id !== id) } : tn).filter((tn) => !(tn.kind === "pending" && tn.actions.length === 0)));
      appendReply(res);
      if (!res?.reply && !res?.steps?.length) setTurns((t) => [...t, { kind: "system", text: "已执行。" }]);
    } catch { setTurns((t) => [...t, { kind: "system", text: "执行失败，请重试。" }]); }
    finally { setApproving(null); }
  }

  return (
    <div style={{ position: "relative", zIndex: 40, width: "min(680px,100%)", margin: "0 auto" }}>
      <div style={{ ...row(11), background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 13, padding: "0 14px", height: 46, boxShadow: open ? "0 0 0 1px var(--accent-soft)" : "none" }}>
        <img src={A("brand-mark.png")} alt="" style={{ width: 26, height: 26, borderRadius: 7, objectFit: "cover", flex: "none" }} />
        <span style={{ font: "700 14px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>&gt;_</span>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onFocus={() => setOpen(true)} onKeyDown={(e) => { if (e.key === "Enter") send(draft); }} placeholder="问 Cortex 一句… (天气 / 情报 / 跑个 agent / 记一笔)" style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "var(--text)", font: "500 13.5px 'Space Grotesk',sans-serif" }} />
        {busy && <span style={mono(10, "var(--text-mute)")}>思考中…</span>}
        <button onClick={() => send(draft)} disabled={busy} style={{ border: 0, cursor: busy ? "default" : "pointer", background: "var(--accent)", color: "#fff", font: "600 11px 'Space Grotesk'", padding: "7px 14px", borderRadius: 8, opacity: busy ? 0.6 : 1 }}>发送</button>
        {open && <button onClick={() => setOpen(false)} title="收起" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", width: 30, height: 30, borderRadius: 8, display: "grid", placeContent: "center" }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 15l6-6 6 6" /></svg></button>}
      </div>

      {open && (
        <div style={{ position: "absolute", left: 0, right: 0, top: 54, background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 14, boxShadow: "var(--shadow)", display: "grid", gridTemplateRows: "minmax(0,1fr) auto", maxHeight: "min(56vh,520px)", overflow: "hidden", animation: "cxRise .2s ease both" }}>
          <div ref={scrollRef} style={{ overflowY: "auto", minHeight: 0, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 11 }}>
            {turns.map((tn, i) => {
              if (tn.kind === "user") return <div key={i} style={{ alignSelf: "flex-end", maxWidth: "78%", background: "var(--accent)", color: "#fff", font: "500 13.5px 'Space Grotesk',sans-serif", padding: "10px 14px", borderRadius: 13, borderBottomRightRadius: 4, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{tn.text}</div>;
              if (tn.kind === "steps") return (
                <div key={i} style={{ alignSelf: "flex-start", display: "grid", gap: 6, width: "90%" }}>
                  {tn.steps.map((st, j) => { const tone = stepTone(st.status); return (
                    <div key={j} style={{ ...row(9), background: "var(--panel-2)", border: "1px solid var(--border)", borderLeft: `3px solid ${tone.bar}`, borderRadius: 9, padding: "8px 11px" }}><code style={{ font: "600 11.5px 'IBM Plex Mono',monospace", color: tone.bar }}>{st.tool}</code><span style={flex1} /><span style={mono(10)}>{tone.label}</span></div>
                  ); })}
                </div>
              );
              if (tn.kind === "assistant") return <div key={i} style={{ alignSelf: "flex-start", maxWidth: "90%", background: "var(--panel-2)", border: "1px solid var(--border)", color: "var(--text-dim)", font: "400 13.5px/1.62 'Space Grotesk',sans-serif", padding: "12px 15px", borderRadius: 13, borderBottomLeftRadius: 4, whiteSpace: "pre-wrap" }}>{tn.text}</div>;
              if (tn.kind === "system") return <div key={i} style={{ alignSelf: "center", ...mono(10.5, "var(--bad)") }}>{tn.text}</div>;
              return (
                <div key={i} style={{ alignSelf: "flex-start", display: "grid", gap: 6, maxWidth: "90%" }}>
                  {tn.actions.map((act) => (
                    <div key={act.id} style={{ ...row(9), background: "rgba(255,180,84,.08)", border: "1px solid rgba(255,180,84,.3)", borderRadius: 11, padding: "10px 13px" }}><span style={{ font: "600 10.5px 'IBM Plex Mono',monospace", color: "var(--warn)", whiteSpace: "nowrap" }}>⚠ 待确认</span><code style={{ font: "500 11.5px 'IBM Plex Mono',monospace", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{act.reason || act.tool || act.id}</code><button onClick={() => approve(act.id)} disabled={approving === act.id} style={{ border: 0, cursor: "pointer", background: "var(--warn)", color: "#1a0f08", font: "600 10.5px 'Space Grotesk'", padding: "5px 11px", borderRadius: 6, whiteSpace: "nowrap", opacity: approving === act.id ? 0.6 : 1 }}>{approving === act.id ? "执行中" : "确认"}</button></div>
                  ))}
                </div>
              );
            })}
            {busy && <div style={{ alignSelf: "flex-start", ...mono(10.5, "var(--text-mute)") }}>中枢思考中…</div>}
          </div>
          <div style={{ padding: "10px 14px 12px", borderTop: "1px solid var(--border-soft)", display: "flex", flexWrap: "wrap", gap: 7 }}>
            {suggestions.map((sug) => (<button key={sug} onClick={() => send(sug)} disabled={busy} className="cx-chip" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", font: "500 11.5px 'Space Grotesk',sans-serif", padding: "6px 11px", borderRadius: 999, opacity: busy ? 0.5 : 1 }}>{sug}</button>))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============ 高德小地图（Q1 控件+定位 / Q7 主题联动）============
function AmapMini() {
  const [cfg, setCfg] = useState<AmapConfig | null>(null);
  const [wx, setWx] = useState<AmapWeather | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [failed, setFailed] = useState(false);
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<{ setMapStyle?: (s: string) => void } | null>(null);

  // R2: 彩色地图（不再用灰白 dark 样式）。浅色用标准彩色，深色用蓝调彩色（无权限会自动回退标准彩色）。
  const styleFor = () => (document.documentElement.dataset.theme === "light" ? "amap://styles/normal" : "amap://styles/darkblue");

  useEffect(() => {
    getAmapConfig().then((c) => { setCfg(c); if (c.configured && c.home_city) getAmapWeather(c.home_city).then(setWx).catch(() => {}); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!cfg?.configured || !cfg.center || collapsed) return;
    const center = cfg.center.split(",").map(Number);
    let cancelled = false;
    const w = window as unknown as { AMap?: any; _AMapSecurityConfig?: unknown };
    const build = () => {
      if (cancelled || mapRef.current || !w.AMap || !elRef.current) return;
      try {
        const map = new w.AMap.Map(elRef.current, { center, zoom: 11, viewMode: "2D", mapStyle: styleFor() });
        mapRef.current = map;
        w.AMap.plugin(["AMap.ToolBar", "AMap.Scale", "AMap.Geolocation"], () => {
          try {
            map.addControl(new w.AMap.ToolBar({ position: { top: "10px", right: "10px" } }));
            map.addControl(new w.AMap.Scale());
            const geo = new w.AMap.Geolocation({ position: "RB", offset: [12, 26], showButton: true, enableHighAccuracy: true, zoomToAccuracy: true });
            map.addControl(geo);
            // R2: 加载即真实定位到当前位置并居中（不止一个静态中心点）。
            geo.getCurrentPosition((status: string, result: { position?: unknown }) => {
              if (status === "complete" && result?.position) { try { map.setCenter(result.position); map.setZoom(13); } catch { /* ignore */ } }
            });
          } catch { /* 控件失败不致命 */ }
        });
      } catch { setFailed(true); }
    };
    const timer = setTimeout(() => { if (!mapRef.current) setFailed(true); }, 4000);
    if (w.AMap) { build(); clearTimeout(timer); }
    else {
      w._AMapSecurityConfig = { securityJsCode: "" };
      let s = document.getElementById("amap-js") as HTMLScriptElement | null;
      if (s) { s.addEventListener("load", build); }
      else {
        s = document.createElement("script"); s.id = "amap-js"; s.async = true;
        s.src = `https://webapi.amap.com/maps?v=2.0&key=${cfg.js_key}&plugin=AMap.ToolBar,AMap.Scale,AMap.Geolocation`;
        s.onload = build; s.onerror = () => setFailed(true);
        document.body.appendChild(s);
      }
    }
    const obs = new MutationObserver(() => { if (mapRef.current?.setMapStyle) { try { mapRef.current.setMapStyle(styleFor()); } catch { /* ignore */ } } });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { cancelled = true; clearTimeout(timer); obs.disconnect(); };
  }, [cfg, collapsed]);

  if (cfg && !cfg.configured) return null;
  const wxChip = wx?.ok ? `${wx.weather} ${wx.temperature}°C` : "";
  return (
    <div style={{ ...panel, padding: 0, overflow: "hidden", minHeight: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr)" }}>
      <div style={{ ...row(8), padding: "11px 13px" }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.9"><path d="M12 21s-7-6.5-7-11a7 7 0 0 1 14 0c0 4.5-7 11-7 11z" /><circle cx="12" cy="10" r="2.4" /></svg>
        <span style={lbl}>高德地图 · {cfg?.home_city || "—"}</span>
        <span style={flex1} />
        {wxChip && <span style={{ ...mono(10, "var(--text-dim)"), background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 999, padding: "2px 8px" }}>{wxChip}</span>}
        <button onClick={() => setCollapsed((v) => !v)} title={collapsed ? "展开" : "收起"} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", width: 24, height: 24, borderRadius: 7, display: "grid", placeContent: "center" }}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d={collapsed ? "M6 9l6 6 6-6" : "M6 15l6-6 6 6"} /></svg>
        </button>
      </div>
      {!collapsed && (
        <div style={{ background: "var(--panel-2)", position: "relative", minHeight: 150 }}>
          {!failed && <div ref={elRef} style={{ position: "absolute", inset: 0 }} />}
          {failed && cfg?.center && <img alt="地图" src={`https://restapi.amap.com/v3/staticmap?location=${cfg.center}&zoom=11&size=360*200&scale=2&markers=mid,,A:${cfg.center}&key=${cfg.js_key}`} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />}
          {!cfg && <div style={{ position: "absolute", inset: 0, display: "grid", placeContent: "center", ...mono(10.5) }}>加载地图…</div>}
        </div>
      )}
    </div>
  );
}

// 天气文字 → emoji
function wxEmoji(t?: string): string {
  const s = t || "";
  if (s.includes("雷")) return "⛈"; if (s.includes("雪")) return "❄️"; if (s.includes("雨")) return "🌧";
  if (s.includes("雾") || s.includes("霾")) return "🌫"; if (s.includes("阴")) return "☁️";
  if (s.includes("多云")) return "⛅"; if (s.includes("晴")) return "☀️"; return "🌤";
}

// ============ 今日台：时间 + 天气 + 星座并入一行（R7）============
const _SIGNS = ["天秤", "双鱼", "双子"];
function HoroscopeLine() {
  const [data, setData] = useState<Record<string, Horoscope>>({});
  useEffect(() => {
    let live = true;
    _SIGNS.forEach((s) => getHoroscope(s).then((d) => { if (live && d?.ok) setData((p) => ({ ...p, [s]: d })); }).catch(() => {}));
    return () => { live = false; };
  }, []);
  return (
    <div style={{ ...row(10), flexWrap: "wrap" }}>
      {_SIGNS.map((s) => { const h = data[s]; const sc = typeof h?.score === "number" ? h.score : null; const tone = sc == null ? "var(--text-mute)" : sc >= 75 ? "var(--good)" : sc >= 45 ? "var(--warn)" : "var(--bad)"; return (
        <span key={s} title={h?.advice || ""} className="cx-link" style={{ ...row(4), font: "500 11px 'Space Grotesk',sans-serif", color: "var(--text-dim)", cursor: "default" }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: tone, display: "inline-block", boxShadow: `0 0 5px ${tone}` }} />{s} <b style={{ color: "var(--text)" }}>{sc ?? "—"}</b></span>
      ); })}
    </div>
  );
}
function TodayCompact({ wx }: { wx: AmapWeather | null }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  const pad = (n: number) => String(n).padStart(2, "0");
  const week = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][now.getDay()];
  const greet = now.getHours() < 6 ? "凌晨好" : now.getHours() < 12 ? "早上好" : now.getHours() < 14 ? "中午好" : now.getHours() < 18 ? "下午好" : "晚上好";
  return (
    <div style={{ ...panel, position: "relative", overflow: "hidden", display: "grid", gap: 9 }}>
      <div style={{ position: "absolute", right: -34, top: -34, width: 130, height: 130, borderRadius: "50%", background: "radial-gradient(circle,var(--accent-soft),transparent 70%)", pointerEvents: "none" }} />
      <div style={{ ...row(8) }}>
        <span style={{ font: "700 30px 'Space Grotesk',sans-serif", color: "var(--text)", lineHeight: 1 }}>{pad(now.getHours())}:{pad(now.getMinutes())}<span style={{ font: "600 14px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>:{pad(now.getSeconds())}</span></span>
        <span style={flex1} />
        <span style={{ ...row(6) }}><span style={{ fontSize: 26, lineHeight: 1 }}>{wxEmoji(wx?.weather)}</span><b style={{ font: "700 18px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{wx?.ok ? `${wx.temperature}°` : "—"}</b></span>
      </div>
      <div style={{ ...mono(10.5, "var(--text-dim)") }}>{now.getFullYear()}年{now.getMonth() + 1}月{now.getDate()}日 · {week} · {greet}{wx?.ok ? ` · ${wx.city} ${wx.weather}` : ""}</div>
      <HoroscopeLine />
    </div>
  );
}

// ============ 中间大区域：实时情报扫描 feed（R3/R4：点击→详情抽屉）============
function IntelFeed({ onOpen, goIntel }: { onOpen: (id: string) => void; goIntel: () => void }) {
  const [brief, setBrief] = useState<Briefing | null>(null);
  const [scanning, setScanning] = useState(false);
  useEffect(() => {
    let live = true;
    const load = (flash: boolean) => { if (flash) setScanning(true); getBriefing().then((d) => { if (live) setBrief(d); }).catch(() => {}).finally(() => { if (live && flash) setTimeout(() => setScanning(false), 1400); }); };
    load(false);
    const t = setInterval(() => load(true), 60000);  // 每分钟扫描一次最新
    return () => { live = false; clearInterval(t); };
  }, []);
  const items = (Array.isArray(brief?.items) ? brief!.items! : []).filter((it) => it.kind !== "github_repo" && it.kind !== "repo").sort((a, b) => ((b.ts as number) || 0) - ((a.ts as number) || 0));
  const total = brief?.counts?.total ?? items.length;
  return (
    <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, overflow: "hidden", position: "relative" }}>
      <div style={{ ...row(10), padding: "14px 18px 12px", borderBottom: "1px solid var(--border-soft)" }}>
        <span style={{ position: "relative", width: 28, height: 28, flex: "none" }}>
          <svg width="28" height="28" viewBox="0 0 28 28" style={{ opacity: 0.5 }}><circle cx="14" cy="14" r="12" fill="none" stroke="var(--border)" /><circle cx="14" cy="14" r="7" fill="none" stroke="var(--border)" /><circle cx="14" cy="14" r="1.6" fill="var(--accent)" /></svg>
          <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "conic-gradient(from 0deg,var(--accent-soft) 0deg,transparent 60deg)", animation: "cxRadar 2.6s linear infinite" }} />
        </span>
        <div><div style={{ font: "600 13.5px 'Space Grotesk',sans-serif", color: "var(--accent)" }}>实时情报扫描</div><div style={mono(9.5)}>按发布时间滚动 · 新闻 / 科技 / 财经 / 军事</div></div>
        <span style={flex1} />
        {scanning && <span style={{ ...row(5), ...mono(10, "var(--good)") }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxPulse 1s ease infinite" }} />扫描中</span>}
        <button onClick={goIntel} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", ...mono(10, "var(--accent)") }}>全部 {total} →</button>
      </div>
      <div style={{ overflowY: "auto", minHeight: 0, position: "relative" }}>
        {scanning && <div className="cx-scanline" style={{ top: 0 }} />}
        <div style={{ padding: "4px 14px 14px" }}>
          {brief === null && <div style={{ ...mono(11), padding: "30px 0", textAlign: "center" }}>正在接入实时情报流…</div>}
          {brief !== null && items.length === 0 && <div style={{ ...mono(11), padding: "30px 0", textAlign: "center" }}>暂无情报，去情报页手动扫描</div>}
          {items.slice(0, 40).map((it, i) => { const [pf, pb] = priStyle(it.priority); const time = tsToTime(it.ts); const id = it.event_id; const cat = (it as { category?: string }).category; return (
            <button key={id || i} onClick={() => { if (id) onOpen(id); }} className="cx-feed" style={{ animationDelay: `${Math.min(i, 12) * 0.025}s`, textAlign: "left", width: "100%", border: 0, cursor: id ? "pointer" : "default", background: "transparent", padding: "11px 8px", borderBottom: "1px solid var(--border-soft)", display: "grid", gap: 5, borderRadius: 9 }}>
              <div style={row(7)}><span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: pf, background: pb, borderRadius: 999, padding: "2px 7px" }}>{it.priority || "观察"}</span><span style={mono(9.5)}>{it.source || ""}{time ? ` · ${time}` : ""}</span>{cat && <span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "var(--text-mute)", background: "var(--panel-2)", borderRadius: 999, padding: "2px 7px" }}>{cat}</span>}<span style={flex1} /><span style={{ ...mono(9, "var(--accent)"), opacity: 0 }} className="cx-feed-cta">详情 →</span></div>
              <b style={{ font: "600 13.5px/1.42 'Space Grotesk',sans-serif", color: "var(--text)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{it.title}</b>
              {it.take && <p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{it.take}</p>}
            </button>
          ); })}
        </div>
      </div>
    </div>
  );
}

// ============ 右上：记事卡（点击吊起记事面板，R3）============
function NotesWidget({ notes, onSaved, onExpand }: { notes: PersonalNote[]; onSaved: () => void; onExpand: (id?: string) => void }) {
  const [bubble, setBubble] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  async function quickSave() {
    const t = text.trim(); if (!t || saving) return;
    setSaving(true);
    try { await createNote({ content: t, source: "manual" }); setText(""); setBubble(false); onSaved(); }
    catch { /* ignore */ } finally { setSaving(false); }
  }
  return (
    <div style={{ ...panel, position: "relative", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0 }}>
      <div style={{ ...row(8), marginBottom: 11 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.9"><path d="M5 3h11l3 3v15H5z" /><path d="M8.5 9h7M8.5 12.5h7M8.5 16h4" /></svg>
        <span style={lbl}>个人记事</span><span style={flex1} />
        <button onClick={() => setBubble((v) => !v)} className="cx-chip" style={{ ...row(5), border: "1px solid var(--border)", background: bubble ? "var(--accent-soft)" : "var(--panel-2)", color: "var(--accent)", cursor: "pointer", borderRadius: 8, padding: "4px 9px", font: "600 11px 'Space Grotesk'" }}>＋ 记一笔</button>
        <button onClick={() => onExpand()} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", ...mono(10, "var(--text-mute)") }}>展开 →</button>
      </div>
      {bubble && (
        <div style={{ position: "absolute", top: 38, right: 12, left: 12, zIndex: 20, background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 12, boxShadow: "var(--shadow)", padding: 12, animation: "cxRise .16s ease both" }}>
          <textarea autoFocus value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") quickSave(); }} placeholder="随手记一笔…（⌘↵ 保存）" style={{ width: "100%", height: 72, resize: "none", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: "9px 11px", color: "var(--text)", font: "400 12.5px/1.5 'Space Grotesk',sans-serif", outline: "none" }} />
          <div style={{ ...row(8), marginTop: 8 }}><span style={flex1} /><button onClick={() => { setBubble(false); setText(""); }} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "5px 12px", font: "600 11px 'Space Grotesk'" }}>取消</button><button onClick={quickSave} disabled={saving || !text.trim()} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "5px 14px", font: "600 11px 'Space Grotesk'", opacity: saving || !text.trim() ? 0.5 : 1 }}>{saving ? "保存中" : "保存"}</button></div>
        </div>
      )}
      <div style={{ overflowY: "auto", minHeight: 0, display: "grid", gap: 7, alignContent: "start", paddingRight: 2 }}>
        {notes.length === 0 && <div style={{ ...mono(10.5), padding: "6px 2px" }}>暂无记事，点「记一笔」或「展开」</div>}
        {notes.slice(0, 5).map((nt, i) => { const when = nt.updated_ts ? `${fmtAgo(nt.updated_ts)}前` : ""; return (
          <button key={nt.id || i} onClick={() => onExpand(nt.id)} className="cx-row" style={{ textAlign: "left", ...sub, padding: "9px 11px", cursor: "pointer", display: "grid", gap: 3, minWidth: 0 }}>
            <div style={{ ...row(6) }}>{nt.pinned && <span style={{ fontSize: 10 }}>📌</span>}<b style={{ font: "600 11.5px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{nt.title || "未命名"}</b><span style={mono(8.5)}>{when}</span></div>
            <p style={{ margin: 0, font: "400 10px/1.45 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{nt.excerpt || nt.content || ""}</p>
          </button>
        ); })}
      </div>
    </div>
  );
}

// 记事浮层：点击右上角记事吊起的「页面」——浏览/快编/删除，不离开首页（R3）
function NotesOverlay({ openId, onClose, goFull }: { openId?: string; onClose: () => void; goFull: (id?: string) => void }) {
  const [notes, setNotes] = useState<PersonalNote[]>([]);
  const [sel, setSel] = useState<string | null>(openId ?? null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const load = () => getNotes().then((d) => setNotes(Array.isArray(d?.notes) ? d.notes : [])).catch(() => {});
  useEffect(() => { load(); }, []);
  useEffect(() => { if (sel) getNote(sel).then((r) => { if (r?.note) { setTitle(r.note.title || ""); setContent(r.note.content || ""); setDirty(false); } }).catch(() => {}); }, [sel]);
  useEffect(() => { const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, [onClose]);
  function newNote() { setSel(null); setTitle(""); setContent(""); setDirty(true); }
  async function save() {
    if (saving || (!title.trim() && !content.trim())) return;
    setSaving(true);
    try { if (sel) await updateNote(sel, { title, content }); else { const r = await createNote({ title, content }); if (r?.note?.id) setSel(r.note.id); } setDirty(false); load(); }
    catch { /* ignore */ } finally { setSaving(false); }
  }
  async function del() { if (!sel || !window.confirm("删除这条记事？")) return; try { await deleteNote(sel); newNote(); load(); } catch { /* ignore */ } }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(4,6,9,.5)", backdropFilter: "blur(2px)", display: "flex", justifyContent: "flex-end", animation: "cxFade .18s ease both" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: "min(720px,94vw)", height: "100%", background: "var(--panel)", borderLeft: "1px solid var(--border)", boxShadow: "-24px 0 60px rgba(0,0,0,.4)", display: "grid", gridTemplateColumns: "240px minmax(0,1fr)", animation: "cxSlideIn .26s cubic-bezier(.22,.61,.36,1) both" }}>
        <div style={{ borderRight: "1px solid var(--border-soft)", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0 }}>
          <div style={{ ...row(8), padding: "14px 14px 10px" }}><span style={lbl}>记事</span><span style={flex1} /><button onClick={newNote} title="新建" style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", width: 24, height: 24, borderRadius: 7, font: "700 15px 'Space Grotesk'", lineHeight: 0 }}>＋</button></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "0 10px 12px", display: "grid", gap: 6, alignContent: "start" }}>
            {notes.length === 0 && <div style={{ ...mono(10.5), padding: "16px 0", textAlign: "center" }}>无记事</div>}
            {notes.map((nt) => { const on = sel === nt.id; return (
              <button key={nt.id} onClick={() => setSel(nt.id!)} className="cx-row" style={{ textAlign: "left", background: on ? "var(--accent-soft)" : "var(--panel-2)", border: `1px solid ${on ? "var(--accent)" : "var(--border-soft)"}`, borderRadius: 9, padding: "8px 10px", cursor: "pointer", display: "grid", gap: 3 }}>
                <b style={{ font: "600 11.5px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{nt.title || "未命名"}</b>
                <span style={mono(8.5)}>{nt.updated_ts ? `${fmtAgo(nt.updated_ts)}前` : ""}</span>
              </button>
            ); })}
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", minHeight: 0 }}>
          <div style={{ ...row(10), padding: "12px 16px", borderBottom: "1px solid var(--border-soft)" }}>
            <input value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true); }} placeholder="标题…" style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "var(--text)", font: "600 16px 'Space Grotesk',sans-serif" }} />
            {sel && <button onClick={del} title="删除" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--bad)", cursor: "pointer", borderRadius: 7, width: 28, height: 28, display: "grid", placeContent: "center" }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" /></svg></button>}
            <button onClick={save} disabled={saving} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "6px 14px", font: "600 12px 'Space Grotesk'", opacity: saving ? 0.6 : 1 }}>{saving ? "保存中" : "保存"}</button>
            <button onClick={onClose} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", borderRadius: 7, width: 28, height: 28, display: "grid", placeContent: "center" }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
          </div>
          <textarea value={content} onChange={(e) => { setContent(e.target.value); setDirty(true); }} placeholder="正文支持 Markdown…" style={{ margin: 0, resize: "none", background: "transparent", border: 0, outline: "none", padding: "14px 18px", color: "var(--text)", font: "400 13.5px/1.75 'Space Grotesk',sans-serif" }} />
          <div style={{ ...row(8), padding: "9px 16px", borderTop: "1px solid var(--border-soft)" }}>{dirty && <span style={mono(10, "var(--warn)")}>未保存</span>}<span style={flex1} /><button onClick={() => goFull(sel ?? undefined)} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", ...mono(10.5, "var(--accent)") }}>完整记事本 →</button></div>
        </div>
      </div>
    </div>
  );
}

// ============ 左下：本机服务（P7：紧凑、状态点、不被边缘吃）============
function ServicesCard({ services }: { services: Service[] }) {
  const online = services.filter((s) => s.health === "online");
  const rest = services.filter((s) => s.health !== "online");
  const shown = [...online, ...rest].map((s) => ({
    name: s.display && !/^(Python|Electron|node)$/i.test(s.display) ? s.display : s.name,
    port: s.port ?? 0, online: s.health === "online",
    dot: s.health === "online" ? "var(--good)" : s.health === "offline" ? "var(--bad)" : "var(--text-mute)",
  }));
  return (
    <div style={{ ...panel, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0 }}>
      <div style={{ ...row(8), marginBottom: 11 }}><span style={lbl}>本机服务</span><span style={flex1} /><span style={mono(10, "var(--text-dim)")}>{online.length}/{services.length}</span></div>
      <div style={{ display: "grid", gap: 6, overflowY: "auto", minHeight: 0, alignContent: "start", paddingRight: 2 }}>
        {shown.length === 0 && <div style={{ ...mono(10), padding: "4px 2px" }}>检测本机服务中…</div>}
        {shown.map((s, i) => (
          <div key={`${s.name}-${i}`} style={{ ...row(9), background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: 9, padding: "8px 11px", minWidth: 0 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: s.dot, flex: "none", boxShadow: s.online ? `0 0 6px ${s.dot}` : "none" }} />
            <span style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
            <span style={{ ...mono(9.5), flex: "none" }}>{s.port ? `:${s.port}` : ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============ 应用与邮件（R8：不暗化 + 可点击看详情/打开）============
function AppIcon({ a, size = 46 }: { a: NotifApp; size?: number }) {
  const local: Record<string, string> = { mail: "mail.png", wechat: "wechat.png", telegram: "telegram.png", popo: "popo.png", mailmaster: "mailmaster.png" };
  const src = a.icon || (local[a.id] ? A(local[a.id]) : "");
  // 统一 tile：所有图标（含 Gmail）满铺 + 同一描边。描边用半透明灰，在「白底 Gmail」和
  // 「彩色满铺图标」上都同样轻——不会出现彩色图标看不见描边、白底 Gmail 却像加了边框的割裂感。
  const frame: CSSProperties = { width: size, height: size, borderRadius: Math.round(size * 0.26), boxShadow: "0 0 0 1px rgba(140,146,158,.16), 0 1px 3px rgba(0,0,0,.22)", display: "grid", placeContent: "center", overflow: "hidden", boxSizing: "border-box", flex: "none", background: "var(--panel-2)" };
  if (a.id === "gmail" && !a.icon) return <span style={{ ...frame, background: "#fff" }}><GmailMark size={Math.round(size * 0.82)} /></span>;
  if (src) return <span style={frame}><img src={src} alt={a.name || a.id} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} /></span>;
  return <span style={{ ...frame, font: `700 ${Math.round(size * 0.4)}px 'Space Grotesk'`, color: "var(--text-dim)" }}>{(a.name || a.id).slice(0, 1).toUpperCase()}</span>;
}
function AppsWidget({ apps }: { apps: NotifApp[] }) {
  const local: Record<string, string> = { mail: "mail.png", wechat: "wechat.png", telegram: "telegram.png", popo: "popo.png", mailmaster: "mailmaster.png" };
  const list = apps.filter((a) => a.id === "gmail" || local[a.id] || a.icon);
  const [sel, setSel] = useState<NotifApp | null>(null);
  const [opening, setOpening] = useState(false);
  async function open(a: NotifApp) { setOpening(true); try { await openApp(a.name || a.id); } catch { /* ignore */ } finally { setOpening(false); setSel(null); } }
  return (
    <div style={{ ...panel, position: "relative" }}>
      <div style={{ ...row(8), marginBottom: 13 }}><span style={lbl}>应用与邮件</span><span style={flex1} /><span style={mono(9)}>点击查看 · 仅读计数</span></div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {list.length === 0 && <span style={mono(10.5)}>暂无应用通知</span>}
        {list.map((a) => {
          const count = typeof a.count === "number" ? a.count : 0;
          const on = sel?.id === a.id;
          return (
            <button key={a.id} title={a.name || a.id} onClick={() => setSel(on ? null : a)} className="cx-app" style={{ position: "relative", border: 0, background: "transparent", cursor: "pointer", padding: 0, borderRadius: 10, outline: on ? "2px solid var(--accent)" : "none", outlineOffset: 2 }}>
              <AppIcon a={a} />
              {count > 0 && <span style={{ position: "absolute", top: -5, right: -5, minWidth: 17, height: 17, padding: "0 4px", borderRadius: 9, background: "var(--bad)", color: "#fff", font: "700 9px 'IBM Plex Mono'", display: "grid", placeContent: "center", border: "2px solid var(--panel)" }}>{count}</span>}
            </button>
          );
        })}
      </div>
      {sel && (
        <div style={{ position: "absolute", left: 14, right: 14, bottom: 12, zIndex: 20, background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 12, boxShadow: "var(--shadow)", padding: 12, display: "grid", gap: 10, animation: "cxRise .16s ease both" }}>
          <div style={{ ...row(10) }}>
            <AppIcon a={sel} size={34} />
            <div style={{ flex: 1, minWidth: 0 }}><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{sel.name || sel.id}</div><div style={mono(9.5)}>{typeof sel.count === "number" && sel.count > 0 ? `${sel.count} 条未读` : "无未读"}</div></div>
            <button onClick={() => setSel(null)} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", width: 26, height: 26, borderRadius: 7, display: "grid", placeContent: "center" }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
          </div>
          <button onClick={() => open(sel)} disabled={opening} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 9, padding: "8px 0", font: "600 12px 'Space Grotesk'", opacity: opening ? 0.6 : 1 }}>{opening ? "打开中…" : "打开应用"}</button>
        </div>
      )}
    </div>
  );
}

// ============ COCKPIT（P10 新布局）============
// 中枢核心：旋转轨道 + 品牌核 + 均衡器（design 稿装饰中枢）
// 中枢核心（动态头像）—— 缩小 ~30%，点击即呼出 Jarvis 对话气泡。
function CoreOrb({ online, onClick }: { online: boolean; onClick?: () => void }) {
  return (
    <button onClick={onClick} title="点击和 Jarvis 对话" className="cx-orb" style={{ border: 0, background: "transparent", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 5, animation: "cxRise .6s ease both", padding: 0, justifySelf: "center" }}>
      <div style={{ position: "relative", width: 124, height: 124, display: "grid", placeItems: "center", flex: "none" }}>
        <div style={{ position: "absolute", width: 124, height: 124, borderRadius: "50%", border: "1px solid rgba(194,59,84,.18)", animation: "cxSpin 26s linear infinite" }} />
        <div style={{ position: "absolute", width: 124, height: 124, animation: "cxSpin 26s linear infinite" }}><span style={{ position: "absolute", top: -3, left: "50%", width: 5, height: 5, borderRadius: "50%", background: "var(--accent)", transform: "translateX(-50%)", boxShadow: "0 0 8px var(--accent)" }} /></div>
        <div style={{ position: "absolute", width: 100, height: 100, borderRadius: "50%", border: "1px dashed rgba(194,59,84,.28)", animation: "cxSpinR 18s linear infinite" }} />
        <div style={{ position: "absolute", width: 80, height: 80, borderRadius: "50%", border: "1px solid rgba(194,59,84,.4)", animation: "cxPing 3.4s ease-out infinite" }} />
        <div className="cx-orb-core" style={{ position: "relative", width: 64, height: 64, borderRadius: "50%", display: "grid", placeItems: "center", background: "radial-gradient(circle at 38% 32%,#1d232e,#0f141b)", boxShadow: "inset 0 0 14px rgba(0,0,0,.6),0 0 0 1px var(--border)", animation: "cxCorePulse 4.5s ease infinite", overflow: "hidden" }}>
          <img src={A("brand-mark.png")} alt="" style={{ width: 64, height: 64, objectFit: "cover", opacity: .92 }} />
          <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 50% 120%,rgba(194,59,84,.4),transparent 60%)" }} />
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, flex: "none" }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 2.5, height: 13 }}>
          {Array.from({ length: 9 }).map((_, i) => <i key={i} style={{ width: 2.5, height: "100%", background: "linear-gradient(#d9536b,var(--accent))", borderRadius: 2, display: "block", transformOrigin: "bottom", animation: `cxBar ${(0.7 + (i % 4) * 0.22).toFixed(2)}s ease-in-out infinite ${(i * 0.09).toFixed(2)}s` }} />)}
        </div>
        <span style={{ ...row(4), font: "600 9px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--accent)", whiteSpace: "nowrap" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: online ? "var(--good)" : "var(--text-mute)", display: "inline-block", boxShadow: online ? "0 0 5px var(--good)" : "none" }} />点我 · 和 Jarvis 对话</span>
      </div>
    </button>
  );
}

// 中枢对话气泡 —— 点击动态头像呼出的浮层对话框（不再占首页固定版面）。
function JarvisChat({ onClose }: { onClose: () => void }) {
  const greeting = "我是你的中枢 Jarvis。问本机状态、今日情报、天气路线，或让我跑个 agent、记一笔。";
  const tips = ["磁盘为什么满了", "今天高优先情报", "让 codex 看这个项目", "记一笔"];
  const [turns, setTurns] = useState<Turn[]>([{ kind: "assistant", text: greeting }]);
  const [history, setHistory] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [approving, setApproving] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight; }, [turns, busy]);
  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 80); const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  function appendReply(res: ChatReply | null | undefined) {
    const add: Turn[] = [];
    if (res?.steps && res.steps.length) add.push({ kind: "steps", steps: res.steps });
    if (res?.reply) add.push({ kind: "assistant", text: String(res.reply) });
    if (res?.pending_actions && res.pending_actions.length) add.push({ kind: "pending", actions: res.pending_actions });
    if (add.length) setTurns((t) => [...t, ...add]);
    if (res?.reply) setHistory((h) => [...h, { role: "assistant", content: String(res.reply) }]);
  }
  async function send(text: string) {
    const msg = text.trim(); if (!msg || busy) return;
    setDraft(""); setTurns((t) => [...t, { kind: "user", text: msg }]);
    const next: ChatMsg[] = [...history, { role: "user", content: msg }];
    setHistory(next); setBusy(true);
    try { appendReply(await agentChat(next)); }
    catch { setTurns((t) => [...t, { kind: "system", text: "中枢暂时无法连接，请稍后再试。" }]); }
    finally { setBusy(false); }
  }
  async function approve(id: string) {
    if (approving) return; setApproving(id);
    try {
      const res = await approveAction(id, "approve");
      setTurns((t) => t.map((tn) => tn.kind === "pending" ? { ...tn, actions: tn.actions.filter((a) => a.id !== id) } : tn).filter((tn) => !(tn.kind === "pending" && tn.actions.length === 0)));
      appendReply(res);
      if (!res?.reply && !res?.steps?.length) setTurns((t) => [...t, { kind: "system", text: "已执行。" }]);
    } catch { setTurns((t) => [...t, { kind: "system", text: "执行失败，请重试。" }]); }
    finally { setApproving(null); }
  }
  const single = turns.length <= 1;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(0,0,0,.34)", display: "grid", placeItems: "start center", paddingTop: 84, animation: "cxFade .16s ease both" }}>
      <div onClick={(e) => e.stopPropagation()} className="cx-pop-in" style={{ width: "min(580px,92vw)", height: "min(64vh,560px)", ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden", position: "relative", background: "linear-gradient(180deg,var(--panel),var(--panel-2))", boxShadow: "var(--shadow)" }}>
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}><span style={{ position: "absolute", top: 0, left: 0, width: "32%", height: "100%", background: "linear-gradient(90deg,transparent,rgba(194,59,84,.06),transparent)", animation: "cxSheen 7s ease-in-out infinite" }} /></div>
      <div style={{ ...row(9), padding: "12px 14px 11px", borderBottom: "1px solid var(--border-soft)", position: "relative" }}>
        <img src={A("brand-mark.png")} alt="" style={{ width: 28, height: 28, borderRadius: 8, objectFit: "cover", flex: "none" }} />
        <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "700 13.5px 'Space Grotesk',sans-serif", color: "var(--text)" }}>和 Jarvis 对话</div><div style={{ ...row(4), ...mono(8.5, "var(--good)") }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 2.6s ease infinite" }} />中枢在线 · 工具总线就绪</div></div>
        <span style={{ font: "700 15px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>&gt;_</span>
        <button onClick={onClose} title="关闭(Esc)" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", width: 28, height: 28, borderRadius: 8, display: "grid", placeContent: "center", flex: "none" }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
      </div>
      <div ref={scrollRef} style={{ overflowY: "auto", minHeight: 0, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 9, position: "relative" }}>
        {turns.map((tn, i) => {
          if (tn.kind === "user") return <div key={i} style={{ alignSelf: "flex-end", maxWidth: "86%", background: "var(--accent)", color: "#fff", font: "500 12.5px 'Space Grotesk',sans-serif", padding: "8px 12px", borderRadius: 12, borderBottomRightRadius: 4, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{tn.text}</div>;
          if (tn.kind === "steps") return <div key={i} style={{ alignSelf: "flex-start", display: "grid", gap: 5, width: "94%" }}>{tn.steps.map((st, j) => { const tone = stepTone(st.status); return <div key={j} style={{ ...row(8), background: "var(--panel)", border: "1px solid var(--border)", borderLeft: `3px solid ${tone.bar}`, borderRadius: 8, padding: "6px 9px" }}><code style={{ font: "600 10.5px 'IBM Plex Mono',monospace", color: tone.bar }}>{st.tool}</code><span style={flex1} /><span style={mono(9)}>{tone.label}</span></div>; })}</div>;
          if (tn.kind === "assistant") return <div key={i} style={{ alignSelf: "flex-start", maxWidth: "92%", background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text-dim)", font: "400 12.5px/1.6 'Space Grotesk',sans-serif", padding: "9px 12px", borderRadius: 12, borderBottomLeftRadius: 4, whiteSpace: "pre-wrap" }}>{tn.text}</div>;
          if (tn.kind === "system") return <div key={i} style={{ alignSelf: "center", ...mono(10, "var(--bad)") }}>{tn.text}</div>;
          return <div key={i} style={{ alignSelf: "flex-start", display: "grid", gap: 5, maxWidth: "94%" }}>{tn.actions.map((act) => <div key={act.id} style={{ ...row(8), background: "rgba(255,180,84,.08)", border: "1px solid rgba(255,180,84,.3)", borderRadius: 10, padding: "8px 11px" }}><span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "var(--warn)", whiteSpace: "nowrap" }}>⚠ 待确认</span><code style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{act.reason || act.tool || act.id}</code><button onClick={() => approve(act.id)} disabled={approving === act.id} style={{ border: 0, cursor: "pointer", background: "var(--warn)", color: "#1a0f08", font: "600 10px 'Space Grotesk'", padding: "4px 10px", borderRadius: 6, whiteSpace: "nowrap", opacity: approving === act.id ? 0.6 : 1 }}>{approving === act.id ? "执行中" : "确认"}</button></div>)}</div>;
        })}
        {single && <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 2 }}>{tips.map((q) => <button key={q} onClick={() => send(q)} className="cx-chip" style={{ border: "1px solid var(--border)", background: "var(--panel)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 999, padding: "5px 10px", font: "500 10.5px 'Space Grotesk'" }}>{q}</button>)}</div>}
        {busy && <div style={{ alignSelf: "flex-start", ...mono(10, "var(--text-mute)") }}>中枢思考中…</div>}
      </div>
      <div style={{ ...row(8), padding: "10px 12px", borderTop: "1px solid var(--border-soft)", position: "relative" }}>
        <input ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(draft); }} placeholder="和 Jarvis 说点什么…" style={{ flex: 1, background: "var(--panel-3)", border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", color: "var(--text)", font: "500 12.5px 'Space Grotesk',sans-serif", outline: "none" }} />
        <button onClick={() => send(draft)} disabled={busy || !draft.trim()} style={{ border: 0, cursor: busy || !draft.trim() ? "default" : "pointer", background: "var(--accent)", color: "#fff", font: "600 12px 'Space Grotesk'", padding: "8px 15px", borderRadius: 9, flex: "none", opacity: busy || !draft.trim() ? 0.5 : 1 }}>发送</button>
      </div>
      </div>
    </div>
  );
}

// 中枢综述：整个系统的简报 —— 服务告警 / 资源 / 智能体 / 邮件 / 顶级情报，合成 4 条（不只是新闻）。E1①
type BriefLine = { idx: string; topic: string; detail: string; tone: string; id?: string };
function synthBrief(opts: { news: BriefItem[]; services: Service[]; svcTotal: number; svcOnline: number; health: number | null; ssd: number | null; ram: number | null; cpu: number | null; unread: number; running: number; sigCount: number }): BriefLine[] {
  const lines: Omit<BriefLine, "idx">[] = [];
  // ① 第一条永远是系统脉搏（这是「整个系统的简报」，不是新闻简报）。
  const offline = opts.services.filter((s) => s.health === "offline");
  if (offline.length) lines.push({ topic: "服务告警", detail: `${offline.map((s) => s.display || s.name).slice(0, 2).join("、")} 掉线，重启预案就绪，待你确认。`, tone: "#ff5d5d" });
  else if (opts.ssd != null && opts.ssd >= 85) lines.push({ topic: "磁盘吃紧", detail: `SSD 已用 ${opts.ssd}%，建议清理热点目录释放空间。`, tone: "#ffb454" });
  else if (opts.cpu != null && opts.cpu >= 85) lines.push({ topic: "CPU 高负载", detail: `当前负载 ${opts.cpu}%，留意占用最高的进程。`, tone: "#ffb454" });
  else lines.push({ topic: "系统平稳", detail: `${opts.svcOnline}/${opts.svcTotal} 服务在线，健康分 ${opts.health ?? "—"}，磁盘 ${opts.ssd ?? "—"}%，无告警。`, tone: "var(--good)" });
  // ② 智能体 / 未读 —— 系统侧动态
  if (opts.running > 0) lines.push({ topic: "智能体在跑", detail: `${opts.running} 个会话运行中，切换页面不影响后台执行。`, tone: "var(--accent)" });
  if (opts.unread > 0) lines.push({ topic: "未读消息", detail: `共 ${opts.unread} 条未读，可在右侧应用区直接打开处理。`, tone: "#ffb454" });
  // ③ 顶级情报，把简报填到 4 条
  const rank = (p?: string) => p === "高优先" ? 0 : p === "中优先" ? 1 : 2;
  const top = [...opts.news].sort((a, b) => (rank(a.priority) - rank(b.priority)) || (((b.score as number) || 0) - ((a.score as number) || 0)));
  for (const it of top) {
    if (lines.length >= 4) break;
    const title = String(it.title || "");
    lines.push({ topic: (title.split(/[，。：、!?！？\s]/)[0] || title).slice(0, 16), detail: String(it.take || (it as { why_important?: string }).why_important || title).slice(0, 80), tone: it.priority === "高优先" ? "#ff5d5d" : "var(--accent)", id: it.event_id });
  }
  return lines.slice(0, 4).map((l, i) => ({ idx: String(i + 1).padStart(2, "0"), ...l }));
}

// 今日日程：独立填写入口（时间+事项）→ 存为带「日程」标签的记事。E1⑥
function SchedulePanel({ todos, onSaved, onOpen }: { todos: PersonalNote[]; onSaved: () => void; onOpen: (id?: string) => void }) {
  const [open, setOpen] = useState(false);
  const [time, setTime] = useState("");
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  async function add() {
    const t = title.trim(); if (!t || saving) return;
    setSaving(true);
    try { await createNote({ title: (time.trim() ? time.trim() + " · " : "") + t, content: t, tags: ["日程"] }); setTime(""); setTitle(""); setOpen(false); onSaved(); }
    catch { /* ignore */ } finally { setSaving(false); }
  }
  return (
    <div style={{ ...panel, position: "relative", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, animation: "cxRise .78s ease both" }}>
      <div style={{ ...row(8), marginBottom: 11 }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>今日日程</span><span style={mono(9)}>{todos.length} 项</span><span style={flex1} /><button onClick={() => setOpen((v) => !v)} className="cx-chip" style={{ ...row(4), border: "1px solid var(--border)", background: open ? "var(--accent-soft)" : "var(--panel-2)", color: "var(--accent)", borderRadius: 8, padding: "3px 9px", font: "600 10.5px 'Space Grotesk'", cursor: "pointer", whiteSpace: "nowrap" }}>＋ 加日程</button></div>
      {open && (
        <div style={{ position: "absolute", top: 36, left: 12, right: 12, zIndex: 20, background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 12, boxShadow: "var(--shadow)", padding: 11, display: "grid", gap: 8, animation: "cxRise .16s ease both" }}>
          <div style={{ ...row(8) }}>
            <input value={time} onChange={(e) => setTime(e.target.value)} placeholder="10:00" style={{ width: 70, flex: "none", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 9px", color: "var(--text)", font: "500 12px 'IBM Plex Mono',monospace", outline: "none", textAlign: "center" }} />
            <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }} placeholder="事项，如 评估本地代理协议" style={{ flex: 1, minWidth: 0, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px", color: "var(--text)", font: "400 12.5px 'Space Grotesk',sans-serif", outline: "none" }} />
          </div>
          <div style={{ ...row(8) }}><span style={flex1} /><button onClick={() => { setOpen(false); setTime(""); setTitle(""); }} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "5px 12px", font: "600 11px 'Space Grotesk'" }}>取消</button><button onClick={add} disabled={saving || !title.trim()} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "5px 14px", font: "600 11px 'Space Grotesk'", opacity: saving || !title.trim() ? 0.5 : 1 }}>{saving ? "保存中" : "添加"}</button></div>
        </div>
      )}
      <div style={{ display: "grid", gap: 8, overflowY: "auto", minHeight: 0, alignContent: "start" }}>
        {todos.length === 0 && <div style={{ ...mono(10.5), padding: "6px 2px", lineHeight: 1.6 }}>暂无日程。点「＋ 加日程」填一条，或给记事打「待办」标签。</div>}
        {todos.slice(0, 6).map((n) => (
          <button key={n.id} onClick={() => onOpen(n.id)} className="cx-row" style={{ textAlign: "left", border: 0, background: "transparent", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, padding: "5px 6px", borderRadius: 8 }}><span style={{ width: 15, height: 15, borderRadius: 5, border: "1.5px solid var(--accent)", flex: "none" }} /><span style={{ font: "500 12px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.title || "未命名"}</span></button>
        ))}
      </div>
    </div>
  );
}

function Cockpit({ goIntel, goNotes, goAgents }: { goIntel: () => void; goNotes: (id?: string) => void; goAgents: () => void }) {
  const [overview, setOverview] = useState<SystemOverview | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [notes, setNotes] = useState<PersonalNote[]>([]);
  const [notifApps, setNotifApps] = useState<NotifApp[]>([]);
  const [wx, setWx] = useState<AmapWeather | null>(null);
  const [brief, setBrief] = useState<Briefing | null>(null);
  const [sessions, setSessions] = useState<CliSession[]>([]);
  const [external, setExternal] = useState<ExternalAgent[]>([]);
  const [horos, setHoros] = useState<Record<string, Horoscope>>({});
  const [now, setNow] = useState(new Date());
  const [leadIdx, setLeadIdx] = useState(0);  // 头条卡片在 Top3 重要消息间轮播
  const [chatOpen, setChatOpen] = useState(false);  // 点动态头像呼出 Jarvis 对话气泡
  const [detailId, setDetailId] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<{ open: boolean; id?: string }>({ open: false });

  const reloadNotes = () => { getNotes().then((d) => setNotes(Array.isArray(d?.notes) ? d.notes : [])).catch(() => {}); };
  useEffect(() => {
    let live = true;
    const clock = setInterval(() => setNow(new Date()), 1000);
    const pull = () => { getServices().then((d) => { if (live && Array.isArray(d)) setServices(d); }).catch(() => {}); getSystemOverview().then((d) => { if (live) setOverview(d); }).catch(() => {}); };
    pull(); const t = setInterval(pull, 10000);
    const pullBrief = () => getBriefing().then((d) => { if (live) setBrief(d); }).catch(() => {});
    pullBrief(); const tb = setInterval(pullBrief, 60000);
    const pullSess = () => getCliSessions().then((d) => { if (live) { setSessions(d.sessions || []); setExternal(d.external || []); } }).catch(() => {});
    pullSess(); const tsv = setInterval(pullSess, 4000);
    reloadNotes();
    getNotifications().then((d) => { if (live) setNotifApps(Array.isArray(d?.apps) ? d.apps : []); }).catch(() => {});
    const tn = setInterval(() => { getNotifications().then((d) => { if (live) setNotifApps(Array.isArray(d?.apps) ? d.apps : []); }).catch(() => {}); }, 30000);
    const loadWx = () => getAmapWeather("深圳").then((wd) => { if (live && wd?.ok) setWx(wd); }).catch(() => {});
    loadWx(); const tw = setInterval(loadWx, 600000);
    ["天秤", "双鱼", "双子"].forEach((s) => getHoroscope(s).then((d) => { if (live && d?.ok) setHoros((p) => ({ ...p, [s]: d })); }).catch(() => {}));
    return () => { live = false; clearInterval(clock); clearInterval(t); clearInterval(tb); clearInterval(tsv); clearInterval(tn); clearInterval(tw); };
  }, []);

  const pad = (n: number) => String(n).padStart(2, "0");
  const week = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][now.getDay()];
  const greet = now.getHours() < 6 ? "凌晨好" : now.getHours() < 12 ? "早上好" : now.getHours() < 14 ? "中午好" : now.getHours() < 18 ? "下午好" : "晚上好";
  const health = typeof overview?.score === "number" ? Math.round(overview.score) : null;
  const mod = (id: string) => overview?.modules?.find((m) => m.id === id);
  const pctOf = (id: string): number | null => { const v = mod(id)?.metrics?.used_pct; return typeof v === "number" ? Math.round(v) : null; };
  const ssdPct = pctOf("disk"); const ramPct = pctOf("memory"); const cpuPct = (() => { const v = mod("cpu")?.metrics?.load_pct; return typeof v === "number" ? Math.round(v) : null; })();
  const ringOffset = health != null ? +(100.5 * (1 - health / 100)).toFixed(1) : 100.5;
  const svcOnline = services.filter((s) => s.health === "online").length;

  const allItems = Array.isArray(brief?.items) ? brief!.items! : [];
  const news = allItems.filter((it) => it.kind !== "github_repo" && it.kind !== "repo");
  const newsByTime = [...news].sort((a, b) => ((b.ts as number) || 0) - ((a.ts as number) || 0));
  const totalUnread = notifApps.reduce((a, b) => a + (typeof b.count === "number" ? b.count : 0), 0);
  const signalCount = brief?.counts?.total ?? news.length;
  const runningNow = sessions.filter((s) => s.status === "running").length + external.length;  // 含常驻网关(Hermes/OpenClaw)
  const briefLines = synthBrief({ news, services, svcTotal: services.length, svcOnline, health, ssd: ssdPct, ram: ramPct, cpu: cpuPct, unread: totalUnread, running: runningNow, sigCount: signalCount });

  const PRI: Record<string, [string, string]> = { 高优先: ["#fff", "#ff5d5d"], 中优先: ["#fff", "var(--accent)"], 简报: ["#fff", "var(--accent)"], 观察: ["var(--text-dim)", "var(--panel-2)"] };
  const pstyle = (p?: string): [string, string] => PRI[p || "观察"] || PRI["观察"];
  const leads = [...news].sort((a, b) => { const r = (p?: string) => p === "高优先" ? 0 : p === "中优先" ? 1 : 2; return (r(a.priority) - r(b.priority)) || (((b.score as number) || 0) - ((a.score as number) || 0)); }).slice(0, 3);
  const leadCount = Math.max(1, leads.length);
  const lead = leads[leadIdx % leadCount];  // 进度条走完即切下一条
  const feed = newsByTime.slice(0, 20);  // E1③ 填满情报流（之前只 6 条留大片空白）
  const catColor: Record<string, string> = { AI科技: "#4da3ff", 财经: "#ffb454", 军事: "#ff5d5d", 科技: "#36d39a", 中文科技: "#b69cff", 开发: "#5ad1c0", 综合资讯: "#9aa4b2", X社媒: "#d9536b" };
  useEffect(() => { if (leadCount <= 1) return; const t = setInterval(() => setLeadIdx((i) => (i + 1) % leadCount), 6500); return () => clearInterval(t); }, [leadCount]);
  const running = sessions.filter((s) => s.status === "running");
  const tagOf = (a: string): [string, string] => TAG[a] || [a.slice(0, 2).toUpperCase(), "#9aa6b2"];
  const todoNotes = notes.filter((n) => Array.isArray(n.tags) && n.tags.some((t: string) => /待办|todo|日程/i.test(t)));

  return (
    <div className="cx-page" style={{ position: "relative", height: "100%", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", gap: 18, padding: "16px 20px", minHeight: 0 }}>
      <style>{"@keyframes cxSlideIn{from{transform:translateX(28px);opacity:.4}to{transform:translateX(0);opacity:1}}@keyframes cxFade{from{opacity:0}to{opacity:1}}"}</style>

      {/* ROW 1 — 中枢综述 / 核心 / 时间天气健康 */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 268px 240px", gap: 20, alignItems: "stretch" }}>
        <div style={{ animation: "cxRiseL .5s ease both", display: "flex", flexDirection: "column", justifyContent: "center", minWidth: 0 }}>
          <div style={{ ...row(9), marginBottom: 4 }}>
            <span style={{ font: "600 9px 'IBM Plex Mono',monospace", letterSpacing: ".24em", color: "var(--accent)" }}>中枢综述</span>
            <span style={{ font: "500 9px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--text-mute)" }}>{now.getFullYear()}.{pad(now.getMonth() + 1)}.{pad(now.getDate())}</span>
            <span style={{ ...row(5), font: "500 9px 'IBM Plex Mono',monospace", color: "var(--good)" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 2.6s ease infinite" }} />已综合 {signalCount} 信号 · {totalUnread} 未读 · {svcOnline} 服务</span>
          </div>
          <h1 style={{ margin: "0 0 3px", font: "600 21px/1.05 'Space Grotesk',sans-serif", letterSpacing: "-.02em", color: "var(--text)" }}>{greet}，Leo<span style={{ color: "var(--accent)", animation: "cxGlowText 4s ease infinite" }}>.</span></h1>
          <div style={{ display: "grid", gap: 0, maxWidth: 760 }}>
            {briefLines.length === 0 && <div style={{ ...mono(11), padding: "4px 0" }}>正在综合今日情报…</div>}
            {briefLines.map((b) => (
              <button key={b.idx} onClick={() => { if (b.id) setDetailId(b.id); }} className="cx-row" title={`${b.topic} — ${b.detail}`} style={{ textAlign: "left", border: 0, background: "transparent", cursor: b.id ? "pointer" : "default", display: "flex", alignItems: "center", gap: 10, padding: "1px 8px", borderRadius: 6 }}>
                <span style={{ font: "600 10.5px 'IBM Plex Mono',monospace", color: "var(--accent)", flex: "none", letterSpacing: ".04em" }}>{b.idx}</span>
                <span style={{ width: 1, height: 12, background: "var(--border)", flex: "none" }} />
                <span style={{ minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", lineHeight: 1.35 }}><b style={{ font: "600 11.5px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{b.topic}</b><span style={{ font: "400 11px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}> — {b.detail}</span></span>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: b.tone, flex: "none", boxShadow: `0 0 5px ${b.tone}` }} />
              </button>
            ))}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 5 }}>
            <button onClick={goIntel} className="cx-chip" style={{ border: 0, cursor: "pointer", background: "var(--accent)", color: "#fff", font: "600 12px 'Space Grotesk'", padding: "6px 13px", borderRadius: 8, boxShadow: "0 6px 18px rgba(194,59,84,.28)" }}>读完整简报 →</button>
            <button onClick={goAgents} className="cx-chip" style={{ border: "1px solid var(--border)", cursor: "pointer", background: "var(--panel)", color: "var(--text)", font: "600 12px 'Space Grotesk'", padding: "7px 14px", borderRadius: 8 }}>看智能体 →</button>
            <button onClick={() => goNotes()} className="cx-chip" style={{ border: "1px solid var(--border)", cursor: "pointer", background: "var(--panel)", color: "var(--text)", font: "600 12px 'Space Grotesk'", padding: "7px 14px", borderRadius: 8 }}>＋ 记一笔</button>
          </div>
          {/* 今日概览统计条已并入「综述」标注行 + 右栏 + 各面板，避免重复、压缩首屏高度 */}
        </div>
        <CoreOrb online={svcOnline > 0} onClick={() => setChatOpen(true)} />
        <div style={{ display: "grid", gap: 6, alignContent: "center", paddingRight: 18, animation: "cxRise .7s ease both" }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ font: "700 29px/1 'Space Grotesk',sans-serif", color: "var(--text)", letterSpacing: "-.01em" }}>{pad(now.getHours())}:{pad(now.getMinutes())}<span style={{ font: "600 13px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>:{pad(now.getSeconds())}</span></div>
            <div style={{ font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--text-mute)", marginTop: 2 }}>{now.getMonth() + 1}月{now.getDate()}日 · {week} · {greet}</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 7 }}>
            <span style={{ fontSize: 19, lineHeight: 1 }}>{wxEmoji(wx?.weather)}</span><span style={{ font: "700 16px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{wx?.ok ? `${wx.temperature}°` : "—"}</span><span style={{ font: "500 10.5px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>{wx?.city || "深圳"} · {wx?.weather || "—"}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 9 }}>
            {["天秤", "双鱼", "双子"].map((s) => { const h = horos[s]; const sc = typeof h?.score === "number" ? h.score : null; const tn = sc == null ? "var(--text-mute)" : sc >= 75 ? "var(--good)" : sc >= 45 ? "var(--warn)" : "var(--bad)"; return <span key={s} title={h?.advice || ""} style={{ ...row(4), font: "500 10px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: tn, display: "inline-block", boxShadow: `0 0 5px ${tn}` }} />{s} <b style={{ color: "var(--text)" }}>{sc ?? "—"}</b></span>; })}
          </div>
          <div style={{ height: 1, background: "var(--border-soft)", margin: "1px 0" }} />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8 }}>
            <div style={{ position: "relative", width: 34, height: 34, flex: "none" }}>
              <svg width="34" height="34" viewBox="0 0 34 34" style={{ transform: "rotate(-90deg)" }}><circle cx="17" cy="17" r="14" fill="none" stroke="var(--border)" strokeWidth="3.5" /><circle cx="17" cy="17" r="14" fill="none" stroke="var(--accent)" strokeWidth="3.5" strokeLinecap="round" strokeDasharray="87.96" strokeDashoffset={health != null ? +(87.96 * (1 - health / 100)).toFixed(1) : 87.96} style={{ filter: "drop-shadow(0 0 4px rgba(194,59,84,.6))", transition: "stroke-dashoffset .6s" }} /></svg>
              <div style={{ position: "absolute", inset: 0, display: "grid", placeContent: "center", font: "700 11px 'Space Grotesk'", color: "var(--text)" }}>{health ?? "—"}</div>
            </div>
            <div style={{ display: "grid", gap: 3, textAlign: "right" }}>
              <span style={{ font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>系统健康 · 平稳</span>
              <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--text-dim)" }}><span>CPU <b style={{ color: "var(--text)" }}>{cpuPct ?? "—"}%</b></span><span>RAM <b style={{ color: "var(--text)" }}>{ramPct ?? "—"}%</b></span><span>SSD <b style={{ color: "var(--warn)" }}>{ssdPct ?? "—"}%</b></span></div>
            </div>
          </div>
        </div>
      </div>

      {chatOpen && <JarvisChat onClose={() => setChatOpen(false)} />}

      {/* ROW 3 — 5 面板 bento */}
      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr 1fr", gridTemplateRows: "repeat(2,minmax(0,1fr))", gap: 14, minHeight: 0 }}>
        {/* 实时情报（span 2） */}
        <div style={{ gridRow: "span 2", ...panel, padding: 0, display: "grid", gridTemplateRows: "auto auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden", animation: "cxRise .6s ease both" }}>
          <div style={{ ...row(10), padding: "15px 18px 0" }}>
            <span style={{ position: "relative", width: 22, height: 22, flex: "none" }}><svg width="22" height="22" viewBox="0 0 22 22" style={{ opacity: .55 }}><circle cx="11" cy="11" r="9.5" fill="none" stroke="var(--border)" /><circle cx="11" cy="11" r="1.4" fill="var(--accent)" /></svg><span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "conic-gradient(from 0deg,rgba(194,59,84,.4),transparent 55%)", animation: "cxSpin 2.4s linear infinite" }} /></span>
            <div style={{ font: "600 13.5px 'Space Grotesk',sans-serif", color: "var(--text)" }}>实时情报</div>
            <span style={{ ...row(4), font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--good)" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxNew 1.4s ease infinite" }} />直播</span>
            <span style={flex1} />
            <button onClick={goIntel} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", font: "500 10px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>全部 {signalCount} →</button>
          </div>
          {lead ? (
            <button key={`lead-${leadIdx}`} onClick={() => { if (lead.event_id) setDetailId(lead.event_id); }} style={{ textAlign: "left", margin: "13px 16px 0", background: "linear-gradient(135deg,var(--panel-2),var(--panel))", border: "1px solid var(--border)", borderRadius: 13, padding: "14px 15px", position: "relative", overflow: "hidden", cursor: "pointer", animation: "cxFade .45s ease both" }} className="cx-lift">
              <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}><span style={{ position: "absolute", top: 0, left: 0, width: "36%", height: "100%", background: "linear-gradient(90deg,transparent,rgba(194,59,84,.06),transparent)", animation: "cxSheen 6.5s ease-in-out infinite" }} /></div>
              <div style={{ ...row(8), marginBottom: 8, position: "relative" }}><span style={{ font: "700 9px 'IBM Plex Mono',monospace", color: pstyle(lead.priority)[0], background: pstyle(lead.priority)[1], borderRadius: 999, padding: "3px 9px" }}>头条 · {lead.priority || "观察"}</span><span style={{ font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>{lead.source || ""} · {tsToTime(lead.ts)}</span><span style={flex1} />{typeof lead.score === "number" && <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>相关 {lead.score.toFixed(2)}</span>}</div>
              <b style={{ font: "600 16px/1.38 'Space Grotesk',sans-serif", color: "var(--text)", position: "relative", display: "block", overflow: "hidden", maxHeight: "2.76em" }}>{lead.title}</b>
              <p style={{ margin: "6px 0 10px", font: "400 12px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", position: "relative", display: "block", overflow: "hidden", maxHeight: "3em" }}>{lead.take || ""}</p>
              <div style={{ ...row(9), position: "relative" }}>
                <div style={{ flex: 1, height: 2, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}><i style={{ display: "block", height: "100%", background: "var(--accent)", animation: "cxProg 6.5s linear" }} /></div>
                <div style={{ ...row(5), flex: "none" }}>{leads.map((_, k) => <b key={k} onClick={(e) => { e.stopPropagation(); setLeadIdx(k); }} style={{ width: k === leadIdx % leadCount ? 16 : 6, height: 6, borderRadius: 999, background: k === leadIdx % leadCount ? "var(--accent)" : "var(--border)", display: "inline-block", transition: "all .3s", cursor: "pointer" }} />)}</div>
              </div>
            </button>
          ) : <div style={{ margin: "13px 16px 0", ...mono(11), padding: "10px 0", textAlign: "center" }}>暂无头条</div>}
          <div style={{ overflowY: "auto", minHeight: 0, padding: "11px 14px 8px", display: "flex", flexDirection: "column", gap: 8 }}>
            {feed.map((it, i) => { const [pf, pb] = pstyle(it.priority); const cat = (it as { category?: string }).category; const ac = (cat && catColor[cat]) || (it.priority === "高优先" ? "#ff5d5d" : "var(--accent)"); return (
              <button key={it.event_id || i} onClick={() => { if (it.event_id) setDetailId(it.event_id); }} className="cx-feed cx-lift" style={{ animationDelay: `${Math.min(i, 10) * 0.025}s`, flexShrink: 0, textAlign: "left", width: "100%", border: "1px solid var(--border-soft)", background: "var(--panel-2)", cursor: "pointer", display: "flex", flexDirection: "column", gap: 4, padding: "10px 13px 10px 15px", borderRadius: 12, position: "relative", overflow: "hidden" }}>
                <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: ac }} />
                <div style={{ ...row(7), flexWrap: "wrap" }}>
                  <span style={{ font: "600 8px 'IBM Plex Mono',monospace", color: pf, background: pb, borderRadius: 999, padding: "2px 7px" }}>{it.priority || "观察"}</span>
                  {cat && <span style={{ font: "600 8px 'IBM Plex Mono',monospace", color: ac, background: "var(--panel-3)", borderRadius: 999, padding: "2px 7px" }}>{cat}</span>}
                  <span style={{ font: "500 9px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>{it.source || ""} · {tsToTime(it.ts)}</span>
                  {i === 0 && <span style={{ font: "700 7.5px 'IBM Plex Mono',monospace", color: "var(--good)", background: "rgba(54,211,154,.14)", borderRadius: 999, padding: "1px 5px", animation: "cxNew 1.2s ease infinite" }}>刚到</span>}
                  <span style={flex1} />
                  {typeof it.score === "number" && <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>相关 {it.score.toFixed(0)}</span>}
                </div>
                <b style={{ display: "block", font: "600 13px/1.42 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", maxHeight: "2.84em", wordBreak: "break-word" }}>{it.title || "（无标题）"}</b>
                {it.take && <div style={{ font: "400 11px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.take}</div>}
              </button>
            ); })}
            {feed.length === 0 && <div style={{ ...mono(11), padding: "16px 0", textAlign: "center" }}>正在接入情报流…</div>}
          </div>
          <div style={{ ...row(8), padding: "10px 16px", borderTop: "1px solid var(--border-soft)" }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="var(--text-mute)"><path d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.3-1.8-1.3-1.8-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.7-1.6-2.7-.3-5.5-1.3-5.5-6 0-1.2.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2a11 11 0 0 1 6 0C17 4.6 18 4.9 18 4.9c.6 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.1 0 4.7-2.8 5.7-5.5 6 .4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .3z" /></svg>
            <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--text-mute)" }}>GITHUB 雷达</span><span style={flex1} />
            <button onClick={goIntel} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", font: "500 10px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>查看雷达 →</button>
          </div>
        </div>

        {/* 智能体 */}
        <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, overflow: "hidden", animation: "cxRise .66s ease both" }}>
          <div style={{ ...row(9), padding: "14px 16px 11px" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: runningNow ? "var(--good)" : "var(--text-mute)", boxShadow: runningNow ? "0 0 8px var(--good)" : "none", animation: runningNow ? "cxBreathe 2.4s ease infinite" : "none", flex: "none" }} />
            <div style={{ font: "600 12.5px 'Space Grotesk',sans-serif", color: "var(--text)" }}>智能体</div><span style={{ font: "500 10px 'IBM Plex Mono',monospace", color: "var(--text-dim)" }}>{runningNow} 运行中</span>
            <span title="实时状态(每 4 秒刷新)。agent 是独立后台进程，切换页面 / 离开首页都不会终止它的运行。" style={{ ...row(4), font: "500 8.5px 'IBM Plex Mono',monospace", color: "var(--text-mute)", cursor: "help" }}>· 后台持续</span>
            <span style={flex1} />
            <button onClick={goAgents} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", font: "500 11px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>编排 →</button>
          </div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "0 14px 12px", display: "grid", gap: 8, alignContent: "start" }}>
            {sessions.length === 0 && external.length === 0 && <div style={{ ...mono(10.5), padding: "10px 2px", lineHeight: 1.6 }}>暂无运行中的会话。去智能体页给 agent 派任务。</div>}
            {external.map((e) => { const [tg, fg] = tagOf(e.agent); return (
              <button key={`gw-${e.agent}`} onClick={goAgents} style={{ textAlign: "left", width: "100%", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 11, padding: "10px 11px", display: "grid", gap: 7, cursor: "pointer" }}>
                <div style={{ ...row(8) }}>
                  <span style={{ width: 24, height: 24, borderRadius: 7, background: "var(--panel-3)", border: "1px solid var(--border)", display: "grid", placeContent: "center", font: "700 9.5px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>
                  <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 11.5px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{e.display}</div><div style={{ font: "500 8.5px 'IBM Plex Mono',monospace", color: "var(--good)" }}>:{e.port} · 常驻网关</div></div>
                  <span style={{ ...row(4), font: "600 8.5px 'IBM Plex Mono',monospace", color: "var(--good)", flex: "none" }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", display: "inline-block", boxShadow: "0 0 6px var(--good)", animation: "cxBreathe 2.4s ease infinite" }} />常驻</span>
                </div>
              </button>
            ); })}
            {sessions.slice(0, 4).map((s) => { const [tg, fg] = tagOf(s.agent); const live = s.status === "running"; return (
              <div key={s.id} style={{ background: "var(--panel-2)", border: `1px solid ${live ? "var(--border)" : "var(--border-soft)"}`, borderRadius: 11, padding: "10px 11px", display: "grid", gap: 7 }}>
                <div style={{ ...row(8) }}>
                  <span style={{ width: 24, height: 24, borderRadius: 7, background: "var(--panel-3)", border: "1px solid var(--border)", display: "grid", placeContent: "center", font: "700 9.5px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>
                  <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 11.5px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{s.name}</div><div style={{ font: "500 8.5px 'IBM Plex Mono',monospace", color: "var(--text-mute)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>$ {s.prompt}</div></div>
                  <b style={{ width: 7, height: 7, borderRadius: "50%", background: live ? "var(--good)" : "var(--text-mute)", flex: "none", boxShadow: live ? "0 0 6px var(--good)" : "none" }} />
                </div>
                <div style={{ font: "500 9.5px/1.4 'IBM Plex Mono',monospace", color: live ? "var(--text-dim)" : "var(--text-mute)", background: "var(--panel-3)", border: "1px solid var(--border-soft)", borderRadius: 7, padding: "6px 9px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(s.output || "启动中…").split("\n").filter(Boolean).slice(-1)[0] || "运行中…"}</div>
              </div>
            ); })}
          </div>
        </div>

        {/* 邮件 & 应用 */}
        <div style={{ ...panel, display: "grid", gridTemplateRows: "auto auto minmax(0,1fr)", gap: 12, minHeight: 0, animation: "cxRise .72s ease both" }}>
          <div style={{ ...row(8) }}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>邮件 & 应用</span><span style={flex1} />{totalUnread > 0 && <span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "#ff8a8a", background: "rgba(255,93,93,.12)", borderRadius: 999, padding: "2px 8px" }}>{totalUnread} 未读</span>}</div>
          <AppsWidgetRow apps={notifApps} />
          <div style={{ display: "grid", gap: 7, overflowY: "auto", minHeight: 0, alignContent: "start", borderTop: "1px solid var(--border-soft)", paddingTop: 11 }}>
            <div style={{ ...row(8), marginBottom: 1 }}><span style={mono(9, "var(--text-mute)")}>通知状态 · {notifApps.length} 应用</span><span style={flex1} /><span style={{ ...row(4), ...mono(9.5, totalUnread > 0 ? "#ff8a8a" : "var(--good)") }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: totalUnread > 0 ? "#ff8a8a" : "var(--good)", display: "inline-block", boxShadow: `0 0 5px ${totalUnread > 0 ? "#ff8a8a" : "var(--good)"}` }} />{totalUnread > 0 ? `${totalUnread} 条待处理` : "全部已读"}</span></div>
            {notifApps.length === 0 && <div style={{ ...mono(10.5), padding: "14px 2px", textAlign: "center" }}>未监控任何应用通知</div>}
            {[...notifApps].sort((a, b) => (b.count || 0) - (a.count || 0)).map((a) => { const c = typeof a.count === "number" ? a.count : 0; return (
              <button key={a.id} onClick={() => openApp(a.id || a.name || "").catch(() => {})} className="cx-row" style={{ textAlign: "left", ...row(10), padding: "7px 9px", borderRadius: 10, background: c > 0 ? "rgba(255,93,93,.07)" : "var(--panel-2)", border: `1px solid ${c > 0 ? "rgba(255,93,93,.22)" : "var(--border-soft)"}`, cursor: "pointer" }}>
                <AppIcon a={a} size={28} />
                <div style={{ minWidth: 0, flex: 1 }}><b style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{a.name || a.id}</b><div style={mono(8.5)}>{a.kind === "mail" || /mail|邮/i.test(a.name || a.id) ? "邮件" : "消息"} · 点按打开</div></div>
                {c > 0
                  ? <span style={{ font: "700 10px 'IBM Plex Mono',monospace", color: "#fff", background: "var(--bad)", borderRadius: 999, padding: "3px 9px", flex: "none" }}>{c} 未读</span>
                  : <span style={{ ...row(4), ...mono(9.5, "var(--good)"), flex: "none" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", display: "inline-block" }} />已读</span>}
              </button>
            ); })}
          </div>
        </div>

        {/* 今日日程 —— 带独立填写入口 */}
        <SchedulePanel todos={todoNotes} onSaved={reloadNotes} onOpen={(id) => setOverlay({ open: true, id })} />

        {/* 个人记事 */}
        <div style={{ ...panel, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, animation: "cxRise .84s ease both" }}>
          <div style={{ ...row(8), marginBottom: 11 }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.9"><path d="M5 3h11l3 3v15H5z" /><path d="M8.5 9h7M8.5 12.5h7M8.5 16h4" /></svg><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>个人记事</span><span style={flex1} /><span onClick={() => setOverlay({ open: true })} className="cx-chip" style={{ ...row(4), border: "1px solid var(--border)", background: "var(--accent-soft)", color: "var(--accent)", borderRadius: 8, padding: "3px 9px", font: "600 10.5px 'Space Grotesk'", cursor: "pointer", whiteSpace: "nowrap" }}>＋ 记一笔</span></div>
          <div style={{ display: "grid", gap: 7, overflowY: "auto", minHeight: 0, alignContent: "start" }}>
            {notes.length === 0 && <div style={{ ...mono(10.5), padding: "6px 2px" }}>暂无记事，点「记一笔」</div>}
            {notes.slice(0, 4).map((nt) => (
              <button key={nt.id} onClick={() => setOverlay({ open: true, id: nt.id })} className="cx-row" style={{ textAlign: "left", background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: 10, padding: "8px 10px", display: "grid", gap: 2, cursor: "pointer" }}>
                <div style={{ ...row(6) }}>{nt.pinned && <span style={{ fontSize: 9 }}>📌</span>}<b style={{ font: "600 11px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{nt.title || "未命名"}</b><span style={{ font: "500 8px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>{nt.updated_ts ? fmtAgo(nt.updated_ts) : ""}</span></div>
                <p style={{ margin: 0, font: "400 9.5px/1.4 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{nt.excerpt || nt.content || ""}</p>
              </button>
            ))}
          </div>
        </div>
      </div>

      {detailId && <IntelDetail id={detailId} onClose={() => setDetailId(null)} />}
      {overlay.open && <NotesOverlay openId={overlay.id} onClose={() => { setOverlay({ open: false }); reloadNotes(); }} goFull={(id) => { setOverlay({ open: false }); goNotes(id); }} />}
    </div>
  );
}

// 邮件&应用图标行（不暗化, 可点击看详情/打开 —— 复用 R8 逻辑）
function AppsWidgetRow({ apps }: { apps: NotifApp[] }) {
  const local: Record<string, string> = { mail: "mail.png", wechat: "wechat.png", telegram: "telegram.png", popo: "popo.png", mailmaster: "mailmaster.png" };
  const [custom, setCustom] = useState<NotifApp[]>(() => { try { return JSON.parse(localStorage.getItem("cx-custom-apps") || "[]"); } catch { return []; } });
  const saveCustom = (c: NotifApp[]) => { setCustom(c); try { localStorage.setItem("cx-custom-apps", JSON.stringify(c)); } catch { /* ignore */ } };
  const list: NotifApp[] = [...apps.filter((a) => a.id === "gmail" || local[a.id] || a.icon), ...custom];
  const [sel, setSel] = useState<NotifApp | null>(null);
  const [opening, setOpening] = useState(false);
  async function open(a: NotifApp) { setOpening(true); try { await openApp(a.id || a.name || ""); } catch { /* ignore */ } finally { setOpening(false); setSel(null); } }
  function addCustom() { const name = window.prompt("添加应用：输入 macOS 应用名或网址（如 Safari / 备忘录 / Visual Studio Code / https://x.com）"); if (!name || !name.trim()) return; const id = name.trim(); if (custom.some((c) => c.id === id)) return; saveCustom([...custom, { id, name: id, custom: true } as NotifApp]); }
  return (
    <div style={{ position: "relative" }}>
      <div style={{ display: "flex", gap: 11, flexWrap: "wrap", alignItems: "center" }}>
        {list.map((a) => { const count = typeof a.count === "number" ? a.count : 0; return (
          <button key={a.id} title={a.name || a.id} onClick={() => setSel(sel?.id === a.id ? null : a)} className="cx-app" style={{ position: "relative", border: 0, background: "transparent", cursor: "pointer", padding: 0, borderRadius: 10, outline: sel?.id === a.id ? "2px solid var(--accent)" : "none", outlineOffset: 2 }}>
            <AppIcon a={a} />
            {count > 0 && <span style={{ position: "absolute", top: -5, right: -5, minWidth: 17, height: 17, padding: "0 4px", borderRadius: 9, background: "var(--bad)", color: "#fff", font: "700 9px 'IBM Plex Mono'", display: "grid", placeContent: "center", border: "2px solid var(--panel)" }}>{count}</span>}
          </button>
        ); })}
        <button onClick={addCustom} title="添加应用" className="cx-app" style={{ width: 46, height: 46, borderRadius: 12, border: "1px dashed var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", display: "grid", placeContent: "center", font: "700 19px 'Space Grotesk'", lineHeight: 0 }}>＋</button>
      </div>
      {sel && (
        <div style={{ position: "absolute", left: 0, right: 0, top: 46, zIndex: 20, background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 12, boxShadow: "var(--shadow)", padding: 11, display: "grid", gap: 9, animation: "cxRise .16s ease both" }}>
          <div style={{ ...row(9) }}><AppIcon a={sel} size={30} /><div style={{ flex: 1, minWidth: 0 }}><div style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{sel.name || sel.id}</div><div style={mono(9)}>{(sel as { custom?: boolean }).custom ? "自定义应用" : (typeof sel.count === "number" && sel.count > 0 ? `${sel.count} 条未读` : "无未读")}</div></div><button onClick={() => setSel(null)} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", width: 24, height: 24, borderRadius: 7, display: "grid", placeContent: "center" }}><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg></button></div>
          <div style={{ ...row(8) }}>
            <button onClick={() => open(sel)} disabled={opening} style={{ flex: 1, border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "7px 0", font: "600 11.5px 'Space Grotesk'", opacity: opening ? 0.6 : 1 }}>{opening ? "打开中…" : "打开"}</button>
            {(sel as { custom?: boolean }).custom && <button onClick={() => { saveCustom(custom.filter((c) => c.id !== sel.id)); setSel(null); }} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--bad)", cursor: "pointer", borderRadius: 8, padding: "7px 12px", font: "600 11px 'Space Grotesk'" }}>移除</button>}
          </div>
        </div>
      )}
    </div>
  );
}

// ============ AGENTS（P9 重构）============
// 真实交互终端：xterm.js ←→ 后端 PTY（/ws/term）。在这里跑的是 agent 的**原生 REPL**，
// 所以 claude 的 /model、/cost、/clear 这些原生斜杠命令会真实弹出、完整执行 —— 不是假壳。
const PTY_CAPABLE = ["claude", "codex", "cursor", "grok", "hermes", "openclaw", "shell"];
function PtyTerminal({ agent, themeMode, sessionKey }: { agent: string; themeMode: Theme; sessionKey: number }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"connecting" | "live" | "exited">("connecting");
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const dark = themeMode === "dark";
    const term = new XTerm({
      fontFamily: "'IBM Plex Mono','SFMono-Regular',monospace",
      fontSize: 12.5, lineHeight: 1.32, cursorBlink: true, scrollback: 5000,
      allowProposedApi: true,
      theme: dark
        ? { background: "#0f141b", foreground: "#cdd6e2", cursor: "#d9536b", cursorAccent: "#0f141b", selectionBackground: "rgba(217,83,107,.32)", black: "#0f141b", brightBlack: "#5b6573" }
        : { background: "#0f141b", foreground: "#cdd6e2", cursor: "#d9536b", cursorAccent: "#0f141b", selectionBackground: "rgba(217,83,107,.32)" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host);
    const doFit = () => { try { fit.fit(); } catch { /* noop */ } };
    setTimeout(doFit, 0);

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/ws/term`);
    ws.binaryType = "arraybuffer";
    const dec = new TextDecoder();
    ws.onopen = () => {
      setStatus("live");
      ws.send(JSON.stringify({ type: "start", agent, cwd: "~", cols: term.cols, rows: term.rows }));
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
    void dec;

    return () => { onData.dispose(); ro.disconnect(); try { ws.close(); } catch { /* noop */ } term.dispose(); };
    // sessionKey 变化 = 用户点了「重启会话」，强制重建终端
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, sessionKey]);

  return (
    <div style={{ position: "relative", height: "100%", minHeight: 0, background: "#0f141b" }}>
      <div ref={hostRef} style={{ height: "100%", padding: "8px 4px 8px 12px" }} />
      <span style={{ position: "absolute", top: 9, right: 13, ...row(5), font: "600 9px 'IBM Plex Mono',monospace", color: status === "live" ? "var(--good)" : status === "connecting" ? "var(--warn)" : "var(--text-mute)", pointerEvents: "none" }}>
        <b style={{ width: 6, height: 6, borderRadius: "50%", background: status === "live" ? "var(--good)" : status === "connecting" ? "var(--warn)" : "var(--text-mute)", display: "inline-block", boxShadow: status === "live" ? "0 0 6px var(--good)" : "none", animation: status === "live" ? "cxBreathe 2.5s ease infinite" : "none" }} />
        {status === "live" ? "PTY 在线" : status === "connecting" ? "连接中…" : "已结束"}
      </span>
    </div>
  );
}

function Agents({ themeMode }: { themeMode: Theme }) {
  const [agents, setAgents] = useState<CliAgent[]>([]);
  const [sessions, setSessions] = useState<CliSession[]>([]);
  const [external, setExternal] = useState<ExternalAgent[]>([]);
  const [sel, setSel] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [centerCmd, setCenterCmd] = useState("");
  const [slashIdx, setSlashIdx] = useState(0);
  const [agentCmds, setAgentCmds] = useState<CliCommand[]>([]);
  const [agentModels, setAgentModels] = useState<string[]>([]);
  const [modelOverride, setModelOverride] = useState<string | null>(null);
  const [modelMenu, setModelMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [termMode, setTermMode] = useState<"pty" | "task">("pty");  // E2: 默认进真实交互终端
  const [ptyKey, setPtyKey] = useState(0);                          // ++ = 重启 PTY 会话
  const termRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    getCliAgents().then((d) => { setAgents(d.agents); const inst = d.agents.find((a) => a.installed); if (inst) setSel((s) => s || inst.name); }).catch(() => {});
    const poll = () => getCliSessions().then((d) => { setSessions(d.sessions || []); setExternal(d.external || []); setActive((cur) => cur || (d.sessions && d.sessions[0]?.id) || null); }).catch(() => {});
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { const el = termRef.current; if (el) el.scrollTop = el.scrollHeight; }, [sessions, active]);
  // 取「当前目标 agent」真实支持的斜杠命令 + 模型清单。换 agent 时重置模型覆盖。
  useEffect(() => {
    const sess = sessions.find((s) => s.id === active);
    const ag = sess?.agent || (active && active.startsWith("gw:") ? active.slice(3) : "") || sel;
    if (!ag) { setAgentCmds([]); setAgentModels([]); return; }
    let live = true;
    getCliCommands(ag).then((d) => { if (live) { setAgentCmds(d.commands || []); setAgentModels(d.models || []); } }).catch(() => {});
    setModelOverride(null); setModelMenu(false);
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, active]);

  const installed = agents.filter((a) => a.installed);
  const runningCount = sessions.filter((s) => s.status === "running").length + external.length;
  const tagOf = (a: string): [string, string] => TAG[a] || [a.slice(0, 2).toUpperCase(), "#9aa6b2"];
  const cur = sessions.find((s) => s.id === active) || null;

  async function runWith(agentName: string, p: string) {
    if (!p.trim() || !agentName || busy) return;
    setBusy(true); setErr("");
    try {
      const r = await runCliAgent(agentName, p.trim(), "~", modelOverride || undefined);
      if (!r.ok) setErr(r.error || "启动失败");
      else { setPrompt(""); setCenterCmd(""); if (r.id) setActive(r.id); getCliSessions().then((d) => { setSessions(d.sessions || []); setExternal(d.external || []); }).catch(() => {}); }
    } catch (e) { setErr(String((e as Error)?.message || e)); } finally { setBusy(false); }
  }
  function run() { if (sel) runWith(sel, prompt); }
  async function stop(id: string) { await stopCliSession(id).catch(() => {}); getCliSessions().then((d) => { setSessions(d.sessions || []); setExternal(d.external || []); }).catch(() => {}); }
  async function clearDone() { await clearFinishedSessions().catch(() => {}); if (active && !active.startsWith("gw:")) setActive(null); getCliSessions().then((d) => { setSessions(d.sessions || []); setExternal(d.external || []); }).catch(() => {}); }
  // R6: 中间终端直接发指令（带 /model 选的模型）。
  function sendCenter(agentName: string) { runWith(agentName, centerCmd); }

  const finishedCount = sessions.filter((s) => s.status !== "running").length;
  const agentInfo = (name: string) => agents.find((a) => a.name === name);
  const curGw = active && active.startsWith("gw:") ? external.find((e) => `gw:${e.agent}` === active) || null : null;
  const info = cur ? agentInfo(cur.agent) : null;
  const target = cur?.agent || curGw?.agent || sel;  // R6: 中间终端发指令的目标 agent
  const targetLabel = cur?.name || curGw?.display || (installed.find((a) => a.name === sel)?.display) || sel || "agent";
  // E2: PTY 交互终端的目标 agent —— 选中的 agent 若支持交互就用它，否则回退到 claude / shell。
  const ptyAgent = PTY_CAPABLE.includes(sel) ? sel : (installed.find((a) => PTY_CAPABLE.includes(a.name))?.name || "shell");
  const ptyLabel = installed.find((a) => a.name === ptyAgent)?.display || (ptyAgent === "shell" ? "Shell" : ptyAgent);

  // 斜杠快捷指令：用后端给的「该 agent 真实支持的命令」（内建 + 扫描到的自定义命令）。
  const slashQuery = centerCmd.startsWith("/") ? centerCmd.slice(1).toLowerCase() : null;
  const slashMatches = slashQuery !== null ? agentCmds.filter((c) => slashQuery === "" || c.cmd.slice(1).toLowerCase().startsWith(slashQuery) || c.label.toLowerCase().includes(slashQuery)) : [];
  const slashOpen = !modelMenu && slashQuery !== null && slashMatches.length > 0;
  function pickSlash(c: CliCommand) {
    setSlashIdx(0);
    if (c.kind === "model") { setModelMenu(true); return; }              // /model → 弹真实模型菜单
    if (c.kind === "clear") { setActive(null); setCenterCmd(""); return; }
    setCenterCmd("");                                                     // 立即收起菜单
    if (target) runWith(target, c.cmd);                                   // send/自定义：发给 agent（claude -p "/cmd" 会展开）
  }
  function pickModel(m: string) { setModelOverride(m); setModelMenu(false); setCenterCmd(""); setSlashIdx(0); }

  return (
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateColumns: "300px minmax(0,1fr) 264px", gap: 14, padding: 16, minHeight: 0 }}>
      {/* LEFT rail */}
      <div style={{ display: "grid", gridTemplateRows: "auto auto minmax(0,1fr)", gap: 14, minHeight: 0 }}>
        <div style={{ ...panel, padding: "14px 16px" }}>
          <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>编排台 · ORCHESTRATOR</div>
          <div style={{ ...row(10), marginTop: 8 }}>
            <div style={{ font: "700 22px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{runningCount}<span style={{ font: "500 12px 'Space Grotesk'", color: "var(--text-mute)" }}> 运行中</span></div>
            <span style={flex1} />
            <div style={{ textAlign: "right" }}><div style={mono(9.5)}>已装 AGENT</div><div style={{ font: "700 16px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>{installed.length}</div></div>
          </div>
        </div>

        <div style={{ ...panel, padding: "12px 14px", display: "grid", gap: 9 }}>
          <div style={{ ...row(7), flexWrap: "wrap" }}>
            {installed.map((a) => { const [tg, fg] = tagOf(a.name); const on = sel === a.name; return (
              <button key={a.name} onClick={() => setSel(a.name)} title={a.version || ""} style={{ ...row(6), border: `1px solid ${on ? fg : "var(--border)"}`, background: on ? "var(--accent-soft)" : "var(--panel-2)", cursor: "pointer", borderRadius: 9, padding: "6px 10px" }}><span style={{ font: "700 10px 'IBM Plex Mono',monospace", color: fg }}>{tg}</span><span style={{ font: "600 12px 'Space Grotesk',sans-serif", color: on ? "var(--text)" : "var(--text-dim)" }}>{a.display}</span></button>
            ); })}
            {installed.length === 0 && <span style={mono(11)}>检测本机 agent 中…</span>}
          </div>
          <div style={{ ...row(9), background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 10, padding: "0 12px", height: 40 }}>
            <span style={{ font: "600 13px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>$</span>
            <input value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") run(); }} placeholder={`给 ${sel || "agent"} 一个任务…`} style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "var(--text)", font: "500 13px 'Space Grotesk',sans-serif" }} />
            <button onClick={run} disabled={busy} style={{ border: 0, cursor: busy ? "default" : "pointer", background: "var(--accent)", color: "#fff", font: "600 11px 'Space Grotesk'", padding: "6px 13px", borderRadius: 7, opacity: busy ? 0.6 : 1 }}>{busy ? "启动中" : "运行"}</button>
          </div>
          {err && <div style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "var(--bad)" }}>{err}</div>}
        </div>

        <div style={{ ...panel, padding: "12px 12px", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0 }}>
          <div style={{ ...row(8), marginBottom: 9 }}><span style={lbl}>会话 / 网关</span><span style={flex1} />{finishedCount > 0 && <button onClick={clearDone} title="清空已结束会话" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", borderRadius: 7, padding: "3px 8px", font: "500 9.5px 'Space Grotesk'" }}>清空已结束 {finishedCount}</button>}<span style={mono(10, "var(--text-dim)")}>{sessions.length + external.length}</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, display: "grid", gap: 7, alignContent: "start", paddingRight: 2 }}>
            {external.length > 0 && <div style={{ ...row(6) }}><span style={{ ...mono(9, "var(--good)"), letterSpacing: ".1em" }}>常驻网关 · 在运行</span><span style={flex1} /><span title="常驻网关 = 后台一直跑着的守护进程（检测到端口在监听，如 Hermes :8642、OpenClaw :18789）。claude / codex / cursor / grok 是命令行工具，按需调用、平时没有常驻进程，所以不在这一组——这就是为什么只有这两个显示常驻运行。" style={{ ...mono(11, "var(--text-mute)"), cursor: "help", border: "1px solid var(--border)", borderRadius: "50%", width: 15, height: 15, display: "grid", placeContent: "center", lineHeight: 1 }}>?</span></div>}
            {external.map((e) => { const [tg, fg] = tagOf(e.agent); const on = active === `gw:${e.agent}`; return (
              <button key={`ext-${e.agent}`} onClick={() => { setActive(`gw:${e.agent}`); setSel(e.agent); setTermMode("pty"); }} style={{ textAlign: "left", ...row(9), background: on ? "var(--accent-soft)" : "var(--panel-2)", border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`, borderRadius: 10, padding: "9px 10px", cursor: "pointer", width: "100%" }}>
                <span style={{ width: 26, height: 26, borderRadius: 7, background: "var(--panel-3)", border: "1px solid var(--border)", display: "grid", placeContent: "center", font: "700 10px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>
                <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{e.display}</div><div style={mono(9)}>:{e.port} 网关常驻</div></div>
                <span style={{ ...row(4), ...mono(9, "var(--good)"), flex: "none" }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 3s ease infinite" }} />运行中</span>
              </button>
            ); })}
            {sessions.length === 0 && external.length === 0 && <div style={{ ...mono(10.5), padding: "8px 2px", lineHeight: 1.6 }}>还没有会话。选 agent、给个任务，输出实时流到中间。</div>}
            {sessions.length > 0 && <div style={{ ...row(6), marginTop: external.length ? 4 : 0 }}><span style={{ ...mono(9, "var(--text-mute)"), letterSpacing: ".1em" }}>CLI 会话 · 按需调用</span></div>}
            {sessions.map((s) => { const [tg, fg] = tagOf(s.agent); const live = s.status === "running"; const on = active === s.id; return (
              <button key={s.id} onClick={() => { setActive(s.id); setTermMode("task"); }} style={{ textAlign: "left", ...row(9), background: on ? "var(--accent-soft)" : "var(--panel-2)", border: `1px solid ${on ? "var(--accent)" : "var(--border-soft)"}`, borderRadius: 10, padding: "9px 10px", cursor: "pointer", width: "100%" }}>
                <span style={{ width: 26, height: 26, borderRadius: 7, background: "var(--panel-3)", border: "1px solid var(--border)", display: "grid", placeContent: "center", font: "700 10px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>
                <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</div><div style={{ ...mono(9), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.prompt}</div></div>
                <b style={{ width: 7, height: 7, borderRadius: "50%", background: live ? "var(--good)" : "var(--text-mute)", flex: "none", boxShadow: live ? "0 0 6px var(--good)" : "none" }} />
              </button>
            ); })}
          </div>
        </div>
      </div>

      {/* CENTER — 真实交互终端(PTY，默认) / 任务输出流 双模 */}
      <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden" }}>
        {/* 顶部：分段 Tab + 状态 */}
        <div style={{ ...row(10), padding: "10px 12px 10px 14px", borderBottom: "1px solid var(--border-soft)" }}>
          <div style={{ display: "flex", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: 3, gap: 2 }}>
            {([["pty", "⚡ 交互终端"], ["task", "📋 任务流"]] as const).map(([m, label]) => (
              <button key={m} onClick={() => setTermMode(m)} style={{ border: 0, cursor: "pointer", borderRadius: 7, padding: "5px 13px", font: "600 11px 'Space Grotesk',sans-serif", background: termMode === m ? "var(--accent)" : "transparent", color: termMode === m ? "#fff" : "var(--text-dim)", transition: "all .15s" }}>{label}</button>
            ))}
          </div>
          <span style={flex1} />
          {termMode === "pty" ? (
            <div style={{ ...row(8) }}>
              {(() => { const [tg, fg] = tagOf(ptyAgent); return <span style={{ ...row(5), font: "600 11px 'IBM Plex Mono',monospace", color: "var(--text-dim)" }}><b style={{ color: fg, fontWeight: 700 }}>{tg}</b>{ptyLabel} · 原生 REPL</span>; })()}
              <button onClick={() => setPtyKey((k) => k + 1)} title="重启这个交互会话（清空并重新启动 agent）" className="cx-chip" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", cursor: "pointer", borderRadius: 7, padding: "5px 11px", ...mono(9.5, "var(--text-dim)") }}>↻ 重启</button>
            </div>
          ) : cur ? (
            <span style={{ ...row(5), flex: "none", font: "600 9.5px 'IBM Plex Mono',monospace", color: cur.status === "running" ? "var(--good)" : "var(--text-mute)" }}><b style={{ width: 7, height: 7, borderRadius: "50%", background: cur.status === "running" ? "var(--good)" : "var(--text-mute)", display: "inline-block", boxShadow: cur.status === "running" ? "0 0 7px var(--good)" : "none", animation: cur.status === "running" ? "cxBreathe 2.5s ease infinite" : "none" }} />{cur.status === "running" ? "运行中" : "已结束"}</span>
          ) : <span style={mono(10)}>点左侧会话看输出</span>}
        </div>

        {/* 主体 */}
        {termMode === "pty" ? (
          <PtyTerminal agent={ptyAgent} themeMode={themeMode} sessionKey={ptyKey} />
        ) : (
          <div style={{ display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0 }}>
            <div style={{ ...row(10), padding: "12px 16px 10px", borderBottom: "1px solid var(--border-soft)" }}>
              {cur ? (<>
                {(() => { const [tg, fg] = tagOf(cur.agent); return <span style={{ width: 28, height: 28, borderRadius: 8, background: "var(--panel-2)", border: "1px solid var(--border)", display: "grid", placeContent: "center", font: "700 10px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>; })()}
                <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{cur.name}</div><div style={{ ...mono(9.5), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>$ {cur.prompt}</div></div>
              </>) : curGw ? (<>
                {(() => { const [tg, fg] = tagOf(curGw.agent); return <span style={{ width: 28, height: 28, borderRadius: 8, background: "var(--panel-2)", border: "1px solid var(--border)", display: "grid", placeContent: "center", font: "700 10px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>; })()}
                <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{curGw.display}</div><div style={mono(9.5)}>:{curGw.port} · 常驻网关</div></div>
              </>) : (<>
                <span style={{ width: 28, height: 28, borderRadius: 8, background: "var(--panel-2)", border: "1px solid var(--border)", display: "grid", placeContent: "center", font: "700 13px 'IBM Plex Mono'", color: "var(--accent)", flex: "none" }}>$</span>
                <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>任务输出流</div><div style={mono(9.5)}>一次性任务（{`${ptyLabel} -p`}）的实时输出汇总到这里</div></div>
              </>)}
            </div>
            {cur
              ? <pre ref={termRef} style={{ margin: 0, padding: "14px 16px", background: "var(--panel-3)", font: "500 11.5px/1.62 'IBM Plex Mono',monospace", color: "#9aa6b2", overflowY: "auto", minHeight: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{cur.output || "启动中…"}</pre>
              : curGw
                ? <div style={{ overflowY: "auto", minHeight: 0, display: "grid", placeContent: "center", textAlign: "center", padding: 30, gap: 12 }}>
                    <p style={{ margin: 0, font: "400 12.5px/1.75 'Space Grotesk',sans-serif", color: "var(--text-dim)", maxWidth: 420 }}>{curGw.docs || "本机常驻 agent 网关，一直在后台运行。"}</p>
                    <div style={{ ...sub, padding: "12px 14px", textAlign: "left", maxWidth: 420, margin: "0 auto" }}><div style={mono(9.5)}>在下方输入框直接给它发任务，等价于：</div><code style={{ display: "block", marginTop: 6, font: "500 11.5px 'IBM Plex Mono'", color: "var(--accent)" }}>{curGw.agent === "hermes" ? "hermes -z <任务>" : "openclaw agent <任务>"}</code></div>
                  </div>
                : <div style={{ overflowY: "auto", minHeight: 0, display: "grid", placeContent: "center", textAlign: "center", color: "var(--text-mute)", padding: 30 }}>
                    <div style={{ font: "600 14px 'Space Grotesk',sans-serif", marginBottom: 8, color: "var(--text-dim)" }}>一次性任务流</div>
                    <div style={{ font: "400 12px/1.7 'Space Grotesk',sans-serif", maxWidth: 340 }}>下面输入命令回车即可后台驱动（切到别的页面也不会终止）；或点左侧已有会话查看其输出。想要原生斜杠命令？切到 <b style={{ color: "var(--accent)" }}>⚡ 交互终端</b>。</div>
                  </div>}
          </div>
        )}

        {/* 底部：PTY 模式给提示条；任务模式给输入条 */}
        {termMode === "pty" ? (
          <div style={{ ...row(9), padding: "9px 14px", borderTop: "1px solid var(--border-soft)", background: "var(--panel)" }}>
            <span style={{ font: "700 13px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>❯</span>
            <span style={{ font: "400 11px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", flex: 1 }}>直接在上方终端里敲 —— <b style={{ color: "var(--text)" }}>/model</b> <b style={{ color: "var(--text)" }}>/cost</b> <b style={{ color: "var(--text)" }}>/clear</b> 等<b style={{ color: "var(--accent)" }}>原生斜杠命令完整执行</b>（这是 {ptyLabel} 的真实 REPL，不是输入框）。左侧切 agent。</span>
          </div>
        ) : (
        <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border-soft)", display: "grid", gap: 8, position: "relative" }}>
          {(slashOpen || modelMenu) && (
            <div className="cx-pop-in" style={{ position: "absolute", bottom: "calc(100% - 2px)", left: 16, right: 16, background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 11, boxShadow: "var(--shadow)", overflow: "hidden", zIndex: 30, maxHeight: 320, overflowY: "auto" }}>
              {modelMenu ? (<>
                <div style={{ ...row(8), padding: "7px 12px", borderBottom: "1px solid var(--border-soft)" }}><button onClick={() => setModelMenu(false)} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", ...mono(9, "var(--text-mute)") }}>‹ 返回</button><span style={mono(9, "var(--accent)")}>选择模型 · {targetLabel}</span><span style={flex1} /><span style={mono(8.5)}>↑↓ ↵</span></div>
                {agentModels.length === 0 && <div style={{ ...mono(10.5), padding: "12px" }}>该 agent 无可选模型</div>}
                {agentModels.map((m, i) => (
                  <button key={m} onMouseEnter={() => setSlashIdx(i)} onClick={() => pickModel(m)} style={{ ...row(10), width: "100%", textAlign: "left", border: 0, cursor: "pointer", background: i === slashIdx ? "var(--accent-soft)" : "transparent", padding: "10px 12px", borderBottom: "1px solid var(--border-soft)" }}>
                    <code style={{ font: "600 12px 'IBM Plex Mono',monospace", color: "var(--accent)", flex: 1 }}>{m}</code>
                    {modelOverride === m && <span style={mono(9, "var(--good)")}>● 当前</span>}
                  </button>
                ))}
              </>) : (<>
                <div style={{ ...row(8), padding: "7px 12px", borderBottom: "1px solid var(--border-soft)" }}><span style={mono(9, "var(--accent)")}>{targetLabel} · 真实命令</span><span style={flex1} /><span style={mono(8.5)}>↑↓ 选择 · ↵ 确认 · esc 关闭</span></div>
                {slashMatches.map((s, i) => (
                  <button key={s.cmd} onMouseEnter={() => setSlashIdx(i)} onClick={() => pickSlash(s)} style={{ ...row(10), width: "100%", textAlign: "left", border: 0, cursor: "pointer", background: i === slashIdx ? "var(--accent-soft)" : "transparent", padding: "9px 12px", borderBottom: "1px solid var(--border-soft)" }}>
                    <code style={{ font: "600 11.5px 'IBM Plex Mono',monospace", color: "var(--accent)", flex: "none", minWidth: 92 }}>{s.cmd}</code>
                    <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{s.label}</div><div style={{ ...mono(9), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.desc}</div></div>
                    {s.kind === "model" && <span style={{ ...mono(8.5, "var(--accent)"), flex: "none" }}>▸ 选择</span>}
                    {s.kind === "clear" && <span style={{ ...mono(8.5, "var(--warn)"), flex: "none" }}>控制</span>}
                  </button>
                ))}
              </>)}
            </div>
          )}
          <div style={{ ...row(9), background: "var(--panel-3)", border: `1px solid ${(slashOpen || modelMenu) ? "var(--accent)" : target ? "var(--border)" : "var(--border-soft)"}`, borderRadius: 9, padding: "0 12px", height: 40 }}>
            <span style={{ font: "600 14px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>❯</span>
            {modelOverride && <span style={{ ...row(4), flex: "none", background: "var(--accent-soft)", border: "1px solid var(--accent)", borderRadius: 7, padding: "3px 8px", ...mono(9.5, "var(--accent)") }}>{modelOverride}<b onClick={() => setModelOverride(null)} style={{ cursor: "pointer" }}>✕</b></span>}
            <input value={centerCmd}
              onChange={(e) => { setCenterCmd(e.target.value); setSlashIdx(0); }}
              onKeyDown={(e) => {
                if (modelMenu) {
                  if (e.key === "ArrowDown") { e.preventDefault(); setSlashIdx((i) => Math.min(i + 1, agentModels.length - 1)); return; }
                  if (e.key === "ArrowUp") { e.preventDefault(); setSlashIdx((i) => Math.max(i - 1, 0)); return; }
                  if (e.key === "Enter") { e.preventDefault(); if (agentModels[slashIdx]) pickModel(agentModels[slashIdx]); return; }
                  if (e.key === "Escape") { e.preventDefault(); setModelMenu(false); return; }
                  return;
                }
                if (slashOpen) {
                  if (e.key === "ArrowDown") { e.preventDefault(); setSlashIdx((i) => Math.min(i + 1, slashMatches.length - 1)); return; }
                  if (e.key === "ArrowUp") { e.preventDefault(); setSlashIdx((i) => Math.max(i - 1, 0)); return; }
                  if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pickSlash(slashMatches[slashIdx]); return; }
                  if (e.key === "Escape") { e.preventDefault(); setCenterCmd(""); return; }
                }
                if (e.key === "Enter" && target) sendCenter(target);
              }}
              placeholder={target ? `给 ${targetLabel} 发指令，回车执行（输入 / 调出 ${agentCmds.length} 个真实命令）…` : "先在左上选一个 agent…"} style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "var(--text)", font: "500 12.5px 'IBM Plex Mono',monospace" }} />
            <button onClick={() => target && sendCenter(target)} disabled={busy || !target || !centerCmd.trim()} style={{ border: 0, cursor: busy || !target ? "default" : "pointer", background: "var(--accent)", color: "#fff", font: "600 11px 'Space Grotesk'", padding: "7px 14px", borderRadius: 7, opacity: busy || !target || !centerCmd.trim() ? 0.5 : 1 }}>{busy ? "…" : "发送"}</button>
          </div>
          {err && <div style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "var(--bad)" }}>{err}</div>}
          {cur && <div style={{ ...row(8) }}><span style={mono(9.5)}>pid {cur.pid} · {fmtAgo(cur.started)}前 · {(cur.output || "").length} 字符</span><span style={flex1} />{cur.status === "running" && <button onClick={() => stop(cur.id)} style={{ border: "1px solid var(--border)", background: "transparent", cursor: "pointer", borderRadius: 7, padding: "5px 13px", color: "var(--bad)", font: "600 10.5px 'Space Grotesk'" }}>停止</button>}</div>}
        </div>
        )}
      </div>

      {/* RIGHT — 详情面板（不再单调）*/}
      <div style={{ ...panel, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, gap: 0 }}>
        <div style={{ ...row(8), marginBottom: 12 }}><span style={lbl}>详情</span></div>
        <div style={{ overflowY: "auto", minHeight: 0, display: "grid", gap: 11, alignContent: "start" }}>
          {cur && info && (<>
            <div style={{ ...sub, padding: "11px 13px", display: "grid", gap: 7 }}>
              <div style={{ ...row(8) }}><span style={mono(9.5)}>AGENT</span><span style={flex1} /><b style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)" }}>{info.display}</b></div>
              <div style={{ ...row(8) }}><span style={mono(9.5)}>版本</span><span style={flex1} /><span style={{ ...mono(10, "var(--text-dim)"), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 150 }}>{info.version || "—"}</span></div>
              <div style={{ ...row(8) }}><span style={mono(9.5)}>认证</span><span style={flex1} /><span style={mono(10, info.auth === "creds-present" ? "var(--good)" : "var(--warn)")}>{info.auth}</span></div>
              <div style={{ ...row(8) }}><span style={mono(9.5)}>驱动</span><span style={flex1} /><span style={mono(10, "var(--text-dim)")}>{info.run_supported}</span></div>
            </div>
            <div style={{ ...sub, padding: "11px 13px" }}><div style={{ ...mono(9.5), marginBottom: 5 }}>上下文 / 任务</div><div style={{ font: "400 12px/1.6 'Space Grotesk',sans-serif", color: "var(--text-dim)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{cur.prompt}</div></div>
            <div style={{ ...row(8) }}><span style={mono(9.5)}>输出</span><span style={flex1} /><span style={mono(10, "var(--text-dim)")}>{(cur.output || "").length} 字符</span></div>
          </>)}
          {curGw && (<>
            <div style={{ ...sub, padding: "11px 13px", display: "grid", gap: 7 }}>
              <div style={{ ...row(8) }}><span style={mono(9.5)}>类型</span><span style={flex1} /><b style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)" }}>常驻网关</b></div>
              <div style={{ ...row(8) }}><span style={mono(9.5)}>端口</span><span style={flex1} /><span style={mono(10, "var(--accent)")}>:{curGw.port}</span></div>
              <div style={{ ...row(8) }}><span style={mono(9.5)}>状态</span><span style={flex1} /><span style={mono(10, "var(--good)")}>运行中</span></div>
            </div>
            <div style={{ ...sub, padding: "11px 13px" }}><div style={{ ...mono(9.5), marginBottom: 5 }}>说明</div><div style={{ font: "400 11.5px/1.6 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>{curGw.docs}</div></div>
          </>)}
          {!cur && !curGw && (
            <div style={{ display: "grid", gap: 8 }}>
              <div style={mono(9.5)}>已装 AGENT · {installed.length}</div>
              {installed.map((a) => { const [tg, fg] = tagOf(a.name); return (
                <div key={a.name} style={{ ...row(8), ...sub, padding: "8px 10px" }}><span style={{ font: "700 9px 'IBM Plex Mono'", color: fg, width: 22 }}>{tg}</span><div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 11.5px 'Space Grotesk'", color: "var(--text)" }}>{a.display}</div><div style={{ ...mono(8.5), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.version || a.run_supported}</div></div><span style={{ width: 6, height: 6, borderRadius: "50%", background: a.auth === "creds-present" ? "var(--good)" : "var(--warn)", flex: "none" }} /></div>
              ); })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============ INTEL ============
function repoSignal(speed: number): { sig: string; fg: string; bg: string } {
  if (speed >= 300) return { sig: "爆发", fg: "#fff", bg: "var(--bad)" };
  if (speed >= 80) return { sig: "加速", fg: "#fff", bg: "var(--accent)" };
  return { sig: "升温", fg: "var(--accent)", bg: "var(--accent-soft)" };
}
function compactNum(n?: number): string {
  if (typeof n !== "number" || !isFinite(n)) return "—";
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k";
  return String(n);
}

function IntelDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const [item, setItem] = useState<BriefDetailItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let live = true;
    setLoading(true); setErr(false); setItem(null);
    getBriefingItem(id).then((r) => { if (!live) return; if (r?.ok && r.item) setItem(r.item); else setErr(true); }).catch(() => { if (live) setErr(true); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [id]);
  useEffect(() => { const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, [onClose]);

  const [pf, pb] = priStyle(item?.priority);
  const time = tsToTime(item?.ts);
  const openUrl = () => { if (item?.url) window.open(item.url, "_blank", "noopener,noreferrer"); };
  const sectLbl: CSSProperties = { font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".14em", color: "var(--text-mute)", marginBottom: 8 };
  const bodyText: CSSProperties = { margin: 0, font: "400 14px/1.85 'Space Grotesk','PingFang SC',sans-serif", color: "var(--text-dim)", whiteSpace: "pre-wrap" };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(4,6,9,.55)", backdropFilter: "blur(2px)", display: "flex", justifyContent: "flex-end", animation: "cxFade .18s ease both" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: "min(560px,92vw)", height: "100%", background: "var(--panel)", borderLeft: "1px solid var(--border)", boxShadow: "-24px 0 60px rgba(0,0,0,.4)", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", animation: "cxSlideIn .26s cubic-bezier(.22,.61,.36,1) both" }}>
        <div style={{ ...row(10), padding: "16px 20px 14px", borderBottom: "1px solid var(--border-soft)" }}>
          <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>情报详情 · DETAIL</span>
          <span style={flex1} />
          <button onClick={onClose} aria-label="关闭" style={{ width: 28, height: 28, display: "grid", placeContent: "center", border: "1px solid var(--border)", background: "var(--panel-2)", borderRadius: 8, cursor: "pointer", color: "var(--text-dim)" }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
        </div>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "20px 22px 28px" }}>
          {loading && (
            <div style={{ display: "grid", gap: 12, placeItems: "center", padding: "60px 0", textAlign: "center" }}>
              <div style={{ display: "flex", gap: 5 }}>{[0, 1, 2].map((i) => (<span key={i} style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)", animation: "cxType 1s ease-in-out infinite", animationDelay: `${i * 0.16}s` }} />))}</div>
              <span style={{ font: "500 12px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>正在翻译 / 读取详情…</span>
            </div>
          )}
          {!loading && err && (
            <div style={{ display: "grid", gap: 10, placeItems: "center", padding: "60px 0", textAlign: "center" }}>
              <span style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>详情加载失败</span>
              <span style={{ font: "400 12px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>后端无响应或该条目暂无详情。</span>
            </div>
          )}
          {!loading && !err && item && (<>
            <div style={{ ...row(8), marginBottom: 12, flexWrap: "wrap" }}>
              <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: pf, background: pb, borderRadius: 999, padding: "3px 9px" }}>{item.priority || "观察"}</span>
              <span style={mono(10.5, "var(--text-dim)")}>{item.source || ""}{time ? ` · ${time}` : ""}</span>
              {typeof item.score === "number" && <><span style={flex1} /><span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>评分 {item.score.toFixed(2)}</span></>}
            </div>
            <h2 style={{ margin: "0 0 18px", font: "600 21px/1.4 'Space Grotesk','PingFang SC',sans-serif", color: "var(--text)" }}>{item.title || "(无标题)"}</h2>
            <div style={{ marginBottom: 20 }}>
              <div style={sectLbl}>全文 · 中文{item.source_detail_translated ? "（已翻译）" : ""}</div>
              <div style={{ ...sub, padding: "14px 16px" }}>
                {item.source_detail && item.source_detail.trim() ? <p style={bodyText}>{item.source_detail}</p> : <p style={{ ...bodyText, color: "var(--text-mute)" }}>{item.source_detail_missing ? "该来源未提供可读全文。" : (item.take || "暂无全文正文。")}</p>}
              </div>
            </div>
            {item.why_important && (<div style={{ marginBottom: 18 }}><div style={sectLbl}>为什么重要</div><p style={bodyText}>{item.why_important}</p></div>)}
            {(item.take || item.next_step) && (<div style={{ marginBottom: 18 }}><div style={sectLbl}>建议</div>{item.take && <p style={{ ...bodyText, marginBottom: item.next_step ? 8 : 0 }}>{item.take}</p>}{item.next_step && <p style={{ ...bodyText }}><span style={{ color: "var(--accent)" }}>下一步 · </span>{item.next_step}</p>}</div>)}
            {Array.isArray(item.reasons) && item.reasons.length > 0 && (<div style={{ marginBottom: 18 }}><div style={sectLbl}>判断依据</div><div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{item.reasons.map((r, i) => (<span key={i} style={{ font: "500 11px 'Space Grotesk',sans-serif", color: "var(--text-dim)", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 999, padding: "5px 11px" }}>{r}</span>))}</div></div>)}
            {item.url && (<button onClick={openUrl} className="cx-chip" style={{ ...row(8), border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--accent)", cursor: "pointer", font: "600 12px 'Space Grotesk',sans-serif", padding: "10px 14px", borderRadius: 10, width: "100%", justifyContent: "center" }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 5h5v5M19 5l-9 9M11 5H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg>打开原文链接</button>)}
          </>)}
        </div>
      </div>
    </div>
  );
}

function Intel() {
  const [brief, setBrief] = useState<Briefing | null>(null);
  const [intelData, setIntelData] = useState<Intelligence | null>(null);
  const [filter, setFilter] = useState("全部");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const filters = ["全部", "高优先", "中优先", "观察"];

  useEffect(() => {
    let live = true;
    const load = () => {
      getBriefing().then((b) => { if (live) setBrief(b); }).catch(() => { if (live) setBrief((p) => p ?? { items: [], counts: {} }); });
      getIntelligence().then((d) => { if (live) setIntelData(d); }).catch(() => { if (live) setIntelData((p) => p ?? {}); });
    };
    load();
    const t = setInterval(load, 90000);
    return () => { live = false; clearInterval(t); };
  }, []);

  // 按发布时间倒序（最新滚动在最前）；重要性只作筛选维度，不左右默认顺序。
  const items: BriefItem[] = (Array.isArray(brief?.items) ? brief!.items! : []).filter((it) => it.kind !== "github_repo" && it.kind !== "repo").sort((a, b) => ((b.ts as number) || 0) - ((a.ts as number) || 0));
  const total = items.length;
  const countPri = (p: string) => items.filter((it) => (it.priority || "观察") === p).length;
  const nHigh = countPri("高优先"), nMid = countPri("中优先"), nWatch = items.length - nHigh - nMid;
  const shown = (filter === "全部" ? items : items.filter((it) => (it.priority || "观察") === filter)).slice(0, 240);

  const repos: IntelRepo[] = Array.isArray(intelData?.github) ? intelData!.github! : [];
  const sources: IntelSource[] = Array.isArray(intelData?.sources) ? intelData!.sources! : [];
  const targets: IntelTarget[] = Array.isArray(intelData?.targets) ? intelData!.targets! : [];
  const srcGroups = (() => {
    const m = new Map<string, { total: number; on: number }>();
    for (const s of sources) { const k = (s.type || "其它").toString(); const g = m.get(k) || { total: 0, on: 0 }; g.total++; if (s.enabled) g.on++; m.set(k, g); }
    const dispName: Record<string, string> = { rss: "RSS 源", web: "网页变化监控", github: "GitHub 雷达", mail: "邮件 IMAP", imap: "邮件 IMAP", ics: "ICS 日历", x: "X / 推文" };
    return Array.from(m.entries()).map(([k, g]) => ({ key: k, name: dispName[k] || k, count: `${g.on}/${g.total}`, dot: g.on > 0 ? "var(--good)" : "var(--text-mute)" }));
  })();

  const headBar = { ...row(8), padding: "15px 16px 12px", borderBottom: "1px solid var(--border-soft)" };
  const col = { ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, overflow: "hidden" } as CSSProperties;
  return (
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", gap: 14, padding: 16, minHeight: 0 }}>
      <style>{"@keyframes cxSlideIn{from{transform:translateX(28px);opacity:.4}to{transform:translateX(0);opacity:1}}@keyframes cxFade{from{opacity:0}to{opacity:1}}"}</style>
      <div style={{ ...panel, padding: "14px 16px", ...row(18), flexWrap: "wrap" }}>
        <div style={{ flex: "none", display: "flex", alignItems: "baseline", gap: 8 }}><b style={{ font: "700 26px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{total}</b><span style={mono(11)}>今日信号</span></div>
        <div style={{ flex: "none", display: "flex", gap: 8, font: "600 10.5px 'IBM Plex Mono',monospace" }}>
          <span style={{ ...row(5), background: "rgba(216,58,58,.14)", color: "var(--bad)", borderRadius: 7, padding: "5px 9px" }}>高优先 {nHigh}</span>
          <span style={{ ...row(5), background: "var(--accent-soft)", color: "var(--accent)", borderRadius: 7, padding: "5px 9px" }}>中优先 {nMid}</span>
          <span style={{ ...row(5), background: "var(--panel-2)", color: "var(--text-dim)", borderRadius: 7, padding: "5px 9px" }}>观察 {nWatch}</span>
        </div>
        <span style={{ flex: 1, minWidth: 20 }} />
        <div style={{ flex: "none", display: "flex", gap: 5, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: 4 }}>
          {filters.map((f) => (<button key={f} onClick={() => setFilter(f)} style={{ border: 0, cursor: "pointer", font: "600 11px 'Space Grotesk',sans-serif", padding: "6px 13px", borderRadius: 6, color: filter === f ? "#fff" : "var(--text-dim)", background: filter === f ? "var(--accent)" : "transparent", transition: "all .16s", whiteSpace: "nowrap" }}>{f}</button>))}
        </div>
        <span style={{ flex: "none", ...mono(10) }}>来源 {sources.length} · 关注 {targets.length}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.45fr) minmax(0,1fr) 286px", gap: 14, minHeight: 0 }}>
        <div style={col}>
          <div style={headBar}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>信号流 · 已筛选评分</span><span style={flex1} /><span style={mono(10, "var(--text-dim)")}>{shown.length} 条</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "8px 16px 16px" }}>
            {brief === null && <div style={{ ...mono(11), padding: "20px 0", textAlign: "center" }}>正在加载信号流…</div>}
            {brief !== null && shown.length === 0 && <div style={{ ...mono(11), padding: "20px 0", textAlign: "center" }}>暂无{filter === "全部" ? "" : filter}信号</div>}
            {shown.map((it, i) => { const [pf, pb] = priStyle(it.priority); const time = tsToTime(it.ts); const id = it.event_id; const cat = (it as { category?: string }).category; return (
              <button key={id || i} onClick={() => { if (id) setSelectedId(id); }} className="cx-intel" style={{ textAlign: "left", width: "100%", border: 0, cursor: id ? "pointer" : "default", background: "transparent", padding: "13px 6px", borderBottom: "1px solid var(--border-soft)", display: "grid", gap: 6, borderRadius: 8 }}>
                <div style={row(8)}><span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: pf, background: pb, borderRadius: 999, padding: "2px 8px" }}>{it.priority || "观察"}</span><span style={mono(10)}>{it.source || ""}{time ? ` · ${time}` : ""}</span>{cat && <span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "var(--text-mute)", background: "var(--panel-2)", borderRadius: 999, padding: "2px 7px" }}>{cat}</span>}<span style={flex1} />{typeof it.score === "number" && <span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>评分 {it.score.toFixed(2)}</span>}</div>
                <b style={{ font: "600 14px/1.4 'Space Grotesk',sans-serif", color: "var(--text)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{it.title}</b>
                {it.take && <p style={{ margin: 0, font: "400 12px/1.55 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{it.take}</p>}
              </button>
            ); })}
          </div>
        </div>
        <div style={col}>
          <div style={headBar}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>GITHUB 雷达</span><span style={flex1} /><span style={mono(10, "var(--text-dim)")}>高增速 · {repos.length}</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "12px 16px 16px", display: "grid", gap: 11, alignContent: "start" }}>
            {intelData === null && <div style={{ ...mono(11), padding: "16px 0", textAlign: "center" }}>正在加载雷达…</div>}
            {intelData !== null && repos.length === 0 && <div style={{ ...mono(11), padding: "16px 0", textAlign: "center" }}>暂无仓库</div>}
            {repos.map((rp, i) => { const speed = typeof rp.stars_per_day === "number" ? rp.stars_per_day : 0; const sg = repoSignal(speed); const name = rp.repo_full_name || "(未知仓库)"; const summary = rp.summary_zh || rp.display_description || rp.description || ""; const lang = rp.language || (Array.isArray(rp.display_topics) && rp.display_topics[0]) || ""; const href = rp.url; return (
              <div key={rp.repo_full_name || i} onClick={() => { if (href) window.open(href, "_blank", "noopener,noreferrer"); }} className="cx-intel" style={{ border: "1px solid var(--border-soft)", background: "var(--panel-2)", borderRadius: 11, padding: 12, display: "grid", gap: 6, cursor: href ? "pointer" : "default" }}><div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}><b style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</b><span style={{ flex: "none", font: "600 9px 'IBM Plex Mono',monospace", color: sg.fg, background: sg.bg, borderRadius: 999, padding: "2px 8px" }}>{sg.sig}</span></div>{summary && <p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{summary}</p>}<div style={{ display: "flex", gap: 12, font: "500 10px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>{lang && <span>{lang}</span>}<span>★ {compactNum(rp.stars)}</span>{speed > 0 && <span style={{ color: "var(--good)" }}>▲ {Math.round(speed)}/天</span>}</div></div>
            ); })}
          </div>
        </div>
        <div style={col}>
          <div style={headBar}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>来源 & 关注项</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "14px 16px" }}>
            <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".12em", color: "var(--text-mute)", marginBottom: 9 }}>已接入来源 · {sources.length}</div>
            <div style={{ display: "grid", gap: 7, marginBottom: 16 }}>
              {srcGroups.length === 0 && <div style={mono(10.5)}>{intelData === null ? "加载中…" : "暂无来源"}</div>}
              {srcGroups.map((sc) => (<div key={sc.key} style={row(9)}><span style={{ width: 6, height: 6, borderRadius: "50%", background: sc.dot, flex: "none" }} /><span style={{ font: "500 12px 'Space Grotesk',sans-serif", color: "var(--text-dim)", flex: 1 }}>{sc.name}</span><span style={mono(10)}>{sc.count}</span></div>))}
            </div>
            <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".12em", color: "var(--text-mute)", marginBottom: 9 }}>关注项 · {targets.length}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {targets.length === 0 && <span style={mono(10.5)}>{intelData === null ? "加载中…" : "暂无关注项"}</span>}
              {targets.map((tg) => (<span key={tg.id || tg.label} style={{ font: "500 11px 'Space Grotesk',sans-serif", color: tg.enabled ? "var(--text-dim)" : "var(--text-mute)", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 999, padding: "5px 10px" }}>{tg.label || tg.query}</span>))}
            </div>
          </div>
        </div>
      </div>
      {selectedId && <IntelDetail id={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  );
}

// ============ NOTES（Q6 完整记事本）============
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = rej; r.readAsDataURL(file); });
}
function inlineMd(s: string, kbase: number): ReactNode[] {
  const parts: ReactNode[] = []; let last = 0; let key = kbase; let m: RegExpExecArray | null;
  const re = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`/g;
  while ((m = re.exec(s))) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    if (m[1]) parts.push(<a key={key++} href={m[2]} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>{m[1]}</a>);
    else if (m[3]) parts.push(<b key={key++} style={{ color: "var(--text)" }}>{m[3]}</b>);
    else parts.push(<code key={key++} style={{ font: "500 12px 'IBM Plex Mono'", color: "var(--accent)", background: "var(--panel-2)", padding: "1px 5px", borderRadius: 4 }}>{m[4]}</code>);
    last = re.lastIndex;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}
function renderMd(md: string): ReactNode {
  return md.split("\n").map((ln, i) => {
    const img = ln.match(/^!\[([^\]]*)\]\(([^)]+)\)\s*$/);
    if (img) return <img key={i} src={img[2]} alt={img[1]} style={{ maxWidth: "100%", borderRadius: 9, margin: "8px 0", border: "1px solid var(--border)" }} />;
    if (/^#{1,3}\s/.test(ln)) { const lvl = (ln.match(/^#+/) || ["#"])[0].length; const txt = ln.replace(/^#+\s/, ""); return <div key={i} style={{ font: `700 ${21 - lvl * 2}px 'Space Grotesk',sans-serif`, color: "var(--text)", margin: "12px 0 5px" }}>{inlineMd(txt, i * 50)}</div>; }
    if (/^[-*]\s/.test(ln)) return <div key={i} style={{ display: "flex", gap: 8, margin: "3px 0" }}><span style={{ color: "var(--accent)" }}>•</span><span style={{ font: "400 13px/1.65 'Space Grotesk'", color: "var(--text-dim)" }}>{inlineMd(ln.replace(/^[-*]\s/, ""), i * 50)}</span></div>;
    if (!ln.trim()) return <div key={i} style={{ height: 9 }} />;
    return <p key={i} style={{ margin: "4px 0", font: "400 13px/1.72 'Space Grotesk',sans-serif", color: "var(--text-dim)", whiteSpace: "pre-wrap" }}>{inlineMd(ln, i * 50)}</p>;
  });
}

function hostOf(url: string): string { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url.slice(0, 30); } }
function srcIcon(s: NbSource): string {
  if (s.source_url) return "🔗";
  if (s.source === "attachment_import") return "📎";
  if (s.source === "source_text") return "✍";
  return "📄";
}

// ============ NOTES = open-notebook 工作区（来源 → RAG 对话 → 工作室）============
// 编辑抽屉：从右侧滑出，复用完整 Markdown 编辑器（标题/工具栏/预览/附件/标签/删除）。
function NoteEditorDrawer({ noteId, notebook, onClose, onSaved }: { noteId: string | null; notebook: string; onClose: () => void; onSaved: () => void }) {
  const [selId, setSelId] = useState<string | null>(noteId);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [pinned, setPinned] = useState(false);
  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyMsg, setBusyMsg] = useState("");
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const attachRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (noteId) getNote(noteId).then((r) => { if (r?.note) { const n = r.note; setSelId(n.id || noteId); setTitle(n.title || ""); setContent(n.content || ""); setTags((n.tags || []).join(", ")); setPinned(!!n.pinned); } }).catch(() => {});
    else setTimeout(() => taRef.current?.focus(), 60);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noteId]);

  async function save(): Promise<string | null> {
    if (saving || (!title.trim() && !content.trim())) return selId;
    setSaving(true);
    const payload = { title, content, tags: tags.split(/[,，]/).map((s) => s.trim()).filter(Boolean), pinned, project_name: notebook };
    try {
      let id = selId;
      if (selId) await updateNote(selId, payload);
      else { const r = await createNote(payload); id = r?.note?.id || null; setSelId(id); }
      setBusyMsg("已保存"); setTimeout(() => setBusyMsg(""), 1400); onSaved();
      return id;
    } catch { setBusyMsg("保存失败"); setTimeout(() => setBusyMsg(""), 1600); return selId; }
    finally { setSaving(false); }
  }
  async function del() { if (!selId) { onClose(); return; } if (!window.confirm("删除这条？")) return; try { await deleteNote(selId); onSaved(); onClose(); } catch { /* ignore */ } }
  function insert(text: string) {
    const ta = taRef.current;
    if (!ta) { setContent((c) => c + text); return; }
    const s = ta.selectionStart, e = ta.selectionEnd;
    setContent(content.slice(0, s) + text + content.slice(e));
    setTimeout(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = s + text.length; }, 10);
  }
  async function attachImage(file: File) {
    setBusyMsg("上传中…");
    try {
      let nid = selId; if (!nid) nid = await save();
      const dataUrl = await fileToDataUrl(file);
      const r = await importNoteAttachment({ file_name: file.name, mime_type: file.type, data_base64: dataUrl, note_id: nid || undefined, notebook });
      const aid = r?.attachment?.id;
      if (aid) insert(`\n${(file.type || "").startsWith("image/") ? "!" : ""}[${file.name}](${attachmentUrl(aid)})\n`);
      setBusyMsg("已插入"); setTimeout(() => setBusyMsg(""), 1300); onSaved();
    } catch { setBusyMsg("上传失败"); setTimeout(() => setBusyMsg(""), 1600); }
  }
  function onPaste(e: React.ClipboardEvent) { const items = e.clipboardData?.items; if (!items) return; for (const it of Array.from(items)) if (it.type.startsWith("image/")) { const f = it.getAsFile(); if (f) { e.preventDefault(); attachImage(f); return; } } }
  const tool = (label: string, onClick: () => void, t?: string) => (<button onClick={onClick} title={t || label} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 7, padding: "5px 9px", font: "600 11px 'Space Grotesk'", minWidth: 30 }}>{label}</button>);

  return (
    <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,.42)", zIndex: 40, display: "flex", justifyContent: "flex-end", animation: "cxRise .2s ease both" }}>
      <div onClick={(e) => e.stopPropagation()} className="cx-page" style={{ width: "min(620px,92%)", height: "100%", ...panel, borderRadius: 0, padding: 0, display: "grid", gridTemplateRows: "auto auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden", boxShadow: "var(--shadow)" }}>
        <div style={{ ...row(10), padding: "12px 16px", borderBottom: "1px solid var(--border-soft)" }}>
          <button onClick={onClose} title="关闭" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 7, width: 30, height: 30, fontSize: 15 }}>✕</button>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="标题…" style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "var(--text)", font: "600 17px 'Space Grotesk',sans-serif" }} />
          <button onClick={() => setPinned((v) => !v)} title="置顶" style={{ border: "1px solid var(--border)", background: pinned ? "var(--accent-soft)" : "var(--panel-2)", cursor: "pointer", borderRadius: 7, width: 30, height: 30, fontSize: 13 }}>📌</button>
          <button onClick={del} title="删除" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--bad)", cursor: "pointer", borderRadius: 7, width: 30, height: 30, display: "grid", placeContent: "center" }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" /></svg></button>
          <button onClick={save} disabled={saving} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "7px 15px", font: "600 12px 'Space Grotesk'", opacity: saving ? 0.6 : 1 }}>{saving ? "保存中" : "保存"}</button>
        </div>
        <div style={{ ...row(7), padding: "8px 14px", borderBottom: "1px solid var(--border-soft)", flexWrap: "wrap" }}>
          {tool("B", () => insert("**粗体**"), "加粗")}{tool("H", () => insert("\n## 小标题\n"), "标题")}{tool("•", () => insert("\n- 列表项\n"), "列表")}{tool("链接", () => insert("[文字](https://)"))}{tool("🖼 图片", () => fileRef.current?.click(), "插入图片")}{tool("📎 附件", () => attachRef.current?.click(), "插入附件")}
          <span style={flex1} />
          <button onClick={() => setPreview((v) => !v)} style={{ border: "1px solid var(--border)", background: preview ? "var(--accent-soft)" : "var(--panel-2)", color: preview ? "var(--accent)" : "var(--text-dim)", cursor: "pointer", borderRadius: 7, padding: "5px 11px", font: "600 11px 'Space Grotesk'" }}>{preview ? "编辑" : "预览"}</button>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) attachImage(f); e.currentTarget.value = ""; }} />
          <input ref={attachRef} type="file" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) attachImage(f); e.currentTarget.value = ""; }} />
        </div>
        {preview
          ? <div style={{ overflowY: "auto", minHeight: 0, padding: "16px 20px" }}>{content.trim() ? renderMd(content) : <div style={{ ...mono(11), padding: "20px 0", textAlign: "center" }}>无内容</div>}</div>
          : <textarea ref={taRef} value={content} onChange={(e) => setContent(e.target.value)} onPaste={onPaste} placeholder="正文支持 Markdown，粘贴图片自动上传…" style={{ margin: 0, minHeight: 0, resize: "none", background: "transparent", border: 0, outline: "none", padding: "16px 20px", color: "var(--text)", font: "400 13.5px/1.75 'Space Grotesk',sans-serif" }} />}
        <div style={{ ...row(10), padding: "9px 16px", borderTop: "1px solid var(--border-soft)" }}>
          <span style={mono(10, "var(--text-mute)")}>标签</span>
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="逗号分隔" style={{ flex: 1, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 10px", color: "var(--text)", font: "400 11.5px 'Space Grotesk'", outline: "none" }} />
          {busyMsg && <span style={mono(10.5, "var(--good)")}>{busyMsg}</span>}
        </div>
      </div>
    </div>
  );
}

type NbMsg = { role: "user" | "assistant"; content: string; citations?: NbCitation[]; grounded?: boolean };
const STUDIO_ICON: Record<string, string> = { overview: "🗺", faq: "❓", timeline: "🕓", briefing: "📰", study_guide: "🎓" };

function Notes({ openId }: { openId: string | null }) {
  const [notebooks, setNotebooks] = useState<NotebookMeta[]>([]);
  const [nb, setNb] = useState("");                                  // 当前笔记本（"" = 全部）
  const [ws, setWs] = useState<{ sources: NbSource[]; notes: NbSource[]; templates: StudioTpl[] }>({ sources: [], notes: [], templates: [] });
  const [sel, setSel] = useState<Set<string>>(new Set());            // 参与对话的来源（空 = 全部）
  const [msgs, setMsgs] = useState<NbMsg[]>([]);
  const [input, setInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [studioBusy, setStudioBusy] = useState("");
  const [editId, setEditId] = useState<string | null | undefined>(undefined);  // undefined=关 / null=新建 / id=编辑
  const [textModal, setTextModal] = useState(false);
  const [tsTitle, setTsTitle] = useState(""); const [tsBody, setTsBody] = useState("");
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const flash = (m: string) => { setToast(m); setTimeout(() => setToast(""), 1700); };
  const loadNb = () => getNotebooks().then((d) => setNotebooks(d.notebooks || [])).catch(() => {});
  const loadWs = (name = nb) => getNotebookWorkspace(name).then((d) => setWs({ sources: d.sources || [], notes: d.notes || [], templates: d.studio_templates || [] })).catch(() => {});
  useEffect(() => { loadNb(); }, []);
  useEffect(() => { loadWs(nb); setSel(new Set()); setMsgs([]); /* 切笔记本重置对话 */ /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [nb]);
  useEffect(() => { if (openId) setEditId(openId); }, [openId]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, chatBusy]);

  function refresh() { loadWs(); loadNb(); }
  function toggleSel(id: string) { setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }); }

  async function ask(q?: string) {
    const question = (q ?? input).trim();
    if (!question || chatBusy) return;
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setInput(""); setChatBusy(true);
    try {
      const ids = [...sel];
      const hist = msgs.slice(-4).map((m) => ({ role: m.role, content: m.content }));
      const r = await notebookChat(nb, question, ids, hist);
      setMsgs((m) => [...m, { role: "assistant", content: r.answer || "（无返回）", citations: r.citations || [], grounded: r.grounded }]);
    } catch (e) { setMsgs((m) => [...m, { role: "assistant", content: "出错了：" + String((e as Error)?.message || e) }]); }
    finally { setChatBusy(false); }
  }
  async function addUrl() {
    const url = window.prompt("粘贴链接，会抓取正文作为来源加入本笔记本：");
    if (!url || !url.trim()) return;
    flash("抓取中…");
    try { await importNoteUrl(url.trim(), nb); flash("已加入来源"); refresh(); } catch { flash("导入失败"); }
  }
  async function addFile(file: File) {
    flash("上传中…");
    try { await importNoteAttachment({ file_name: file.name, mime_type: file.type, data_base64: await fileToDataUrl(file), notebook: nb }); flash("已加入来源"); refresh(); }
    catch { flash("上传失败"); }
  }
  async function saveTextSource() {
    if (!tsBody.trim()) return;
    flash("保存中…");
    try { await addNotebookText(nb, tsTitle.trim(), tsBody); setTextModal(false); setTsTitle(""); setTsBody(""); flash("已加入来源"); refresh(); }
    catch { flash("保存失败"); }
  }
  async function runStudio(kind: string) {
    if (!ws.sources.length) { flash("先加来源"); return; }
    setStudioBusy(kind);
    try { const r = await notebookStudio(nb, kind, [...sel]); flash("已生成笔记"); loadWs(); if (r?.note?.id) setEditId(r.note.id); }
    catch { flash("生成失败"); }
    finally { setStudioBusy(""); }
  }

  const groundLabel = sel.size ? `基于选中的 ${sel.size} 个来源` : ws.sources.length ? `基于全部 ${ws.sources.length} 个来源` : "尚无来源";
  const suggestions = ["概括这些来源的核心要点", "列出关键事实和数据", "有哪些待办或下一步", "生成一组常见问答"];
  const nbName = nb || "全部记事";

  return (
    <div className="cx-page" style={{ position: "relative", height: "100%", display: "grid", gridTemplateColumns: "278px minmax(0,1fr) 290px", gap: 14, padding: 16, minHeight: 0 }}>
      {/* ── 左：来源 ── */}
      <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto auto auto minmax(0,1fr)", minHeight: 0, overflow: "hidden" }}>
        <div style={{ ...row(8), padding: "13px 14px 9px" }}><span style={lbl}>笔记本 · NOTEBOOK</span><span style={flex1} /><span style={mono(9.5, "var(--accent)")}>{ws.sources.length} 来源</span></div>
        {/* 笔记本切换 */}
        <div style={{ ...row(6), padding: "0 12px 10px", overflowX: "auto", flexWrap: "nowrap" }}>
          {[{ name: "", note_count: 0, source_count: 0 } as NotebookMeta, ...notebooks.filter((n) => n.name && n.name !== "未归档"), ...notebooks.filter((n) => n.name === "未归档")].map((n) => { const on = nb === n.name; const label = n.name || "全部"; return (
            <button key={label} onClick={() => setNb(n.name)} className="cx-chip" style={{ flex: "none", border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`, background: on ? "var(--accent-soft)" : "var(--panel-2)", color: on ? "var(--accent)" : "var(--text-dim)", cursor: "pointer", borderRadius: 999, padding: "5px 12px", font: "600 11px 'Space Grotesk'" }}>{label}</button>
          ); })}
          <button onClick={() => { const name = window.prompt("新建笔记本名称："); if (name && name.trim()) { setNb(name.trim()); flash("已切到「" + name.trim() + "」，加来源即生效"); } }} title="新建笔记本" style={{ flex: "none", border: "1px dashed var(--border)", background: "transparent", color: "var(--text-mute)", cursor: "pointer", borderRadius: 999, padding: "5px 11px", font: "700 12px 'Space Grotesk'" }}>＋</button>
        </div>
        {/* 添加来源 */}
        <div style={{ ...row(6), padding: "0 12px 10px" }}>
          <button onClick={addUrl} className="cx-chip" style={{ flex: 1, border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "7px 4px", font: "600 11px 'Space Grotesk'" }}>🔗 链接</button>
          <button onClick={() => fileRef.current?.click()} className="cx-chip" style={{ flex: 1, border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "7px 4px", font: "600 11px 'Space Grotesk'" }}>📎 文件</button>
          <button onClick={() => setTextModal(true)} className="cx-chip" style={{ flex: 1, border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "7px 4px", font: "600 11px 'Space Grotesk'" }}>✍ 文本</button>
          <input ref={fileRef} type="file" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) addFile(f); e.currentTarget.value = ""; }} />
        </div>
        {/* 来源列表 */}
        <div style={{ overflowY: "auto", minHeight: 0, padding: "0 10px 12px", display: "grid", gap: 7, alignContent: "start" }}>
          {ws.sources.length === 0 && <div style={{ ...mono(10.5), padding: "24px 8px", textAlign: "center", lineHeight: 1.7 }}>这个笔记本还没有来源。<br />用上面的 链接 / 文件 / 文本 添加，<br />然后就能对它们提问、生成笔记。</div>}
          {ws.sources.map((s) => { const on = sel.has(s.id); return (
            <div key={s.id} className="cx-row" style={{ ...row(8), background: on ? "var(--accent-soft)" : "var(--panel-2)", border: `1px solid ${on ? "var(--accent)" : "var(--border-soft)"}`, borderRadius: 10, padding: "9px 10px" }}>
              <button onClick={() => toggleSel(s.id)} title="纳入/移出对话接地" style={{ flex: "none", width: 18, height: 18, borderRadius: 5, border: `1.5px solid ${on ? "var(--accent)" : "var(--border)"}`, background: on ? "var(--accent)" : "transparent", color: "#fff", cursor: "pointer", display: "grid", placeContent: "center", font: "700 11px 'Space Grotesk'", lineHeight: 0 }}>{on ? "✓" : ""}</button>
              <button onClick={() => setEditId(s.id)} style={{ textAlign: "left", flex: 1, minWidth: 0, background: "transparent", border: 0, cursor: "pointer", display: "grid", gap: 2 }}>
                <b style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{srcIcon(s)} {s.title || "未命名"}</b>
                <span style={{ ...mono(8.5), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.source_url ? hostOf(s.source_url) : `${s.chars || 0} 字`} · {s.updated_ts ? fmtAgo(s.updated_ts) + "前" : ""}</span>
              </button>
            </div>
          ); })}
        </div>
      </div>

      {/* ── 中：RAG 对话 ── */}
      <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden", position: "relative" }}>
        <div className="cx-scanline" />
        <div style={{ ...row(10), padding: "13px 16px 11px", borderBottom: "1px solid var(--border-soft)" }}>
          <span style={{ width: 30, height: 30, borderRadius: 9, background: "var(--accent-soft)", border: "1px solid var(--accent-line)", display: "grid", placeContent: "center", flex: "none", fontSize: 15 }}>💬</span>
          <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "700 14px 'Space Grotesk',sans-serif", color: "var(--text)" }}>问「{nbName}」</div><div style={mono(9.5)}>{groundLabel} · 答案逐句标注来源引用</div></div>
          {msgs.length > 0 && <button onClick={() => setMsgs([])} className="cx-chip" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", borderRadius: 7, padding: "5px 10px", ...mono(9.5) }}>清空</button>}
        </div>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "16px 18px", display: "grid", gap: 14, alignContent: "start" }}>
          {msgs.length === 0 && (
            <div style={{ display: "grid", placeContent: "center", gap: 14, textAlign: "center", height: "100%", padding: 20 }}>
              <div style={{ font: "700 16px 'Space Grotesk',sans-serif", color: "var(--text)" }}>对你的来源提问</div>
              <div style={{ font: "400 12.5px/1.7 'Space Grotesk',sans-serif", color: "var(--text-dim)", maxWidth: 360, margin: "0 auto" }}>这是个 NotebookLM 式的研究助手 —— 它只读你加进来的来源，回答时逐句给出 [n] 引用，绝不编造。</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: 420, margin: "4px auto 0" }}>
                {suggestions.map((q) => <button key={q} onClick={() => ask(q)} disabled={!ws.sources.length} className="cx-chip" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: ws.sources.length ? "var(--text-dim)" : "var(--text-mute)", cursor: ws.sources.length ? "pointer" : "default", borderRadius: 999, padding: "7px 13px", font: "500 11.5px 'Space Grotesk'", opacity: ws.sources.length ? 1 : 0.5 }}>{q}</button>)}
              </div>
            </div>
          )}
          {msgs.map((m, i) => m.role === "user" ? (
            <div key={i} style={{ justifySelf: "end", maxWidth: "82%", background: "var(--accent)", color: "#fff", borderRadius: "14px 14px 4px 14px", padding: "9px 14px", font: "500 13px/1.6 'Space Grotesk',sans-serif" }}>{m.content}</div>
          ) : (
            <div key={i} className="cx-feed" style={{ justifySelf: "start", maxWidth: "92%", background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: "14px 14px 14px 4px", padding: "12px 15px" }}>
              <div style={{ ...row(6), marginBottom: 7 }}><span style={{ font: "700 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".12em", color: "var(--accent)" }}>笔记本助手</span>{m.grounded === false && <span style={mono(8.5, "var(--warn)")}>· 无来源</span>}</div>
              <div style={{ font: "400 13px/1.7 'Space Grotesk',sans-serif" }}>{renderMd(m.content)}</div>
              {m.citations && m.citations.length > 0 && (
                <div style={{ marginTop: 10, paddingTop: 9, borderTop: "1px dashed var(--border)", display: "grid", gap: 5 }}>
                  <div style={mono(8.5, "var(--text-mute)")}>引用来源</div>
                  {m.citations.map((c) => (
                    <button key={c.n} onClick={() => setEditId(c.note_id)} className="cx-row" title={c.snippet} style={{ textAlign: "left", ...row(7), background: "var(--panel)", border: "1px solid var(--border-soft)", borderRadius: 8, padding: "6px 9px", cursor: "pointer" }}>
                      <span style={{ flex: "none", width: 17, height: 17, borderRadius: 5, background: "var(--accent-soft)", color: "var(--accent)", display: "grid", placeContent: "center", font: "700 9.5px 'IBM Plex Mono'" }}>{c.n}</span>
                      <span style={{ minWidth: 0, flex: 1 }}><span style={{ font: "600 11px 'Space Grotesk'", color: "var(--text)", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</span><span style={{ ...mono(8.5), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>{c.snippet}</span></span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {chatBusy && <div style={{ justifySelf: "start", ...row(8), background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: "14px 14px 14px 4px", padding: "11px 15px", ...mono(11, "var(--text-dim)") }}><b style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)", display: "inline-block", animation: "cxPulse 1s ease infinite" }} />检索来源、生成中…</div>}
          <div ref={chatEndRef} />
        </div>
        <div style={{ ...row(9), padding: "11px 14px", borderTop: "1px solid var(--border-soft)", background: "var(--panel-3)" }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }} placeholder={ws.sources.length ? `问问「${nbName}」里的来源…` : "先在左侧加来源，再开始提问…"} disabled={!ws.sources.length} style={{ flex: 1, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 14px", color: "var(--text)", font: "500 13px 'Space Grotesk'", outline: "none", opacity: ws.sources.length ? 1 : 0.6 }} />
          <button onClick={() => ask()} disabled={chatBusy || !input.trim()} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: chatBusy || !input.trim() ? "default" : "pointer", borderRadius: 10, padding: "10px 18px", font: "600 12.5px 'Space Grotesk'", opacity: chatBusy || !input.trim() ? 0.5 : 1, flex: "none" }}>发送</button>
        </div>
      </div>

      {/* ── 右：工作室 + 笔记 ── */}
      <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto auto minmax(0,1fr)", minHeight: 0, overflow: "hidden" }}>
        <div style={{ padding: "13px 14px 10px" }}>
          <div style={{ ...row(8) }}><span style={lbl}>工作室 · STUDIO</span><span style={flex1} /></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 9 }}>
            {(ws.templates.length ? ws.templates : [{ id: "overview", label: "文档概览", tag: "" }, { id: "faq", label: "常见问答", tag: "" }, { id: "timeline", label: "时间线", tag: "" }, { id: "briefing", label: "简报文档", tag: "" }, { id: "study_guide", label: "学习指南", tag: "" }]).map((t) => (
              <button key={t.id} onClick={() => runStudio(t.id)} disabled={!!studioBusy || !ws.sources.length} className="cx-chip" style={{ border: "1px solid var(--border)", background: studioBusy === t.id ? "var(--accent-soft)" : "var(--panel-2)", color: "var(--text-dim)", cursor: ws.sources.length ? "pointer" : "default", borderRadius: 9, padding: "9px 6px", font: "600 11px 'Space Grotesk'", opacity: ws.sources.length ? 1 : 0.5, display: "grid", gap: 2, lineHeight: 1.2 }}>
                <span style={{ fontSize: 15 }}>{STUDIO_ICON[t.id] || "✦"}</span>{studioBusy === t.id ? "生成中…" : t.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ ...row(8), padding: "8px 14px 8px", borderTop: "1px solid var(--border-soft)" }}><span style={lbl}>笔记 · NOTES</span><span style={flex1} /><span style={mono(9.5, "var(--text-dim)")}>{ws.notes.length}</span><button onClick={() => setEditId(null)} title="新建笔记" style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", width: 22, height: 22, borderRadius: 6, font: "700 14px 'Space Grotesk'", lineHeight: 0 }}>＋</button></div>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "0 10px 12px", display: "grid", gap: 7, alignContent: "start" }}>
          {ws.notes.length === 0 && <div style={{ ...mono(10), padding: "16px 6px", textAlign: "center", lineHeight: 1.7 }}>还没有笔记。<br />用上面的工作室一键生成，<br />或点 ＋ 手写一条。</div>}
          {ws.notes.map((n) => { const ai = (n.tags || []).includes("AI工作室") || n.source === "ai_studio" || n.source === "ai_transform"; return (
            <button key={n.id} onClick={() => setEditId(n.id)} className="cx-row" style={{ textAlign: "left", background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: 10, padding: "9px 11px", cursor: "pointer", display: "grid", gap: 4 }}>
              <div style={{ ...row(6) }}>{n.pinned && <span style={{ fontSize: 9 }}>📌</span>}{ai && <span style={{ ...mono(8, "var(--accent)"), background: "var(--accent-soft)", borderRadius: 4, padding: "1px 5px" }}>AI</span>}<b style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{n.title || "未命名"}</b></div>
              <p style={{ margin: 0, font: "400 10.5px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{n.excerpt || ""}</p>
            </button>
          ); })}
        </div>
      </div>

      {toast && <div className="cx-pop-in" style={{ position: "absolute", bottom: 22, left: "50%", transform: "translateX(-50%)", background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 999, padding: "8px 18px", font: "600 12px 'Space Grotesk'", color: "var(--text)", boxShadow: "var(--shadow)", zIndex: 50 }}>{toast}</div>}

      {/* 文本来源 modal */}
      {textModal && (
        <div onClick={() => setTextModal(false)} style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,.42)", zIndex: 45, display: "grid", placeContent: "center", animation: "cxRise .18s ease both" }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: "min(560px,90vw)", ...panel, display: "grid", gap: 11 }}>
            <div style={{ ...row(8) }}><span style={{ font: "700 14px 'Space Grotesk'", color: "var(--text)" }}>✍ 粘贴文本作为来源</span><span style={flex1} /><span style={mono(9.5)}>→ {nbName}</span></div>
            <input value={tsTitle} onChange={(e) => setTsTitle(e.target.value)} placeholder="来源标题（可留空自动生成）" style={{ background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: "9px 12px", color: "var(--text)", font: "500 13px 'Space Grotesk'", outline: "none" }} />
            <textarea value={tsBody} onChange={(e) => setTsBody(e.target.value)} placeholder="把要研究的文字粘贴到这里，它会成为一条可被检索、引用的来源…" style={{ minHeight: 200, resize: "vertical", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: "11px 13px", color: "var(--text)", font: "400 13px/1.7 'Space Grotesk'", outline: "none" }} />
            <div style={{ ...row(9) }}><span style={flex1} /><button onClick={() => setTextModal(false)} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "8px 16px", font: "600 12px 'Space Grotesk'" }}>取消</button><button onClick={saveTextSource} disabled={!tsBody.trim()} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: tsBody.trim() ? "pointer" : "default", borderRadius: 8, padding: "8px 18px", font: "600 12px 'Space Grotesk'", opacity: tsBody.trim() ? 1 : 0.5 }}>加入来源</button></div>
          </div>
        </div>
      )}

      {editId !== undefined && <NoteEditorDrawer noteId={editId} notebook={nb} onClose={() => setEditId(undefined)} onSaved={refresh} />}
    </div>
  );
}

// ============ DEVICES / 舰队（F2：本机 + 未来多设备的只读健康状态）============
function metricBar(pct: number | undefined, color: string) {
  const v = typeof pct === "number" ? Math.max(0, Math.min(100, pct)) : 0;
  return <div style={{ height: 4, background: "var(--panel-3)", borderRadius: 3, overflow: "hidden" }}><i style={{ display: "block", height: "100%", width: `${v}%`, background: color, borderRadius: 3, transition: "width .5s" }} /></div>;
}
function DeviceCard({ d, onRemove }: { d: FleetDevice; onRemove: (id: string) => void }) {
  const m = d.metrics || {};
  const health = typeof d.health === "number" ? Math.round(d.health) : null;
  const statusColor = d.status === "异常" ? "var(--bad)" : d.status === "注意" ? "var(--warn)" : "var(--good)";
  const C = 2 * Math.PI * 21;
  return (
    <div className="cx-lift" style={{ ...panel, display: "grid", gap: 12, opacity: d.online ? 1 : 0.62, borderColor: d.is_current ? "var(--accent-line)" : "var(--border)" }}>
      <div style={{ ...row(11) }}>
        <span style={{ width: 40, height: 40, borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--border)", display: "grid", placeContent: "center", flex: "none", color: "var(--accent)" }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M2 20h20" /></svg></span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ ...row(7) }}><b style={{ font: "700 14.5px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.device_name || d.host_name || "Mac"}</b>{d.is_current && <span style={{ ...mono(8.5, "var(--accent)"), background: "var(--accent-soft)", borderRadius: 999, padding: "2px 8px", flex: "none" }}>本机</span>}</div>
          <div style={{ ...mono(9.5), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.host_name || "—"} · {d.model || "Mac"}</div>
        </div>
        <span style={{ ...row(5), flex: "none", font: "600 9.5px 'IBM Plex Mono',monospace", color: d.online ? "var(--good)" : "var(--text-mute)" }}><b style={{ width: 7, height: 7, borderRadius: "50%", background: d.online ? "var(--good)" : "var(--text-mute)", boxShadow: d.online ? "0 0 7px var(--good)" : "none", display: "inline-block", animation: d.online ? "cxBreathe 2.5s ease infinite" : "none" }} />{d.online ? "在线" : `离线 · ${fmtAgo(d.last_seen_ts)}前`}</span>
      </div>
      <div style={{ ...row(14), ...sub, padding: "13px 14px" }}>
        <div style={{ position: "relative", width: 52, height: 52, flex: "none" }}>
          <svg width="52" height="52" viewBox="0 0 52 52" style={{ transform: "rotate(-90deg)" }}><circle cx="26" cy="26" r="21" fill="none" stroke="var(--border)" strokeWidth="5" /><circle cx="26" cy="26" r="21" fill="none" stroke={statusColor} strokeWidth="5" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={health != null ? +(C * (1 - health / 100)).toFixed(1) : C} style={{ transition: "stroke-dashoffset .6s" }} /></svg>
          <div style={{ position: "absolute", inset: 0, display: "grid", placeContent: "center", font: "700 15px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{health ?? "—"}</div>
        </div>
        <div style={{ flex: 1, minWidth: 0, display: "grid", gap: 7 }}>
          <div style={{ ...row(8) }}><span style={mono(9.5)}>系统健康</span><span style={flex1} /><b style={{ font: "600 11px 'Space Grotesk',sans-serif", color: statusColor }}>{d.status || "—"}</b></div>
          {([["CPU", m.cpu_load_pct, "var(--accent)"], ["RAM", m.ram_used_pct, "var(--info)"], ["SSD", m.ssd_used_pct, "var(--warn)"]] as [string, number | undefined, string][]).map(([lab, val, c]) => (
            <div key={lab} style={{ ...row(8) }}><span style={{ ...mono(9), width: 28, flex: "none" }}>{lab}</span><div style={{ flex: 1 }}>{metricBar(val, c)}</div><span style={{ ...mono(9.5, "var(--text-dim)"), width: 34, textAlign: "right", flex: "none" }}>{typeof val === "number" ? Math.round(val) + "%" : "—"}</span></div>
          ))}
        </div>
      </div>
      <div style={{ ...row(10) }}>
        <span style={mono(9.5)}>服务 <b style={{ color: "var(--text)" }}>{d.services?.online ?? "—"}/{d.services?.total ?? "—"}</b></span>
        {typeof m.battery_percent === "number" && <span style={mono(9.5)}>电池 <b style={{ color: "var(--text)" }}>{m.battery_percent}%</b>{m.battery_plugged ? " ⚡" : ""}</span>}
        {typeof m.ssd_free_gb === "number" && <span style={mono(9.5)}>剩余 <b style={{ color: "var(--text)" }}>{m.ssd_free_gb}G</b></span>}
        <span style={flex1} />
        {d.is_current ? <span style={mono(9, "var(--text-mute)")}>终端/状态：本机实时</span> : <button onClick={() => onRemove(d.device_id)} className="cx-chip" style={{ border: "1px solid var(--border)", background: "transparent", color: "var(--bad)", cursor: "pointer", borderRadius: 7, padding: "4px 11px", font: "600 10px 'Space Grotesk'" }}>移除</button>}
      </div>
      {Array.isArray(d.risks) && d.risks.length > 0 && (
        <div style={{ display: "grid", gap: 5 }}>
          {d.risks.slice(0, 2).map((r, i) => <div key={i} style={{ ...row(7), ...sub, padding: "7px 10px" }}><span style={{ width: 3, height: 18, borderRadius: 3, background: r.level === "异常" ? "var(--bad)" : "var(--warn)", flex: "none" }} /><span style={{ font: "500 10.5px/1.4 'Space Grotesk',sans-serif", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.title || r.detail}</span></div>)}
        </div>
      )}
    </div>
  );
}
function Devices() {
  const [devices, setDevices] = useState<FleetDevice[]>([]);
  const [loaded, setLoaded] = useState(false);
  const load = () => getDevices().then((d) => { setDevices(d.devices || []); setLoaded(true); }).catch(() => setLoaded(true));
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);
  async function remove(id: string) { if (!window.confirm("从舰队移除这台设备？它下次心跳会重新登记。")) return; await deleteDevice(id).catch(() => { /* ignore */ }); load(); }
  const online = devices.filter((d) => d.online).length;
  return (
    <div className="cx-page" style={{ height: "100%", overflowY: "auto", padding: 18, display: "grid", gap: 16, alignContent: "start" }}>
      <div style={{ ...panel, ...row(14) }}>
        <span style={{ width: 44, height: 44, borderRadius: 12, background: "var(--accent-soft)", border: "1px solid var(--accent-line)", display: "grid", placeContent: "center", flex: "none", color: "var(--accent)" }}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M2 20h20M9 16v4M15 16v4" /></svg></span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ font: "700 16px 'Space Grotesk',sans-serif", color: "var(--text)" }}>设备舰队</div>
          <div style={{ font: "400 12px/1.6 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>{devices.length} 台已登记 · {online} 在线。这里看你每台 Mac 的<b style={{ color: "var(--text)" }}>只读健康状态</b>；终端和实时操作始终连<b style={{ color: "var(--accent)" }}>本机</b>。</div>
        </div>
        <span style={{ ...row(5), flex: "none", ...mono(9.5, "var(--good)") }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 2.4s ease infinite" }} />每 5 秒刷新</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(372px,1fr))", gap: 14 }}>
        {!loaded && <div style={{ ...panel, ...mono(11), textAlign: "center", padding: 30 }}>登记本机中…</div>}
        {devices.map((d) => <DeviceCard key={d.device_id} d={d} onRemove={remove} />)}
        <div style={{ ...panel, border: "1px dashed var(--border)", display: "grid", placeContent: "center", textAlign: "center", gap: 9, minHeight: 230, color: "var(--text-mute)" }}>
          <div style={{ fontSize: 26, fontWeight: 300 }}>＋</div>
          <div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>添加更多 Mac</div>
          <div style={{ font: "400 11px/1.7 'Space Grotesk',sans-serif", maxWidth: 250, margin: "0 auto" }}>在另一台 Mac 装上 LeoJarvis 即自动登记进舰队。多设备同步（记事跟人走、状态各机独立）见升级计划 <b style={{ color: "var(--accent)" }}>F1 / F2</b>。</div>
        </div>
      </div>
    </div>
  );
}

// ============ SETTINGS（P6 真实读写）============
type SetTab = "appearance" | "models" | "sources" | "notify" | "amap" | "system";
function Settings({ theme, setTheme, scan, toggleScan }: { theme: Theme; setTheme: (t: Theme) => void; scan: boolean; toggleScan: () => void }) {
  const [tab, setTab] = useState<SetTab>("appearance");
  const [data, setData] = useState<SettingsData | null>(null);
  const [amap, setAmap] = useState<AmapConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(0);
  const load = () => { getSettings().then(setData).catch(() => setData({})); };
  useEffect(() => { load(); getAmapConfig().then(setAmap).catch(() => {}); }, []);

  async function persist(patch: SettingsData) {
    setSaving(true);
    try { await patchSettings(patch); setData((d) => ({ ...(d || {}), ...patch })); setSavedAt(Date.now()); }
    catch { /* ignore */ } finally { setSaving(false); }
  }

  const tabMeta: [SetTab, string, string][] = [["appearance", "外观与动效", "APPEARANCE"], ["models", "模型路由", "MODELS"], ["sources", "情报源", "SOURCES"], ["notify", "通知", "NOTIFY"], ["amap", "高德地图", "AMAP"], ["system", "系统与守卫", "SYSTEM"]];
  const h2 = (t: string, d: string) => (<div style={{ marginBottom: 22 }}><h2 style={{ margin: 0, font: "600 20px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{t}</h2><p style={{ margin: "6px 0 0", font: "400 13px/1.6 'Space Grotesk',sans-serif", color: "var(--text-dim)", maxWidth: 560 }}>{d}</p></div>);
  const Switch = ({ on, onClick }: { on: boolean; onClick: () => void }) => (
    <button onClick={onClick} style={{ width: 40, height: 23, border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`, borderRadius: 999, background: on ? "var(--accent)" : "var(--panel-2)", position: "relative", cursor: "pointer", flex: "none" }}><i style={{ position: "absolute", top: 2, left: on ? 18 : 2, width: 16, height: 16, borderRadius: "50%", background: on ? "#fff" : "var(--text-mute)", transition: "left .18s" }} /></button>
  );
  const card: CSSProperties = { ...sub, padding: 16 };
  const notifications = (data?.notifications && typeof data.notifications === "object") ? data.notifications as Record<string, unknown> : {};
  const system = (data?.system && typeof data.system === "object") ? data.system as Record<string, unknown> : {};

  return (
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateColumns: "208px minmax(0,1fr)", gap: 14, padding: 16, minHeight: 0 }}>
      <div style={{ ...panel, padding: 12, display: "grid", gap: 3, alignContent: "start" }}>
        <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)", padding: "8px 10px 10px" }}>设置台 · CONSOLE</div>
        {tabMeta.map(([id, label, en]) => (
          <button key={id} onClick={() => setTab(id)} style={{ textAlign: "left", border: 0, cursor: "pointer", ...row(10), padding: "10px 11px", borderRadius: 10, background: tab === id ? "var(--panel-2)" : "transparent" }}><span style={{ width: 3, height: 15, borderRadius: 3, background: tab === id ? "var(--accent)" : "transparent", flex: "none" }} /><div style={{ minWidth: 0 }}><div style={{ font: "600 12.5px 'Space Grotesk',sans-serif", color: tab === id ? "var(--text)" : "var(--text-dim)", whiteSpace: "nowrap" }}>{label}</div><div style={{ font: "500 8.5px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--text-mute)", whiteSpace: "nowrap" }}>{en}</div></div></button>
        ))}
        {savedAt > 0 && <div style={{ ...mono(9.5, "var(--good)"), padding: "10px 11px" }}>{saving ? "保存中…" : "✓ 已保存"}</div>}
      </div>

      <div style={{ ...panel, overflowY: "auto", minHeight: 0, padding: "24px 26px" }}>
        {tab === "appearance" && (<>
          {h2("外观与动效", "深色 / 浅色双主题，酒红冷光强调色。扫描线氛围可关。")}
          <div style={{ display: "grid", gap: 14, maxWidth: 620 }}>
            <div style={card}><div style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)", marginBottom: 12 }}>主题模式</div><div style={{ display: "flex", gap: 10 }}>{(["dark", "light"] as Theme[]).map((m) => (<button key={m} onClick={() => setTheme(m)} style={{ flex: 1, cursor: "pointer", border: `1px solid ${theme === m ? "var(--accent)" : "var(--border)"}`, background: theme === m ? "var(--accent-soft)" : "var(--panel)", color: theme === m ? "var(--accent)" : "var(--text-dim)", borderRadius: 10, padding: "12px 0", font: "600 13px 'Space Grotesk'" }}>{m === "dark" ? "🌙 深色" : "☀ 浅色"}</button>))}</div></div>
            <div style={{ ...card, ...row(14) }}><div style={{ flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)" }}>强调色</div><div style={{ font: "400 11px 'Space Grotesk'", color: "var(--text-mute)", marginTop: 2 }}>酒红 burgundy（已应用全局）</div></div><span style={{ width: 30, height: 30, borderRadius: 9, background: "var(--accent)", boxShadow: "0 0 0 2px var(--panel),0 0 0 4px var(--accent)" }} /></div>
            <div style={{ ...card, ...row(14) }}><div style={{ flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)" }}>扫描线氛围</div><div style={{ font: "400 11px 'Space Grotesk'", color: "var(--text-mute)", marginTop: 2 }}>顶部冷光扫描（已收窄变慢）</div></div><Switch on={scan} onClick={toggleScan} /></div>
          </div>
        </>)}

        {tab === "models" && (<>
          {h2("模型路由", "全部 LLM 已切到 DeepSeek。首选失败自动回退到备选。")}
          <div style={{ display: "grid", gap: 12, maxWidth: 620 }}>
            {[["首选 · 中枢/判断/翻译", "deepseek-v4-flash", "已生效"], ["备选 · 自动回退", "deepseek-v4-pro", "待命"]].map(([role, model, st]) => (
              <div key={model} style={{ ...card, display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "center" }}>
                <div><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{role}</div><div style={{ font: "500 12px 'IBM Plex Mono',monospace", color: "var(--accent)", marginTop: 3 }}>{model}</div><div style={{ ...mono(9.5), marginTop: 2 }}>https://api.deepseek.com</div></div>
                <span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: st === "已生效" ? "var(--good)" : "var(--text-dim)", background: st === "已生效" ? "rgba(54,211,154,.12)" : "var(--panel)", borderRadius: 999, padding: "5px 10px" }}>{st}</span>
              </div>
            ))}
            <div style={{ ...mono(10.5), lineHeight: 1.7 }}>嵌入：本机 hash 向量（已移除 ollama 依赖）。密钥存 config/models.toml，不进 Git。</div>
          </div>
        </>)}

        {tab === "sources" && (<>
          {h2("情报源", "RSS / 网页变化 / GitHub 雷达 / X 监控。下方为当前真实配置。")}
          <div style={{ display: "grid", gap: 12, maxWidth: 620 }}>
            {data === null ? <div style={mono(11)}>读取中…</div> : (<>
              <div style={card}><div style={{ ...row(8), marginBottom: 8 }}><span style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>RSS</span><span style={flex1} /><span style={mono(10)}>{(() => { const r = data.rss as Record<string, unknown> | undefined; const f = r?.feeds; return Array.isArray(f) ? `${f.length} 源` : "config/sources.toml"; })()}</span></div><div style={{ ...mono(10.5), lineHeight: 1.6 }}>基线 36 源（AI科技 / 财经 / 军事 / 中文科技…），可在 config/sources.toml 增删。</div></div>
              <div style={card}><div style={{ ...row(8) }}><span style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>X / Twitter 监控</span><span style={flex1} /><span style={mono(10)}>{(() => { const x = data.x_monitor as Record<string, unknown> | undefined; const h = x?.handles; return Array.isArray(h) ? `${h.length} 关注` : "未配置"; })()}</span></div></div>
              <div style={{ ...mono(10.5) }}>情报扫描频率：config/settings.toml [intelligence].scan_minutes</div>
            </>)}
          </div>
        </>)}

        {tab === "notify" && (<>
          {h2("通知", "应用未读徽标与提醒。开关即时保存到本机 user_settings（不进 Git）。")}
          <div style={{ display: "grid", gap: 10, maxWidth: 620 }}>
            {data === null && <div style={mono(11)}>读取中…</div>}
            {data !== null && Object.keys(notifications).length === 0 && <div style={mono(11)}>暂无可配置通知项。</div>}
            {Object.entries(notifications).map(([k, v]) => (
              <div key={k} style={{ ...card, ...row(13) }}><div style={{ flex: 1, minWidth: 0 }}><div style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>{k}</div></div>{typeof v === "boolean" ? <Switch on={v} onClick={() => persist({ notifications: { ...notifications, [k]: !v } })} /> : <span style={mono(10.5, "var(--text-dim)")}>{String(v)}</span>}</div>
            ))}
          </div>
        </>)}

        {tab === "amap" && (<>
          {h2("高德地图", "地理编码 / POI / 天气 / 路线，自然语言可直接调用；首页右下角小地图实时渲染。")}
          <div style={{ display: "grid", gap: 12, maxWidth: 620 }}>
            <div style={{ ...card, ...row(13) }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: amap?.configured ? "var(--good)" : "var(--text-mute)", flex: "none" }} /><div style={{ flex: 1 }}><div style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>Web 服务 + JS API</div><div style={mono(10)}>{amap?.configured ? "key 已配置 · 已生效" : "未配置 key"}</div></div><span style={{ font: "600 10px 'IBM Plex Mono'", color: amap?.configured ? "var(--good)" : "var(--text-dim)" }}>{amap?.configured ? "在线" : "离线"}</span></div>
            <div style={{ ...card }}><div style={{ ...row(8), marginBottom: 6 }}><span style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>默认城市</span><span style={flex1} /><span style={mono(10, "var(--accent)")}>{amap?.home_city || "—"}</span></div><div style={{ ...mono(10) }}>坐标 {amap?.center || "—"}（config/settings.toml [amap].home_city）</div></div>
            <div style={{ ...mono(10.5), lineHeight: 1.7 }}>试试对中枢说：「北京今天天气」「附近的咖啡」「北京站到北京西站怎么走」。</div>
          </div>
        </>)}

        {tab === "system" && (<>
          {h2("系统与守卫", "后台巡检与告警阈值。低风险只读自动执行，重启等高风险需确认。")}
          <div style={{ display: "grid", gap: 10, maxWidth: 620 }}>
            {data === null && <div style={mono(11)}>读取中…</div>}
            {data !== null && Object.keys(system).length === 0 && <div style={mono(11)}>system 段为空，阈值在 config/settings.toml [guard] / [schedule]。</div>}
            {Object.entries(system).map(([k, v]) => (
              <div key={k} style={{ ...card, ...row(13) }}><div style={{ flex: 1, minWidth: 0 }}><div style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>{k}</div></div>{typeof v === "boolean" ? <Switch on={v} onClick={() => persist({ system: { ...system, [k]: !v } })} /> : <span style={mono(10.5, "var(--text-dim)")}>{String(v)}</span>}</div>
            ))}
            <div style={{ ...mono(10.5), lineHeight: 1.7 }}>本机服务：仅保留 LeoJarvis（已清理 ollama / leoapi 等死项）。</div>
          </div>
        </>)}
      </div>
    </div>
  );
}
