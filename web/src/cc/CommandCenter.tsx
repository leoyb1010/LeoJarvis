import { useEffect, useRef, useState, lazy, Suspense, type CSSProperties, type ReactNode } from "react";
// xterm 较重，只有打开终端面板时才懒加载（不进首屏主 bundle）。
const PtyTerminal = lazy(() => import("./PtyTerminal"));
import {
  getCliAgents, getCliCommands, getCliSessions, runCliAgent, stopCliSession, clearFinishedSessions, openApp, fmtAgo,
  type CliCommand,
  getVitals, getServices, getSystemOverview, getBriefing, getNotes, getNotifications,
  agentChatStream, approveAction, getIntelligence, getBriefingItem, translateBriefingItem, subscribeNotify,
  getAmapConfig, getAmapWeather, getSettings, patchSettings,
  getNote, createNote, updateNote, deleteNote, importNoteUrl, importNoteAttachment, attachmentUrl, getHoroscope,
  getNotebooks, getNotebookWorkspace, addNotebookText, notebookChat, notebookStudio,
  type NbSource, type NbCitation, type StudioTpl, type NotebookMeta,
  getDevices, deleteDevice, type FleetDevice,
  getInbox, rebuildInbox, setInboxState, getWrapup, getAgentRuns,
  getEmailTriage, type EmailTriage,
  getScheduledTasks, createScheduledTask, setScheduledTaskStatus, runScheduledTask, type ScheduledTask,
  getAssistantConfig, patchAssistantConfig, runCheckin, type AssistantConfig,
  getSkills, setSkillStatus, importSkill, type Skill,
  getMcpStatus, patchMcpSettings, type McpStatus,
  getSchedule, createSchedule, scheduleDone, deleteSchedule, getCalDavStatus, type ScheduleItem, type CalDavStatus,
  researchReport,
  type CliAgent, type CliSession, type ExternalAgent, type Vitals, type Service, type SystemOverview,
  type Briefing, type BriefItem, type PersonalNote, type NotifApp, type ChatMsg, type ChatStep, type PendingAction, type ChatReply,
  type Intelligence, type IntelRepo, type IntelSource, type IntelTarget, type BriefDetailItem,
  type AmapConfig, type AmapWeather, type Settings as SettingsData, type Horoscope,
  type InboxTask, type WrapUp, type AgentRunsOverview,
} from "./live";
import { SENSE_CHANNELS, ingestSensed, loadSenseState, saveSenseStatus, type SenseChannel, type SenseResult, type SenseSaved } from "./sensing";
import { Drawer, Modal, Popover, Z } from "./Overlay";
import { briefingMainFeed, pickBriefingLeads } from "../briefingOrder";
import { useWhisperRecorder } from "../useWhisperRecorder";

// LeoJarvis 指挥台: 深/浅双主题 + 酒红强调色。颜色一律走 theme.css 的 CSS 变量。
// 每个 agent 一个区分色;统一用主题语义变量(深浅各自适配),不再写死深色 hex。
const TAG: Record<string, [string, string]> = {
  claude: ["CC", "var(--accent-2)"], codex: ["CX", "var(--good)"], cursor: ["CU", "var(--info)"],
  grok: ["GK", "var(--cat-purple)"], gemini: ["GM", "var(--warn)"], opencode: ["OC", "var(--text-dim)"],
  hermes: ["HM", "var(--cat-orange)"], openclaw: ["OW", "var(--cat-teal)"],
};
const A = (f: string) => `/cc/${f}`;

type Page = "cockpit" | "agents" | "intel" | "sense" | "notes" | "devices";
type Theme = "dark" | "light" | "auto";

const panel: CSSProperties = { background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 15, padding: 16 };
const sub: CSSProperties = { background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 13 };
const lbl: CSSProperties = { font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".18em", color: "var(--text-mute)" };
const mono = (s = 10, c = "var(--text-mute)"): CSSProperties => ({ font: `500 ${s}px 'IBM Plex Mono',monospace`, color: c });
const row = (g = 8): CSSProperties => ({ display: "flex", alignItems: "center", gap: g });
const flex1: CSSProperties = { flex: 1 };

// 统一页面说明条:一个「?说明」chip,点开展开「这页做什么 + 怎么用」。各页传不同文案,零冗余。
function PageHelp({ what, points }: { what: string; points: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ display: "grid", gap: open ? 8 : 0 }}>
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open}
        style={{ justifySelf: "start", ...row(6), border: "1px solid var(--border)", background: open ? "var(--accent-soft)" : "var(--panel-2)", color: open ? "var(--accent)" : "var(--text-dim)", cursor: "pointer", borderRadius: 999, padding: "4px 11px", font: "600 10.5px 'Space Grotesk',sans-serif" }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M9.2 9a2.8 2.8 0 0 1 5.5.6c0 1.9-2.7 2.4-2.7 2.4M12 17h.01" /></svg>
        这页怎么用
      </button>
      {open && (
        <div style={{ ...sub, padding: "12px 14px", display: "grid", gap: 8 }}>
          <p style={{ margin: 0, font: "400 12.5px/1.6 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>{what}</p>
          {points.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 5 }}>
              {points.map((p, i) => (
                <li key={i} style={{ ...row(7), alignItems: "flex-start", font: "400 12px/1.55 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>
                  <span style={{ width: 4, height: 4, borderRadius: "50%", background: "var(--accent)", marginTop: 7, flex: "none" }} />
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
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

const PAGES: Page[] = ["cockpit", "agents", "intel", "sense", "notes", "devices"];
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
    try { const v = localStorage.getItem("cx-theme"); return (v === "light" || v === "auto") ? v : v === "dark" ? "dark" : "auto"; } catch { return "auto"; }
  });
  const [vitals, setVitals] = useState<Vitals>({ health: null, cpu: null, online: 0, total: 0 });
  const [notifyToast, setNotifyToast] = useState<string>("");
  const [settingsOpen, setSettingsOpen] = useState(false);  // 问题10:齿轮 → 全屏设置面
  const [skillsHubOpen, setSkillsHubOpen] = useState(false);  // 问题8:技能 + MCP 中枢(顶栏图标)

  // 主题:auto 跟随系统 prefers-color-scheme,light/dark 手动锁定。
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => { document.documentElement.dataset.theme = theme === "auto" ? (mq.matches ? "dark" : "light") : theme; };
    apply();
    try { localStorage.setItem("cx-theme", theme); } catch { /* ignore */ }
    if (theme === "auto") { mq.addEventListener("change", apply); return () => mq.removeEventListener("change", apply); }
  }, [theme]);

  // 实时推送：情报命中/系统告警时弹一条 toast（数据刷新由各页自行订阅 subscribeNotify）。
  useEffect(() => {
    const stop = subscribeNotify((e) => {
      const title = String(e.title || e.source || "有新动态");
      setNotifyToast(title.slice(0, 48));
      window.setTimeout(() => setNotifyToast(""), 4000);
    });
    return stop;
  }, []);

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
    cockpit: ["全景驾驶舱", "实时总览"], agents: ["智能体工作区", "多会话并行"],
    intel: ["情报中心", "时效优先"], sense: ["感知接入", "情境上下文"],
    notes: ["记事与文档", "全能记事"], devices: ["设备舰队", "多端在线"],
  };
  const nav = (p: Page) => ({ fg: page === p ? "var(--accent)" : "var(--text-mute)", bg: page === p ? "var(--accent-soft)" : "transparent", bar: page === p ? "var(--accent)" : "transparent" });
  const navBtn = (p: Page, title: string, icon: ReactNode) => {
    const n = nav(p);
    return (
      <button className="cx-navtip" onClick={() => setPage(p)} data-tip={title} style={{ position: "relative", width: 46, height: 46, border: 0, cursor: "pointer", borderRadius: 13, background: n.bg, color: n.fg, display: "grid", placeContent: "center" }}>
        <span style={{ position: "absolute", left: -14, top: "50%", transform: "translateY(-50%)", width: 3, height: 20, borderRadius: 3, background: n.bar }} />
        {icon}
      </button>
    );
  };

  return (
    <div className="cx-shell" style={{ height: "100vh", display: "grid", gridTemplateColumns: "68px 1fr", background: "var(--bg)", color: "var(--text)", fontFamily: "'Space Grotesk','PingFang SC','Microsoft YaHei',sans-serif", overflow: "hidden" }}>
      <nav className="cx-shell-nav" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "14px 0", background: "var(--bg-2)", borderRight: "1px solid var(--border-soft)" }}>
        <img src={A("brand-mark.png")} alt="" style={{ width: 40, height: 40, borderRadius: 11, objectFit: "cover", boxShadow: "0 0 0 1px var(--border),0 0 18px var(--accent-soft)", marginBottom: 10 }} />
        {navBtn("cockpit", "驾驶舱", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="2" /><rect x="3" y="13.5" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" /></svg>)}
        {navBtn("agents", "智能体工作区", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="5" r="2.4" /><circle cx="5.5" cy="18" r="2.4" /><circle cx="18.5" cy="18" r="2.4" /><path d="M12 7.4v3M11 12l-4 4M13 12l4 4" /></svg>)}
        {navBtn("intel", "情报", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12l6-6" /></svg>)}
        {navBtn("sense", "感知接入", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 12a1.5 1.5 0 1 0 0-.01" /><path d="M8.5 8.5a5 5 0 0 1 7 0M5.6 5.6a9 9 0 0 1 12.8 0" /><path d="M9 15.5a4 4 0 0 0 6 0" /></svg>)}
        {navBtn("notes", "记事与文档", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 3h11l3 3v15a0 0 0 0 1 0 0H5a0 0 0 0 1 0 0z" /><path d="M8.5 8.5h7M8.5 12h7M8.5 15.5h4" /></svg>)}
        {navBtn("devices", "设备", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M2 20h20M9 16v4M15 16v4" /></svg>)}
        <span style={flex1} />
        {/* 技能 + MCP 中枢(问题8):不占 tab,顶栏图标点开。 */}
        <button onClick={() => setSkillsHubOpen(true)} className="cx-navtip" data-tip="技能与 MCP" style={{ width: 46, height: 46, border: 0, cursor: "pointer", borderRadius: 13, background: "transparent", color: "var(--text-mute)", display: "grid", placeContent: "center" }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 3l2.1 4.4 4.9.7-3.5 3.4.8 4.8L12 18l-4.3 2.3.8-4.8-3.5-3.4 4.9-.7z" /></svg>
        </button>
        {/* 深浅色:三态循环 auto → light → dark(问题10)。 */}
        <button onClick={() => setTheme((t) => (t === "auto" ? "light" : t === "light" ? "dark" : "auto"))} className="cx-navtip" data-tip={theme === "auto" ? "主题:跟随系统" : theme === "light" ? "主题:浅色" : "主题:深色"} style={{ width: 46, height: 46, border: 0, cursor: "pointer", borderRadius: 13, background: "transparent", color: "var(--text-mute)", display: "grid", placeContent: "center" }}>
          {theme === "auto"
            ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path d="M12 3v18" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none" /></svg>
            : theme === "dark"
              ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8z" /></svg>
              : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" /></svg>}
        </button>
        {/* 设置:齿轮 → 全屏设置面(问题10)。 */}
        <button onClick={() => setSettingsOpen(true)} className="cx-navtip" data-tip="设置" style={{ width: 46, height: 46, border: 0, cursor: "pointer", borderRadius: 13, background: "transparent", color: "var(--text-mute)", display: "grid", placeContent: "center" }}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></svg>
        </button>
      </nav>

      <div className="cx-shell-main" style={{ display: "grid", gridTemplateRows: page === "cockpit" ? "1fr" : "58px 1fr", minWidth: 0, minHeight: 0 }}>
        {page !== "cockpit" && <header className="cx-shell-header" style={{ ...row(16), padding: "0 18px", borderBottom: "1px solid var(--border-soft)", background: "var(--bg-2)" }}>
          <div style={{ flex: "none", minWidth: 128 }}>
            <div style={{ font: "600 14.5px 'Space Grotesk',sans-serif", color: "var(--text)", lineHeight: 1.1 }}>{META[page][0]}</div>
            <div style={{ font: "500 9.5px 'Space Grotesk',sans-serif", letterSpacing: ".04em", color: "var(--text-mute)", marginTop: 2 }}>{META[page][1]}</div>
          </div>
          <span style={flex1} />
          <div className="cx-shell-vitals" style={{ flex: "none", ...row(9), font: "600 11px 'IBM Plex Mono',monospace" }}>
            <span style={{ ...row(5), background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 9px", color: "var(--text-dim)" }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 4s ease infinite" }} />健康 <b style={{ color: "var(--text)" }}>{vitals.health ?? "—"}</b></span>
            <span style={{ ...row(5), background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 9px", color: "var(--text-dim)" }}>CPU <b style={{ color: "var(--text)" }}>{vitals.cpu != null ? `${vitals.cpu}%` : "—"}</b></span>
            <span style={{ ...row(5), background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 9px", color: "var(--text-dim)" }}>服务 <b style={{ color: "var(--good)" }}>{vitals.online}/{vitals.total}</b></span>
            <span style={{ width: 1, height: 20, background: "var(--border)" }} />
            <span style={{ color: "var(--text)", letterSpacing: ".04em" }}>{clock}</span>
          </div>
        </header>}

        <div className="cx-shell-surface" style={{ position: "relative", minHeight: 0, overflow: "hidden", backgroundImage: "linear-gradient(var(--border-soft) 1px,transparent 1px),linear-gradient(90deg,var(--border-soft) 1px,transparent 1px)", backgroundSize: "38px 38px", backgroundBlendMode: "overlay", opacity: 1 }}>
          {scan && <div className="cx-scanline" style={{ top: 0 }} />}
          {page === "cockpit" && <Cockpit themeMode={theme} goIntel={() => setPage("intel")} goNotes={(id) => { setNotesOpenId(id ?? null); setPage("notes"); }} goAgents={() => setPage("agents")} goSense={() => setPage("sense")} goDevices={() => setPage("devices")} />}
          {page === "agents" && <Agents themeMode={theme} />}
          {page === "intel" && <Intel />}
          {page === "sense" && <Sense />}
          {page === "notes" && <Notes openId={notesOpenId} />}
          {page === "devices" && <Devices />}
        </div>
      </div>
      {/* 问题10:设置全屏面(齿轮呼出) */}
      <Modal open={settingsOpen} onClose={() => setSettingsOpen(false)} eyebrow="设置" title="LeoJarvis 设置" width={1000} maxHeight={780}>
        <Settings theme={theme} setTheme={setTheme} scan={scan} toggleScan={() => setScan((v) => !v)} />
      </Modal>
      {/* 问题8:技能与 MCP 中枢(顶栏图标呼出) */}
      {skillsHubOpen && <SkillsHub onClose={() => setSkillsHubOpen(false)} />}
      {notifyToast && (
        // 底部居中 toast——不再压右上角的时间/状态;轻浮起,4s 自动消失。
        <div className="cx-pop-in" style={{ position: "fixed", bottom: 22, left: "50%", transform: "translateX(-50%)", zIndex: Z.toast, background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 999, padding: "10px 20px", font: "600 12.5px 'Space Grotesk'", color: "var(--text)", boxShadow: "var(--shadow)", maxWidth: "min(440px,90vw)", display: "flex", alignItems: "center", gap: 9 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)", flex: "none", boxShadow: "0 0 7px var(--accent)" }} />{notifyToast}</div>
      )}
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
// 问题4:时效第一。今天显 HH:MM,往日显 MM-DD HH:MM —— 6/26 的历史项不再看着像今天。
function tsToTime(ts?: number): string {
  if (!ts) return "";
  const ms = ts > 1e12 ? ts : ts * 1000;
  const d = new Date(ms);
  if (isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  const now = new Date();
  const sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  return sameDay ? `${p(d.getHours())}:${p(d.getMinutes())}` : `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
// GitHub 仓库的"最近更新"(pushed_at 是 ISO 字符串):显示相对时间。
function githubPushedAgo(pushed?: string): string {
  if (!pushed) return "";
  const t = Date.parse(pushed);
  if (Number.isNaN(t)) return "";
  const days = Math.floor((Date.now() - t) / 86400000);
  if (days <= 0) return "今天更新";
  if (days === 1) return "昨天更新";
  if (days < 30) return `${days} 天前更新`;
  if (days < 365) return `${Math.floor(days / 30)} 个月前更新`;
  return `${Math.floor(days / 365)} 年前更新`;
}

type Turn =
  | { kind: "user"; text: string }
  | { kind: "steps"; steps: ChatStep[] }
  | { kind: "assistant"; text: string }
  | { kind: "pending"; actions: PendingAction[] }
  | { kind: "system"; text: string };

// 天气文字 → emoji
function wxEmoji(t?: string): string {
  const s = t || "";
  if (s.includes("雷")) return "⛈"; if (s.includes("雪")) return "❄️"; if (s.includes("雨")) return "🌧";
  if (s.includes("雾") || s.includes("霾")) return "🌫"; if (s.includes("阴")) return "☁️";
  if (s.includes("多云")) return "⛅"; if (s.includes("晴")) return "☀️"; return "🌤";
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
    catch { alert("保存失败，请重试"); } finally { setSaving(false); }
  }
  async function del() { if (!sel || !window.confirm("删除这条记事？")) return; try { await deleteNote(sel); newNote(); load(); } catch { alert("删除失败，请重试"); } }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: Z.drawer, background: "rgba(4,6,9,.5)", backdropFilter: "blur(2px)", display: "flex", justifyContent: "flex-end", animation: "cxFade .18s ease both" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: "min(720px,94vw)", height: "100%", background: "var(--panel)", borderLeft: "1px solid var(--border)", boxShadow: "var(--shadow)", display: "grid", gridTemplateColumns: "240px minmax(0,1fr)", animation: "cxSlideIn .26s cubic-bezier(.22,.61,.36,1) both" }}>
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


// ============ 应用与邮件（R8：不暗化 + 可点击看详情/打开）============
function AppIcon({ a, size = 46 }: { a: NotifApp; size?: number }) {
  const local: Record<string, string> = { mail: "mail.png", wechat: "wechat.png", telegram: "telegram.png", popo: "popo.png", mailmaster: "mailmaster.png" };
  const src = a.icon || (local[a.id] ? A(local[a.id]) : "");
  // 统一 tile：所有图标（含 Gmail）满铺 + 同一描边。描边用半透明灰，在「白底 Gmail」和
  // 「彩色满铺图标」上都同样轻——不会出现彩色图标看不见描边、白底 Gmail 却像加了边框的割裂感。
  const frame: CSSProperties = { width: size, height: size, borderRadius: Math.round(size * 0.26), boxShadow: "0 0 0 1px rgba(140,146,158,.16), 0 1px 3px rgba(0,0,0,.22)", display: "grid", placeContent: "center", overflow: "hidden", boxSizing: "border-box", flex: "none", background: "var(--panel-2)" };
  if (a.id === "gmail" && !a.icon) return <span style={{ ...frame, background: "var(--panel)" }}><GmailMark size={Math.round(size * 0.82)} /></span>;
  if (src) return <span style={frame}><img src={src} alt={a.name || a.id} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} /></span>;
  return <span style={{ ...frame, font: `700 ${Math.round(size * 0.4)}px 'Space Grotesk'`, color: "var(--text-dim)" }}>{(a.name || a.id).slice(0, 1).toUpperCase()}</span>;
}
// ============ COCKPIT（P10 新布局）============
// 中枢核心：旋转轨道 + 品牌核 + 均衡器（design 稿装饰中枢）
// 中枢核心（动态头像）—— 缩小 ~30%，点击即呼出 Jarvis 对话气泡。
// 光环动效编码真实状态（motivated motion）：
//   在线 = 旋转+脉冲(rose，活着)；离线 = 停转、去饱和变灰(掉线一眼可辨)。
// 不再「为酷而恒转」。reduced-motion 由 theme.css 统一收敛为静态。
function CoreOrb({ online, onClick }: { online: boolean; onClick?: () => void }) {
  // 主题化:在线用 accent、离线用 text-mute;透明梯度用 color-mix(深浅各自适配,不再写死深色 rgb)。
  const tint = online ? "var(--accent)" : "var(--text-mute)";
  const mix = (pct: number) => `color-mix(in srgb, ${tint} ${pct}%, transparent)`;
  const spin = (dur: string, dir = "") => (online ? `cxSpin${dir} ${dur} linear infinite` : "none");
  return (
    <button onClick={onClick} title="点击和 Jarvis 对话" className="cx-orb" style={{ border: 0, background: "transparent", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 5, animation: "cxRise .6s ease both", padding: 0, justifySelf: "center", filter: online ? "none" : "saturate(.25)", opacity: online ? 1 : 0.82, transition: "filter .5s, opacity .5s" }}>
      <div style={{ position: "relative", width: 124, height: 124, display: "grid", placeItems: "center", flex: "none" }}>
        <div style={{ position: "absolute", width: 124, height: 124, borderRadius: "50%", border: `1px solid ${mix(18)}`, animation: spin("26s") }} />
        <div style={{ position: "absolute", width: 124, height: 124, animation: spin("26s") }}><span style={{ position: "absolute", top: -3, left: "50%", width: 5, height: 5, borderRadius: "50%", background: online ? "var(--accent)" : "var(--text-mute)", transform: "translateX(-50%)", boxShadow: online ? "0 0 8px var(--accent)" : "none" }} /></div>
        <div style={{ position: "absolute", width: 100, height: 100, borderRadius: "50%", border: `1px dashed ${mix(28)}`, animation: spin("18s", "R") }} />
        {online && <div style={{ position: "absolute", width: 80, height: 80, borderRadius: "50%", border: `1px solid ${mix(40)}`, animation: "cxPing 3.4s ease-out infinite" }} />}
        <div className="cx-orb-core" style={{ position: "relative", width: 64, height: 64, borderRadius: "50%", display: "grid", placeItems: "center", background: "radial-gradient(circle at 38% 32%, var(--panel-2), var(--panel-3))", boxShadow: "inset 0 0 14px rgba(0,0,0,.35),0 0 0 1px var(--border)", animation: online ? "cxCorePulse 4.5s ease infinite" : "none", overflow: "hidden" }}>
          <img src={A("brand-mark.png")} alt="" style={{ width: 64, height: 64, objectFit: "cover", opacity: .92 }} />
          <div style={{ position: "absolute", inset: 0, background: `radial-gradient(circle at 50% 120%, ${mix(40)}, transparent 60%)` }} />
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, flex: "none" }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 2.5, height: 13 }}>
          {Array.from({ length: 9 }).map((_, i) => <i key={i} style={{ width: 2.5, height: online ? "100%" : "30%", background: online ? "linear-gradient(var(--accent-2),var(--accent))" : "var(--text-mute)", borderRadius: 2, display: "block", transformOrigin: "bottom", animation: online ? `cxBar ${(0.7 + (i % 4) * 0.22).toFixed(2)}s ease-in-out infinite ${(i * 0.09).toFixed(2)}s` : "none" }} />)}
        </div>
        <span style={{ ...row(4), font: "600 9px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: online ? "var(--accent)" : "var(--text-mute)", whiteSpace: "nowrap" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: online ? "var(--good)" : "var(--text-mute)", display: "inline-block", boxShadow: online ? "0 0 5px var(--good)" : "none" }} />{online ? "点我 和 Jarvis 对话" : "Mac 离线"}</span>
      </div>
    </button>
  );
}

// ============ 问题7: 主动助理 = 可配置定时任务引擎(收进 Jarvis 对话弹窗的「主动助理」页) ============
function AssistantSettings() {
  const [cfg, setCfg] = useState<AssistantConfig | null>(null);
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState("");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", prompt: "", trigger: "interval", interval_minutes: 60, cron_hour: 9, cron_minute: 0, trigger_event: "email_actionable", trigger_count: 1 });
  const loadCfg = () => getAssistantConfig().then((d) => setCfg(d.config)).catch(() => {});
  const loadTasks = () => getScheduledTasks().then((d) => setTasks((d.tasks || []).filter((t) => !t.name.startsWith("[check-in]")))).catch(() => {});
  useEffect(() => { loadCfg(); loadTasks(); }, []);
  const save = async (patch: Partial<AssistantConfig>) => { const d = await patchAssistantConfig(patch); setCfg(d.config); };
  const runNow = async (slot: string) => { setBusy(slot); setOut(""); try { const r = await runCheckin(slot); setOut(r.reply || "(无输出)"); } finally { setBusy(""); } };
  const createTask = async () => { if (!form.name.trim() || !form.prompt.trim()) return; await createScheduledTask(form); setAdding(false); setForm({ ...form, name: "", prompt: "" }); loadTasks(); };
  const toggleTask = async (t: ScheduledTask) => { await setScheduledTaskStatus(t.id, t.status === "active" ? "paused" : "active"); loadTasks(); };
  const delTask = async (id: string) => { await setScheduledTaskStatus(id, "deleted"); loadTasks(); };
  const runTask = async (id: string) => { await runScheduledTask(id); loadTasks(); };
  if (!cfg) return <div style={{ padding: 24, ...mono(11) }}>加载助理配置…</div>;
  const ipt: CSSProperties = { background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", color: "var(--text)", font: "400 12.5px 'Space Grotesk'", outline: "none", width: "100%" };
  const slots: [string, string][] = [["morning", "早间"], ["midday", "午间"], ["evening", "晚间"]];
  const presets: [string, string][] = [["简洁干练", "你是 Leo 的私人助理,主动、简洁、以行动为先。汇报时只说要点和该做什么,不寒暄。"], ["温和耐心", "你是 Leo 的私人助理,语气温和、耐心、体贴。汇报清楚到位,在合适时给一句鼓励。"], ["犀利参谋", "你是 Leo 的参谋,直接、犀利、敢于指出问题与风险,给出有判断的建议而非罗列选项。"]];
  const trigText = (t: ScheduledTask) => t.trigger === "interval" ? `每 ${t.interval_minutes} 分` : t.trigger === "cron" ? `每天 ${String(t.cron_hour).padStart(2, "0")}:${String(t.cron_minute).padStart(2, "0")}` : `事件 ${t.trigger_event} ×${t.trigger_count}`;
  return (
    <div style={{ padding: "14px 16px", display: "grid", gap: 14, alignContent: "start" }}>
      <PageHelp what="主动助理 = 你的后台自动工作引擎。设定它的口吻,让它每天定时汇总,或新增任意「到点/遇事自动跑」的任务——像本机定时任务一样,但由 Jarvis 用 agent 能力执行。"
        points={["人格影响所有主动汇报口吻;早中晚 check-in 到点自动汇总待办/邮件/日程", "「新增自动任务」可写任意指令 + 触发方式(按间隔/每天/事件),后台自动执行经行动闸门", "和左上「对话」随时切换"]} />
      {/* 身份 */}
      <div style={{ ...sub, padding: "13px 14px", display: "grid", gap: 11 }}>
        <div style={{ ...row(9) }}><b style={{ font: "600 13px 'Space Grotesk'", color: "var(--text)" }}>身份 & 口吻</b><span style={flex1} /><label style={{ ...row(6), cursor: "pointer", ...mono(10) }}><input type="checkbox" checked={cfg.enabled} onChange={(e) => save({ enabled: e.target.checked })} />启用</label></div>
        <input value={cfg.name} onChange={(e) => setCfg({ ...cfg, name: e.target.value })} onBlur={() => save({ name: cfg.name })} placeholder="名字" style={ipt} />
        <textarea value={cfg.persona} onChange={(e) => setCfg({ ...cfg, persona: e.target.value })} onBlur={() => save({ persona: cfg.persona })} rows={2} placeholder="人格 / 口吻" style={{ ...ipt, resize: "vertical" }} />
        <div style={{ ...row(7), flexWrap: "wrap" }}><span style={mono(9.5)}>预设</span>{presets.map(([n, t]) => <button key={n} onClick={() => { setCfg({ ...cfg, persona: t }); save({ persona: t }); }} style={{ border: "1px solid var(--border)", background: cfg.persona === t ? "var(--accent-soft)" : "var(--panel)", color: cfg.persona === t ? "var(--accent)" : "var(--text-dim)", cursor: "pointer", borderRadius: 999, padding: "4px 11px", font: "500 11px 'Space Grotesk'" }}>{n}</button>)}</div>
      </div>
      {/* 每日 check-in */}
      <div style={{ ...sub, padding: "13px 14px", display: "grid", gap: 9 }}>
        <div style={lbl}>每日主动 check-in</div>
        {slots.map(([key, zh]) => { const c = cfg.checkins[key] || { enabled: true, hour: 9, minute: 0 }; return (
          <div key={key} style={{ ...row(9), flexWrap: "wrap" }}>
            <label style={{ ...row(6), cursor: "pointer" }}><input type="checkbox" checked={c.enabled} onChange={(e) => save({ checkins: { ...cfg.checkins, [key]: { ...c, enabled: e.target.checked } } })} /><b style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)" }}>{zh}</b></label>
            <input type="number" value={c.hour} onChange={(e) => save({ checkins: { ...cfg.checkins, [key]: { ...c, hour: +e.target.value } } })} style={{ ...ipt, width: 56 }} /><span style={mono(10)}>时</span>
            <input type="number" value={c.minute} onChange={(e) => save({ checkins: { ...cfg.checkins, [key]: { ...c, minute: +e.target.value } } })} style={{ ...ipt, width: 56 }} /><span style={mono(10)}>分</span>
            <span style={flex1} /><button onClick={() => runNow(key)} disabled={busy === key} style={{ border: "1px solid var(--accent)", background: "var(--accent-soft)", color: "var(--accent)", cursor: "pointer", borderRadius: 8, padding: "5px 12px", font: "600 10.5px 'Space Grotesk'" }}>{busy === key ? "运行中…" : "试跑"}</button>
          </div>
        ); })}
        {out && <div style={{ ...panel, padding: "10px 12px" }}><div style={{ ...lbl, marginBottom: 5 }}>试跑输出</div><p style={{ margin: 0, font: "400 12px/1.6 'Space Grotesk'", color: "var(--text-dim)", whiteSpace: "pre-wrap" }}>{out}</p></div>}
      </div>
      {/* 自定义自动任务 */}
      <div style={{ ...sub, padding: "13px 14px", display: "grid", gap: 9 }}>
        <div style={{ ...row(8) }}><span style={lbl}>自动任务({tasks.length})</span><span style={flex1} /><button onClick={() => setAdding((v) => !v)} style={{ border: "1px solid var(--accent)", background: "var(--accent-soft)", color: "var(--accent)", cursor: "pointer", borderRadius: 8, padding: "5px 12px", font: "600 10.5px 'Space Grotesk'" }}>{adding ? "收起" : "＋ 新增"}</button></div>
        {adding && (
          <div style={{ ...panel, padding: 12, display: "grid", gap: 8 }}>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="任务名" style={ipt} />
            <textarea value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} placeholder="给 agent 的指令(如:每天早上汇总未读邮件要点发我)" rows={2} style={{ ...ipt, resize: "vertical" }} />
            <div style={{ ...row(6) }}>{(["interval", "cron", "event"] as const).map((tr) => <button key={tr} onClick={() => setForm({ ...form, trigger: tr })} style={{ border: 0, cursor: "pointer", borderRadius: 7, padding: "6px 11px", font: "600 10.5px 'Space Grotesk'", background: form.trigger === tr ? "var(--accent)" : "var(--panel-2)", color: form.trigger === tr ? "#fff" : "var(--text-dim)" }}>{tr === "interval" ? "按间隔" : tr === "cron" ? "每天定时" : "事件触发"}</button>)}</div>
            {form.trigger === "interval" && <div style={{ ...row(7) }}><span style={mono(10)}>每</span><input type="number" value={form.interval_minutes} onChange={(e) => setForm({ ...form, interval_minutes: +e.target.value })} style={{ ...ipt, width: 80 }} /><span style={mono(10)}>分钟</span></div>}
            {form.trigger === "cron" && <div style={{ ...row(7) }}><span style={mono(10)}>每天</span><input type="number" value={form.cron_hour} onChange={(e) => setForm({ ...form, cron_hour: +e.target.value })} style={{ ...ipt, width: 60 }} /><span style={mono(10)}>时</span><input type="number" value={form.cron_minute} onChange={(e) => setForm({ ...form, cron_minute: +e.target.value })} style={{ ...ipt, width: 60 }} /><span style={mono(10)}>分</span></div>}
            {form.trigger === "event" && <div style={{ ...row(7) }}><input value={form.trigger_event} onChange={(e) => setForm({ ...form, trigger_event: e.target.value })} placeholder="事件名" style={{ ...ipt, flex: 1 }} /><span style={mono(10)}>累计</span><input type="number" value={form.trigger_count} onChange={(e) => setForm({ ...form, trigger_count: +e.target.value })} style={{ ...ipt, width: 56 }} /><span style={mono(10)}>次</span></div>}
            <button onClick={createTask} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "8px 0", font: "600 12px 'Space Grotesk'" }}>创建</button>
          </div>
        )}
        {tasks.length === 0 && !adding && <div style={{ ...mono(10.5), padding: "4px 2px", lineHeight: 1.6 }}>还没有自定义自动任务。点「新增」让 Jarvis 定时或遇事自动替你跑活。</div>}
        {tasks.map((t) => (
          <div key={t.id} style={{ ...panel, padding: "10px 12px", display: "grid", gap: 5 }}>
            <div style={{ ...row(8) }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: t.status === "active" ? "var(--good)" : "var(--text-mute)", flex: "none" }} /><b style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)", flex: 1 }}>{t.name}</b><span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--text-dim)", background: "var(--panel-3)", borderRadius: 999, padding: "2px 8px" }}>{trigText(t)}</span></div>
            <div style={{ font: "400 11px 'Space Grotesk'", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.prompt}</div>
            <div style={{ ...row(7) }}><button onClick={() => runTask(t.id)} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--accent)", cursor: "pointer", borderRadius: 7, padding: "4px 11px", font: "600 10px 'Space Grotesk'" }}>立即跑</button><button onClick={() => toggleTask(t)} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 7, padding: "4px 11px", font: "600 10px 'Space Grotesk'" }}>{t.status === "active" ? "暂停" : "启用"}</button><span style={flex1} /><button onClick={() => delTask(t.id)} style={{ border: 0, background: "transparent", color: "var(--text-mute)", cursor: "pointer", font: "600 10px 'Space Grotesk'" }}>删除</button></div>
          </div>
        ))}
      </div>
    </div>
  );
}

// 中枢对话气泡 —— 点击动态头像呼出的浮层对话框（不再占首页固定版面）。
function JarvisChat({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<"chat" | "assistant">("chat");  // 问题7:对话 / 主动助理设置
  const greeting = "我是你的中枢 Jarvis。问本机状态、今日情报、天气路线，或让我跑个 agent、记一笔。";
  const tips = ["磁盘为什么满了", "今天高优先情报", "让 codex 看这个项目", "记一笔"];
  const [turns, setTurns] = useState<Turn[]>([{ kind: "assistant", text: greeting }]);
  const [history, setHistory] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [approving, setApproving] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const voice = useWhisperRecorder({
    prompt: "LeoJarvis 指挥中心 Jarvis 对话",
    onText: (text) => setDraft((prev) => prev.trim() ? `${prev.trim()}\n${text}` : text),
    onError: (message) => setTurns((t) => [...t, { kind: "system", text: `语音识别失败：${message}` }]),
  });
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
    let assistantText = "";
    let streaming = false;
    const steps: ChatStep[] = [];
    try {
      await agentChatStream(next, (e) => {
        if (e.type === "tool_start") {
          steps.push({ tool: e.tool, args: e.args, status: "running" });
          setTurns((t) => [...t, { kind: "steps", steps: [...steps] }]);
        } else if (e.type === "tool_result") {
          const s = steps.find((x) => x.tool === e.tool && x.status === "running");
          if (s) { s.status = e.status; s.result = e.result; }
        } else if (e.type === "token") {
          assistantText += e.text;
          const snap = assistantText;
          setTurns((t) => {
            if (!streaming) { streaming = true; return [...t, { kind: "assistant", text: snap }]; }
            let idx = -1;
            for (let i = t.length - 1; i >= 0; i--) { if (t[i].kind === "assistant") { idx = i; break; } }
            if (idx < 0) return [...t, { kind: "assistant", text: snap }];
            const copy = [...t]; copy[idx] = { kind: "assistant", text: snap }; return copy;
          });
        } else if (e.type === "final") {
          if (e.reply) setHistory((h) => [...h, { role: "assistant", content: e.reply }]);
        } else if (e.type === "pending") {
          if (e.reply && !assistantText) setTurns((t) => [...t, { kind: "assistant", text: e.reply }]);
          if (e.pending_actions?.length) setTurns((t) => [...t, { kind: "pending", actions: e.pending_actions! }]);
        } else if (e.type === "error") {
          setTurns((t) => [...t, { kind: "system", text: e.message }]);
        }
      });
    } catch { setTurns((t) => [...t, { kind: "system", text: "中枢暂时无法连接，请稍后再试。" }]); }
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
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: Z.modal, background: "rgba(0,0,0,.34)", display: "grid", placeItems: "start center", paddingTop: 84, animation: "cxFade .16s ease both" }}>
      <div onClick={(e) => e.stopPropagation()} className="cx-pop-in" style={{ width: mode === "assistant" ? "min(720px,94vw)" : "min(580px,92vw)", height: "min(68vh,600px)", ...panel, padding: 0, display: "grid", gridTemplateRows: mode === "assistant" ? "auto minmax(0,1fr)" : "auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden", position: "relative", background: "linear-gradient(180deg,var(--panel),var(--panel-2))", boxShadow: "var(--shadow)" }}>
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}><span style={{ position: "absolute", top: 0, left: 0, width: "32%", height: "100%", background: "linear-gradient(90deg,transparent,var(--accent-soft),transparent)", animation: "cxSheen 7s ease-in-out infinite" }} /></div>
      <div style={{ ...row(9), padding: "12px 14px 11px", borderBottom: "1px solid var(--border-soft)", position: "relative" }}>
        <img src={A("brand-mark.png")} alt="" style={{ width: 28, height: 28, borderRadius: 8, objectFit: "cover", flex: "none" }} />
        <div style={{ flex: "none", display: "flex", gap: 4, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: 3 }}>
          {([["chat", "对话"], ["assistant", "主动助理"]] as const).map(([m, zh]) => (<button key={m} onClick={() => setMode(m)} style={{ border: 0, cursor: "pointer", borderRadius: 6, padding: "5px 12px", font: "600 11px 'Space Grotesk'", background: mode === m ? "var(--accent)" : "transparent", color: mode === m ? "#fff" : "var(--text-dim)" }}>{zh}</button>))}
        </div>
        <span style={flex1} />
        {mode === "chat" && <span style={{ font: "700 15px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>&gt;_</span>}
        <button onClick={onClose} title="关闭(Esc)" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-mute)", cursor: "pointer", width: 28, height: 28, borderRadius: 8, display: "grid", placeContent: "center", flex: "none" }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
      </div>
      {mode === "assistant" && <div style={{ overflowY: "auto", minHeight: 0 }}><AssistantSettings /></div>}
      {mode === "chat" && <>
      <div ref={scrollRef} style={{ overflowY: "auto", minHeight: 0, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 9, position: "relative" }}>
        {turns.map((tn, i) => {
          if (tn.kind === "user") return <div key={i} style={{ alignSelf: "flex-end", maxWidth: "86%", background: "var(--accent)", color: "#fff", font: "500 12.5px 'Space Grotesk',sans-serif", padding: "8px 12px", borderRadius: 12, borderBottomRightRadius: 4, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{tn.text}</div>;
          if (tn.kind === "steps") return <div key={i} style={{ alignSelf: "flex-start", display: "grid", gap: 5, width: "94%" }}>{tn.steps.map((st, j) => { const tone = stepTone(st.status); return <div key={j} style={{ ...row(8), background: "var(--panel)", border: "1px solid var(--border)", borderLeft: `3px solid ${tone.bar}`, borderRadius: 8, padding: "6px 9px" }}><code style={{ font: "600 10.5px 'IBM Plex Mono',monospace", color: tone.bar }}>{st.tool}</code><span style={flex1} /><span style={mono(9)}>{tone.label}</span></div>; })}</div>;
          if (tn.kind === "assistant") return <div key={i} style={{ alignSelf: "flex-start", maxWidth: "92%", background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text-dim)", font: "400 12.5px/1.6 'Space Grotesk',sans-serif", padding: "9px 12px", borderRadius: 12, borderBottomLeftRadius: 4, whiteSpace: "pre-wrap" }}>{tn.text}</div>;
          if (tn.kind === "system") return <div key={i} style={{ alignSelf: "center", ...mono(10, "var(--bad)") }}>{tn.text}</div>;
          return <div key={i} style={{ alignSelf: "flex-start", display: "grid", gap: 5, maxWidth: "94%" }}>{tn.actions.map((act) => <div key={act.id} style={{ ...row(8), background: "var(--warn-soft)", border: "1px solid var(--warn-soft)", borderRadius: 10, padding: "8px 11px" }}><span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "var(--warn)", whiteSpace: "nowrap" }}>待确认</span><code style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{act.reason || act.tool || act.id}</code><button onClick={() => approve(act.id)} disabled={approving === act.id} style={{ border: 0, cursor: "pointer", background: "var(--warn)", color: "#fff", font: "600 10px 'Space Grotesk'", padding: "4px 10px", borderRadius: 6, whiteSpace: "nowrap", opacity: approving === act.id ? 0.6 : 1 }}>{approving === act.id ? "执行中" : "确认"}</button></div>)}</div>;
        })}
        {single && <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 2 }}>{tips.map((q) => <button key={q} onClick={() => send(q)} className="cx-chip" style={{ border: "1px solid var(--border)", background: "var(--panel)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 999, padding: "5px 10px", font: "500 10.5px 'Space Grotesk'" }}>{q}</button>)}</div>}
        {busy && <div style={{ alignSelf: "flex-start", ...mono(10, "var(--text-mute)") }}>中枢思考中…</div>}
      </div>
      <div style={{ ...row(8), padding: "10px 12px", borderTop: "1px solid var(--border-soft)", position: "relative" }}>
        <input ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(draft); }} placeholder="和 Jarvis 说点什么…" style={{ flex: 1, background: "var(--panel-3)", border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", color: "var(--text)", font: "500 12.5px 'Space Grotesk',sans-serif", outline: "none" }} />
        <button onClick={voice.toggle} disabled={busy || voice.transcribing} title="Whisper 语音输入" style={{ border: "1px solid var(--border)", cursor: busy || voice.transcribing ? "default" : "pointer", background: voice.recording ? "var(--bad)" : "var(--panel-2)", color: voice.recording ? "#fff" : "var(--text-dim)", font: "600 11px 'Space Grotesk'", padding: "8px 12px", borderRadius: 9, flex: "none", opacity: busy || voice.transcribing ? 0.55 : 1 }}>{voice.transcribing ? "转写中" : voice.recording ? "停止" : "语音"}</button>
        <button onClick={() => send(draft)} disabled={busy || !draft.trim()} style={{ border: 0, cursor: busy || !draft.trim() ? "default" : "pointer", background: "var(--accent)", color: "#fff", font: "600 12px 'Space Grotesk'", padding: "8px 15px", borderRadius: 9, flex: "none", opacity: busy || !draft.trim() ? 0.5 : 1 }}>发送</button>
      </div>
      </>}
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
  if (offline.length) lines.push({ topic: "服务告警", detail: `${offline.map((s) => s.display || s.name).slice(0, 2).join("、")} 掉线，重启预案就绪，待你确认。`, tone: "var(--bad)" });
  else if (opts.ssd != null && opts.ssd >= 85) lines.push({ topic: "磁盘吃紧", detail: `SSD 已用 ${opts.ssd}%，建议清理热点目录释放空间。`, tone: "var(--warn)" });
  else if (opts.cpu != null && opts.cpu >= 85) lines.push({ topic: "CPU 高负载", detail: `当前负载 ${opts.cpu}%，留意占用最高的进程。`, tone: "var(--warn)" });
  else lines.push({ topic: "系统平稳", detail: `${opts.svcOnline}/${opts.svcTotal} 服务在线，健康分 ${opts.health ?? "—"}，磁盘 ${opts.ssd ?? "—"}%，无告警。`, tone: "var(--good)" });
  // ② 智能体 / 未读 —— 系统侧动态
  if (opts.running > 0) lines.push({ topic: "智能体在跑", detail: `${opts.running} 个会话运行中，切换页面不影响后台执行。`, tone: "var(--accent)" });
  if (opts.unread > 0) lines.push({ topic: "未读消息", detail: `共 ${opts.unread} 条未读，可在右侧应用区直接打开处理。`, tone: "var(--warn)" });
  // ③ 顶级情报，把简报填到 4 条
  const top = pickBriefingLeads(opts.news, 4);
  for (const it of top) {
    if (lines.length >= 4) break;
    const title = String(it.title || "");
    lines.push({ topic: (title.split(/[，。：、!?！？\s]/)[0] || title).slice(0, 16), detail: String(it.take || (it as { why_important?: string }).why_important || title).slice(0, 80), tone: it.priority === "高优先" ? "var(--bad)" : "var(--accent)", id: it.event_id });
  }
  return lines.slice(0, 4).map((l, i) => ({ idx: String(i + 1).padStart(2, "0"), ...l }));
}


// ============ 驾驶舱重构：首页常驻组件（轻量入口 + 直接操作） ============

// 待办收件箱速览：未确认任务，行内直接确认/忽略（信息转任务的常驻操作位）。
// 待办收件箱速览:紧凑行(一行一条),点行才展开出确认/忽略。只收真需处理的(邮件/日历),不堆新闻。
// 待办时间格式化:今天显 HH:MM,往日显 MM-DD HH:MM。
function fmtSchedWhen(ts: number): string {
  const d = new Date(ts), now = new Date();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  return sameDay ? hm : `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${hm}`;
}
const REPEAT_ZH: Record<string, string> = { daily: "每天", weekly: "每周", monthly: "每月" };
const REMIND_LEADS: { label: string; ms: number | null }[] = [
  { label: "无提醒", ms: null }, { label: "准时", ms: 0 }, { label: "提前5分", ms: 5 * 60000 },
  { label: "提前15分", ms: 15 * 60000 }, { label: "提前30分", ms: 30 * 60000 },
  { label: "提前1小时", ms: 60 * 60000 }, { label: "提前1天", ms: 24 * 60 * 60000 },
];

// 问题2:全能记事——「新建」先选类型,每种类型有专属录入界面(借鉴 open-notebook 的 Sources)。
type NoteKind = "blank" | "link" | "file" | "image" | "web";
function NoteTypePicker({ onClose, onBlank, onCreated }: { onClose: () => void; onBlank: () => void; onCreated: (id?: string) => void }) {
  const [kind, setKind] = useState<NoteKind | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const imgRef = useRef<HTMLInputElement | null>(null);

  const types: { k: NoteKind; name: string; desc: string; icon: ReactNode }[] = [
    { k: "blank", name: "空白笔记", desc: "写长文 · Markdown · 版本历史", icon: <path d="M4 4h12l4 4v12H4z M14 4v4h4" /> },
    { k: "link", name: "链接", desc: "存一个网址,自动抓标题+摘要", icon: <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /> },
    { k: "file", name: "附件", desc: "上传任意文件,落为可检索来源", icon: <path d="M21 12.5V7l-5-4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6 M14 3v5h5 M16 16l3 3 3-3 M19 19v-7" /> },
    { k: "image", name: "图片", desc: "上传/拖拽/粘贴图片,内嵌预览", icon: <path d="M4 5h16v14H4z M8 11l2.5 3 3.5-4.5L20 18" /> },
    { k: "web", name: "网页导入", desc: "抓取网页正文(reader)落为笔记", icon: <path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M3 12h18 M12 3c2.5 2.5 2.5 15.5 0 18 M12 3c-2.5 2.5-2.5 15.5 0 18" /> },
  ];

  async function importByUrl() {
    const u = url.trim(); if (!u || busy) return;
    setBusy(true); setErr("");
    try { const r = await importNoteUrl(u); if (r?.note?.id) onCreated(r.note.id); else setErr("抓取失败,检查链接"); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  async function importFile(file: File) {
    if (!file || busy) return;
    setBusy(true); setErr("");
    try {
      const r = await importNoteAttachment({ file_name: file.name, mime_type: file.type, data_base64: await fileToDataUrl(file) });
      if (r?.note?.id) onCreated(r.note.id); else setErr("上传失败");
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }

  const card: CSSProperties = { display: "grid", gap: 8, justifyItems: "start", textAlign: "left", padding: "14px 14px", borderRadius: 12, border: "1px solid var(--border)", background: "var(--panel-2)", cursor: "pointer" };
  const back = (
    <button onClick={() => { setKind(null); setErr(""); }} style={{ ...row(4), border: 0, background: "transparent", color: "var(--text-dim)", cursor: "pointer", font: "600 10.5px 'Space Grotesk'", padding: 0 }}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></svg>返回选择
    </button>
  );

  return (
    <Modal open onClose={onClose} eyebrow="记事" title="新建记事" width={640} maxHeight={560}>
      {kind === null && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {types.map((t) => (
            <button key={t.k} className="cx-lift" onClick={() => { if (t.k === "blank") { onBlank(); } else setKind(t.k); }} style={card}>
              <span style={{ width: 34, height: 34, borderRadius: 9, display: "grid", placeContent: "center", background: "var(--accent-soft)", color: "var(--accent)" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">{t.icon}</svg>
              </span>
              <b style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{t.name}</b>
              <span style={{ font: "400 10.5px/1.4 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>{t.desc}</span>
            </button>
          ))}
        </div>
      )}
      {(kind === "link" || kind === "web") && (
        <div style={{ display: "grid", gap: 12 }}>
          {back}
          <div style={{ font: "600 13px 'Space Grotesk'", color: "var(--text)" }}>{kind === "link" ? "存一个链接" : "导入网页正文"}</div>
          <input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") importByUrl(); }} placeholder="https://…" style={{ background: "var(--panel-3)", border: "1px solid var(--border)", borderRadius: 9, padding: "11px 13px", color: "var(--text)", font: "500 13px 'IBM Plex Mono',monospace", outline: "none" }} />
          <span style={{ font: "400 10.5px 'Space Grotesk'", color: "var(--text-mute)" }}>{kind === "link" ? "会抓取标题与摘要,存成一条可检索的笔记。" : "会用 reader 抓取网页正文(去广告/导航),落为笔记全文。"}</span>
          {err && <span style={{ font: "500 11px 'IBM Plex Mono'", color: "var(--bad)" }}>{err}</span>}
          <button onClick={importByUrl} disabled={busy || !url.trim()} style={{ justifySelf: "start", border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 9, padding: "9px 18px", font: "600 12px 'Space Grotesk'", opacity: busy || !url.trim() ? 0.5 : 1 }}>{busy ? "抓取中…" : "抓取并保存"}</button>
        </div>
      )}
      {(kind === "file" || kind === "image") && (
        <div style={{ display: "grid", gap: 12 }}>
          {back}
          <div style={{ font: "600 13px 'Space Grotesk'", color: "var(--text)" }}>{kind === "image" ? "上传图片" : "上传附件"}</div>
          <input ref={kind === "image" ? imgRef : fileRef} type="file" accept={kind === "image" ? "image/*" : undefined} style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); }} />
          <button onClick={() => (kind === "image" ? imgRef : fileRef).current?.click()} disabled={busy}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) importFile(f); }}
            style={{ display: "grid", gap: 8, placeItems: "center", padding: "34px 16px", borderRadius: 12, border: "1.5px dashed var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer" }}>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 16V4 M7 9l5-5 5 5 M5 20h14" /></svg>
            <span style={{ font: "500 12px 'Space Grotesk'" }}>{busy ? "上传中…" : (kind === "image" ? "点击或拖拽图片到此" : "点击或拖拽文件到此")}</span>
          </button>
          {err && <span style={{ font: "500 11px 'IBM Plex Mono'", color: "var(--bad)" }}>{err}</span>}
        </div>
      )}
    </Modal>
  );
}

function NotesTodoPanel({ notes, onSaved, onOpen, onAdd }: { notes: PersonalNote[]; onSaved: () => void; onOpen: (id?: string) => void; onAdd: () => void }) {
  const [tab, setTab] = useState<"待办" | "记事">("待办");
  // 记事录入
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  // 待办=真日程
  const [sched, setSched] = useState<ScheduleItem[]>([]);
  const [caldav, setCaldav] = useState<CalDavStatus | null>(null);
  const freshDate = () => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`; };
  const freshTime = () => { const n = new Date(); return `${String((n.getHours() + 1) % 24).padStart(2, "0")}:00`; };
  const [sdate, setSdate] = useState(freshDate);
  const [stime, setStime] = useState(freshTime);
  const [srepeat, setSrepeat] = useState("none");
  const [slead, setSlead] = useState(1); // 默认"准时"
  const [stitle, setStitle] = useState("");

  const loadSched = () => getSchedule("pending").then((d) => setSched(d.items || [])).catch(() => {});
  useEffect(() => {
    loadSched();
    getCalDavStatus().then(setCaldav).catch(() => {});
    const stop = subscribeNotify(() => loadSched());
    return () => stop();
  }, []);

  async function addNote() {
    const t = text.trim(); if (!t || saving) return;
    setSaving(true);
    try { await createNote({ title: t.slice(0, 40), content: t, tags: [] }); setText(""); onSaved(); }
    catch { alert("记事创建失败，请重试"); } finally { setSaving(false); }
  }
  async function addSched() {
    const t = stitle.trim(); if (!t || saving) return;
    const start = Date.parse(`${sdate}T${stime}`);
    if (!start || Number.isNaN(start)) return;
    const lead = REMIND_LEADS[slead]?.ms;
    const remind_ts = lead == null ? null : start - lead;
    setSaving(true);
    try {
      await createSchedule({ title: t, start_ts: start, remind_ts, repeat: srepeat });
      setStitle(""); loadSched();
    } catch { alert("日程创建失败，请重试"); } finally { setSaving(false); }
  }
  async function toggleDone(it: ScheduleItem) { try { await scheduleDone(it.id, true); } catch { alert("操作失败"); } loadSched(); }
  async function removeSched(id: string) { try { await deleteSchedule(id); } catch { alert("删除失败"); } loadSched(); }

  const inp: CSSProperties = { flex: "none", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 8px", color: "var(--text)", font: "500 11px 'IBM Plex Mono',monospace", outline: "none" };
  const sel: CSSProperties = { ...inp, cursor: "pointer", font: "600 10.5px 'Space Grotesk'" };

  return (
    <div style={{ ...panel, display: "grid", gridTemplateRows: "auto auto minmax(0,1fr)", minHeight: 0, gap: 10, animation: "cxRise .84s ease both" }}>
      <div style={{ ...row(8) }}>
        <div style={{ flex: "none", display: "flex", gap: 4, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: 3 }}>
          {(["待办", "记事"] as const).map((f) => (<button key={f} onClick={() => setTab(f)} style={{ border: 0, cursor: "pointer", font: "600 11px 'Space Grotesk',sans-serif", padding: "5px 12px", borderRadius: 6, color: tab === f ? "#fff" : "var(--text-dim)", background: tab === f ? "var(--accent)" : "transparent", transition: "all .15s" }}>{f}</button>))}
        </div>
        {/* 待办:CalDAV 同步状态徽标 */}
        {tab === "待办" && caldav?.configured && <span title={`同步到 ${caldav.url_host || "CalDAV"} 日历`} style={{ ...row(4), font: "600 9px 'IBM Plex Mono'", color: "var(--good)" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", display: "inline-block" }} />同步中</span>}
        <span style={flex1} />
        {tab === "记事" && (
          <button onClick={onAdd} title="新建记事(空白/链接/附件/图片/网页)" className="cx-navtip" data-tip="新建记事" style={{ ...row(5), border: "1px solid var(--accent)", background: "var(--accent-soft)", color: "var(--accent)", cursor: "pointer", borderRadius: 8, padding: "5px 10px", font: "600 10.5px 'Space Grotesk'" }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>新建
          </button>
        )}
        <span style={mono(9)}>{tab === "待办" ? sched.length : notes.length}</span>
      </div>

      {/* 录入区 */}
      {tab === "待办" ? (
        <div style={{ display: "grid", gap: 6 }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <input type="date" value={sdate} onChange={(e) => setSdate(e.target.value)} onFocus={() => { if (sdate < freshDate()) setSdate(freshDate()); }} style={{ ...inp, width: 124 }} />
            <input type="time" value={stime} onChange={(e) => setStime(e.target.value)} style={{ ...inp, width: 86 }} />
            <select value={srepeat} onChange={(e) => setSrepeat(e.target.value)} style={sel}>
              <option value="none">不重复</option><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option>
            </select>
            <select value={slead} onChange={(e) => setSlead(Number(e.target.value))} style={sel}>
              {REMIND_LEADS.map((r, i) => <option key={i} value={i}>{r.label}</option>)}
            </select>
          </div>
          <div style={{ ...row(7) }}>
            <input value={stitle} onChange={(e) => setStitle(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addSched(); }} placeholder="待办内容，回车添加（带时间/提醒/重复）" style={{ flex: 1, minWidth: 0, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px", color: "var(--text)", font: "400 12.5px 'Space Grotesk',sans-serif", outline: "none" }} />
            <button onClick={addSched} disabled={saving || !stitle.trim()} style={{ flex: "none", border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "7px 13px", font: "600 11px 'Space Grotesk'", opacity: saving || !stitle.trim() ? 0.5 : 1 }}>＋</button>
          </div>
        </div>
      ) : (
        <div style={{ ...row(7) }}>
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addNote(); }} placeholder="记一笔，回车保存" style={{ flex: 1, minWidth: 0, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px", color: "var(--text)", font: "400 12.5px 'Space Grotesk',sans-serif", outline: "none" }} />
          <button onClick={addNote} disabled={saving || !text.trim()} style={{ flex: "none", border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "7px 13px", font: "600 11px 'Space Grotesk'", opacity: saving || !text.trim() ? 0.5 : 1 }}>＋</button>
        </div>
      )}

      {/* 列表区 */}
      <div style={{ display: "grid", gap: 7, overflowY: "auto", minHeight: 0, alignContent: "start" }}>
        {tab === "待办" ? (
          <>
            {sched.length === 0 && <div style={{ ...mono(10.5), padding: "6px 2px", lineHeight: 1.6 }}>暂无待办。上面填时间、提醒、重复，加一条。{caldav && !caldav.configured && <><br /><span style={{ color: "var(--text-mute)" }}>本地日程已开启 · 配置 CalDAV 可同步到手机日历/提醒</span></>}</div>}
            {sched.map((it) => (
              <div key={it.id} className="cx-row" style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 6px", borderRadius: 8 }}>
                <button onClick={() => toggleDone(it)} title="标记完成" style={{ width: 16, height: 16, borderRadius: 5, border: "1.5px solid var(--accent)", flex: "none", background: "transparent", cursor: "pointer", padding: 0 }} />
                <div style={{ minWidth: 0, flex: 1, display: "grid", gap: 1 }}>
                  <span style={{ font: "500 12px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.title}</span>
                  <span style={{ ...row(6), font: "500 9px 'IBM Plex Mono',monospace", color: it.overdue ? "var(--bad)" : "var(--text-mute)" }}>
                    <span>{fmtSchedWhen(it.start_ts)}</span>
                    {it.remind_ts != null && <span style={{ ...row(2) }}><svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>提醒</span>}
                    {it.repeat && it.repeat !== "none" && <span style={{ ...row(2) }}><svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 2l4 4-4 4" /><path d="M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4" /><path d="M21 13v1a4 4 0 0 1-4 4H3" /></svg>{REPEAT_ZH[it.repeat]}</span>}
                    {caldav?.configured && (it as any).remote_href && <span title="已同步到日历" style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", display: "inline-block" }} />}
                  </span>
                </div>
                <button onClick={() => removeSched(it.id)} title="删除" className="cx-del" style={{ flex: "none", border: 0, background: "transparent", color: "var(--text-mute)", cursor: "pointer", padding: 2, opacity: 0.5 }}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12" /></svg></button>
              </div>
            ))}
          </>
        ) : (
          <>
            {notes.length === 0 && <div style={{ ...mono(10.5), padding: "6px 2px", lineHeight: 1.6 }}>暂无记事，上面记一笔，或点「新建」选链接/附件/图片/网页。</div>}
            {notes.slice(0, 6).map((nt) => (
              <button key={nt.id} onClick={() => onOpen(nt.id)} className="cx-row" style={{ textAlign: "left", background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: 10, padding: "8px 10px", display: "grid", gap: 2, cursor: "pointer" }}>
                <div style={{ ...row(6) }}>{nt.pinned && <svg width="9" height="9" viewBox="0 0 24 24" fill="var(--accent)"><path d="M9 4v6l-2 3v2h10v-2l-2-3V4z" /><path d="M12 17v3" stroke="var(--accent)" strokeWidth="2" /></svg>}<b style={{ font: "600 11px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{nt.title || "未命名"}</b><span style={{ font: "500 8px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>{nt.updated_ts ? fmtAgo(nt.updated_ts) : ""}</span></div>
                <p style={{ margin: 0, font: "400 9.5px/1.4 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{nt.excerpt || nt.content || ""}</p>
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// 感知接入入口（首页常驻，密集 chip，一点即授权读取并投喂）。
function SensePreview({ goSense }: { goSense: () => void }) {
  const [st, setSt] = useState<Record<string, { status: string; fed?: string }>>(() => loadSenseState());
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { const h = (e: Event) => setSt((((e as CustomEvent).detail) || loadSenseState())); window.addEventListener("cx-sense-change", h); return () => window.removeEventListener("cx-sense-change", h); }, []);
  const run = async (ch: SenseChannel) => {
    setBusy(ch.id);
    try {
      const r: SenseResult = await ch.connect();
      let fed: string | undefined;
      if (r.status === "connected") { const ing = await ingestSensed(ch, r); fed = ing.ok ? `已投喂 ${ing.accepted ?? 0}` : "未投喂"; }
      saveSenseStatus(ch.id, { status: r.status, fed, summary: r.summary, details: r.details, thumb: r.thumb, metrics: r.metrics, ts: Date.now() });
    } finally { setBusy(null); }
  };
  const tone = (s?: string) => s === "connected" ? "var(--good)" : s === "denied" ? "var(--bad)" : s === "unsupported" ? "var(--text-mute)" : "var(--warn)";
  return (
    <div style={{ ...panel, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, animation: "cxRise .9s ease both" }}>
      <div style={{ ...row(8), marginBottom: 11 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.9"><path d="M12 12a1.5 1.5 0 1 0 0-.01" /><path d="M8.5 8.5a5 5 0 0 1 7 0M5.6 5.6a9 9 0 0 1 12.8 0" /><path d="M9 15.5a4 4 0 0 0 6 0" /></svg>
        <span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>感知接入</span>
        <span style={flex1} />
        <button onClick={goSense} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", font: "500 10px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>全部 →</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, overflowY: "auto", minHeight: 0, alignContent: "start" }}>
        {SENSE_CHANNELS.map((ch) => { const s = st[ch.id]; const ok = ch.isSupported(); return (
          <button key={ch.id} onClick={() => ok && run(ch)} disabled={!ok || busy === ch.id} title={ch.reads} className="cx-lift" style={{ textAlign: "left", border: "1px solid var(--border-soft)", background: "var(--panel-2)", borderRadius: 10, padding: "9px 10px", display: "grid", gap: 6, cursor: ok && busy !== ch.id ? "pointer" : "default", opacity: ok ? 1 : 0.5 }}>
            <div style={{ ...row(7) }}><span style={{ color: "var(--accent)", display: "grid", placeContent: "center" }}>{senseIcon(ch.icon)}</span><b style={{ font: "600 11px 'Space Grotesk',sans-serif", color: "var(--text)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ch.name}</b><span style={{ width: 6, height: 6, borderRadius: "50%", background: tone(s?.status), flex: "none" }} /></div>
            <span style={{ font: "500 9px 'IBM Plex Mono',monospace", color: s?.fed ? "var(--good)" : "var(--text-mute)" }}>{busy === ch.id ? "读取中…" : s?.fed || (ok ? "点击授权" : "不支持")}</span>
          </button>
        ); })}
      </div>
    </div>
  );
}

// 资讯情报抽屉：复用右抽屉骨架 + 把内联 feed 行提上来，吃 Cockpit 已有的 news/signalCount（不新增轮询）。
function IntelFeedDrawer({ items, total, pstyle, catColor, onOpenItem, goIntel, onClose }: {
  items: BriefItem[]; total: number; pstyle: (p?: string) => [string, string]; catColor: Record<string, string>;
  onOpenItem: (id: string) => void; goIntel: () => void; onClose: () => void;
}) {
  const feed = items.slice(0, 30);
  const footer = (
    <div style={{ ...row(8) }}>
      <span style={{ font: "500 10px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>点任意条目看 Jarvis 的判读与来源</span>
      <span style={flex1} />
      <button onClick={goIntel} className="cx-link" style={{ border: 0, background: "transparent", cursor: "pointer", font: "500 10px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>情报中心 →</button>
    </div>
  );
  return (
    <Drawer open onClose={onClose} footer={footer}
      title={<span style={{ ...row(6) }}>实时情报 <span style={{ ...row(4), font: "600 9px 'IBM Plex Mono',monospace", color: "var(--good)" }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 3s ease infinite" }} />直播 {total}</span></span>}>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "11px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
          {feed.length === 0 && <div style={{ ...mono(11), padding: "16px 0", textAlign: "center" }}>正在接入情报流…</div>}
          {feed.map((it, i) => { const [pf, pb] = pstyle(it.priority); const cat = (it as { category?: string }).category; const ac = (cat && catColor[cat]) || (it.priority === "高优先" ? "var(--bad)" : "var(--accent)"); return (
            <button key={it.event_id || i} onClick={() => { if (it.event_id) onOpenItem(it.event_id); }} className="cx-feed cx-lift" style={{ flexShrink: 0, textAlign: "left", width: "100%", border: "1px solid var(--border-soft)", background: "var(--panel-2)", cursor: "pointer", display: "flex", flexDirection: "column", gap: 4, padding: "10px 13px 10px 15px", borderRadius: 12, position: "relative", overflow: "hidden" }}>
              <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: ac }} />
              <div style={{ ...row(7), flexWrap: "wrap" }}>
                <span style={{ font: "600 8px 'IBM Plex Mono',monospace", color: pf, background: pb, borderRadius: 999, padding: "2px 7px" }}>{it.priority || "观察"}</span>
                {cat && <span style={{ font: "600 8px 'IBM Plex Mono',monospace", color: ac, background: "var(--panel-3)", borderRadius: 999, padding: "2px 7px" }}>{cat}</span>}
                <span style={{ font: "500 9px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>{it.source || ""} · {tsToTime(it.ts)}</span>
                <span style={flex1} />
                {typeof it.score === "number" && <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>相关 {it.score.toFixed(0)}</span>}
              </div>
              <b style={{ display: "block", font: "600 13px/1.42 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", maxHeight: "2.84em", wordBreak: "break-word" }}>{it.title || "（无标题）"}</b>
              {it.take && <div style={{ font: "400 11px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.take}</div>}
            </button>
          ); })}
        </div>
    </Drawer>
  );
}

function Cockpit({ themeMode, goIntel, goNotes, goAgents, goSense, goDevices }: { themeMode: Theme; goIntel: () => void; goNotes: (id?: string) => void; goAgents: () => void; goSense: () => void; goDevices: () => void }) {
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
  const [chatOpen, setChatOpen] = useState(false);  // 点动态头像呼出 Jarvis 对话气泡
  const [detailId, setDetailId] = useState<string | null>(null);
  const [intelOpen, setIntelOpen] = useState(false);  // 资讯情报抽屉
  const [mailRect, setMailRect] = useState<DOMRect | null>(null);  // hero 快速入口的邮件气泡锚点
  const [inboxCardOpen, setInboxCardOpen] = useState(false);  // 收件箱大卡片(问题6)
  const [reportCardOpen, setReportCardOpen] = useState(false);  // 日报大卡片(问题5)
  const [inboxCount, setInboxCount] = useState(0);
  const [overlay, setOverlay] = useState<{ open: boolean; id?: string }>({ open: false });
  const [noteTypePick, setNoteTypePick] = useState(false);  // 问题2:新建记事类型选择器

  const reloadNotes = () => { getNotes().then((d) => setNotes(Array.isArray(d?.notes) ? d.notes : [])).catch(() => {}); };
  useEffect(() => {
    let live = true;
    const clock = setInterval(() => setNow(new Date()), 1000);
    // 推送驱动 + 兜底慢轮询：实时事件来了立即刷新，否则按更长间隔兜底（降轮询压力）。
    const pull = () => { getServices().then((d) => { if (live && Array.isArray(d)) setServices(d); }).catch(() => {}); getSystemOverview().then((d) => { if (live) setOverview(d); }).catch(() => {}); };
    pull(); const t = setInterval(pull, 30000);              // 10s → 30s（推送会即时补刷）
    const pullBrief = () => getBriefing().then((d) => { if (live) setBrief(d); }).catch(() => {});
    pullBrief(); const tb = setInterval(pullBrief, 120000);  // 60s → 120s（情报命中走推送即时刷）
    const pullSess = () => getCliSessions().then((d) => { if (live) { setSessions(d.sessions || []); setExternal(d.external || []); } }).catch(() => {});
    pullSess(); const tsv = setInterval(pullSess, 6000);     // 4s → 6s
    reloadNotes();
    const pullInbox = () => getInbox("unconfirmed").then((d) => { if (live) setInboxCount((d.counts?.unconfirmed ?? d.tasks?.length) || 0); }).catch(() => {});
    pullInbox(); const ti = setInterval(pullInbox, 30000);
    getNotifications().then((d) => { if (live) setNotifApps(Array.isArray(d?.apps) ? d.apps : []); }).catch(() => {});
    const tn = setInterval(() => { getNotifications().then((d) => { if (live) setNotifApps(Array.isArray(d?.apps) ? d.apps : []); }).catch(() => {}); }, 30000);
    // 实时推送：情报命中/系统告警 → 立即刷新简报与系统态，不等下一个轮询周期。
    const stopNotify = subscribeNotify(() => { if (!live) return; pullBrief(); pull(); });
    // 天气城市取高德配置的 home_city（config/settings.toml [amap].home_city），未配置时回退深圳。
    let wxCity = "深圳";
    const loadWx = () => getAmapWeather(wxCity).then((wd) => { if (live && wd?.ok) setWx(wd); }).catch(() => {});
    getAmapConfig().then((c) => { if (live && c?.home_city) wxCity = c.home_city; loadWx(); }).catch(() => loadWx());
    const tw = setInterval(loadWx, 600000);
    ["天秤", "双鱼", "双子"].forEach((s) => getHoroscope(s).then((d) => { if (live && d?.ok) setHoros((p) => ({ ...p, [s]: d })); }).catch(() => {}));
    return () => { live = false; clearInterval(clock); clearInterval(t); clearInterval(tb); clearInterval(tsv); clearInterval(tn); clearInterval(tw); clearInterval(ti); stopNotify(); };
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
  const news = briefingMainFeed(allItems);
  const totalUnread = notifApps.reduce((a, b) => a + (typeof b.count === "number" ? b.count : 0), 0);
  const signalCount = brief?.counts?.total ?? news.length;
  const runningNow = sessions.filter((s) => s.status === "running").length + external.length;  // 含常驻网关(Hermes/OpenClaw)
  const briefLines = synthBrief({ news, services, svcTotal: services.length, svcOnline, health, ssd: ssdPct, ram: ramPct, cpu: cpuPct, unread: totalUnread, running: runningNow, sigCount: signalCount });

  // 情报抽屉用：优先级配色 + 分类配色（首页内联情报面板已收进抽屉）。
  const pstyle = (p?: string): [string, string] => PRI[p || "观察"] || PRI["观察"];
  const catColor: Record<string, string> = { AI科技: "var(--info)", 财经: "var(--warn)", 军事: "var(--bad)", 科技: "var(--good)", 中文科技: "var(--cat-purple)", 开发: "var(--cat-teal)", 综合资讯: "var(--text-dim)", X社媒: "var(--accent-2)" };

  return (
    <div className="cx-page" style={{ position: "relative", height: "100%", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", gap: 18, padding: "16px 20px", minHeight: 0 }}>
      <style>{"@keyframes cxSlideIn{from{transform:translateX(28px);opacity:.4}to{transform:translateX(0);opacity:1}}@keyframes cxFade{from{opacity:0}to{opacity:1}}"}</style>

      {/* ROW 1 — 中枢综述 / 核心 / 时间天气健康（限高，保证下方工作区拿到稳定空间、不被撑出视口）*/}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 268px 240px", gap: 20, alignItems: "stretch", maxHeight: "40vh", minHeight: 0 }}>
        <div style={{ animation: "cxRiseL .5s ease both", display: "flex", flexDirection: "column", justifyContent: "center", minWidth: 0 }}>
          <div style={{ ...row(14), marginBottom: 4 }}>
            <span style={{ font: "600 9px 'IBM Plex Mono',monospace", letterSpacing: ".24em", color: "var(--accent)" }}>中枢综述</span>
            <span style={{ font: "500 9px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--text-mute)" }}>{now.getFullYear()}.{pad(now.getMonth() + 1)}.{pad(now.getDate())}</span>
            {/* 信号/未读/服务改成有呼吸的独立小块，去掉一行四五个中点的 tell */}
            <span style={{ ...row(5), font: "500 9px 'IBM Plex Mono',monospace", color: "var(--good)" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", display: "inline-block", animation: "cxBreathe 2.6s ease infinite" }} />在线</span>
            <span style={{ display: "flex", gap: 14, font: "500 9px 'IBM Plex Mono',monospace", color: "var(--text-mute)" }}>
              <span>信号 <b style={{ color: "var(--text-dim)" }}>{signalCount}</b></span>
              <span>未读 <b style={{ color: totalUnread > 0 ? "var(--bad)" : "var(--text-dim)" }}>{totalUnread}</b></span>
              <span>服务 <b style={{ color: "var(--text-dim)" }}>{svcOnline}</b></span>
            </span>
          </div>
          <h1 style={{ margin: "0 0 3px", font: "600 21px/1.05 'Space Grotesk',sans-serif", letterSpacing: "-.02em", color: "var(--text)" }}>{greet}，Leo<span style={{ color: "var(--accent)", animation: "cxGlowText 4s ease infinite" }}>.</span></h1>
          <div style={{ display: "grid", gap: 0, maxWidth: 760 }}>
            {briefLines.length === 0 && <div style={{ ...mono(11), padding: "4px 0" }}>正在综合今日情报…</div>}
            {briefLines.map((b) => (
              <button key={b.idx} onClick={() => { if (b.id) setDetailId(b.id); }} className="cx-row" title={`${b.topic}：${b.detail}`} style={{ textAlign: "left", border: 0, background: "transparent", cursor: b.id ? "pointer" : "default", display: "flex", alignItems: "center", gap: 9, padding: "1px 8px", borderRadius: 6 }}>
                {/* 去掉 01/02 编号 tell：状态点(语义色) + 标题本身即标签 */}
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: b.tone, flex: "none", boxShadow: `0 0 5px ${b.tone}` }} />
                <span style={{ minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", lineHeight: 1.35 }}><b style={{ font: "600 11.5px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{b.topic}</b><span style={{ font: "400 11px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>　{b.detail}</span></span>
              </button>
            ))}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 5, alignItems: "center" }}>
            <button onClick={goIntel} className="cx-chip" style={{ border: 0, cursor: "pointer", background: "var(--accent)", color: "#fff", font: "600 12px 'Space Grotesk'", padding: "6px 13px", borderRadius: 8, boxShadow: "0 6px 18px var(--accent-soft)" }}>读完整简报 →</button>
            <button onClick={() => goNotes()} className="cx-chip" style={{ border: "1px solid var(--border)", cursor: "pointer", background: "var(--panel)", color: "var(--text)", font: "600 12px 'Space Grotesk'", padding: "7px 14px", borderRadius: 8 }}>＋ 记一笔</button>
            <span style={{ width: 1, height: 18, background: "var(--border)", margin: "0 1px" }} />
            {/* 快速入口:从右下角收进 hero CTA 行,接在记一笔后面。chip 紧凑、超出换行。 */}
            {(() => {
              const Chip = ({ icon, label, meta, metaColor, dot, onClick }: { icon: ReactNode; label: string; meta?: string; metaColor?: string; dot?: string; onClick: (e: React.MouseEvent) => void }) => (
                <button onClick={onClick} className="cx-chip" style={{ ...row(6), border: "1px solid var(--border)", cursor: "pointer", background: "var(--panel-2)", color: "var(--text-dim)", font: "600 11.5px 'Space Grotesk'", padding: "6px 11px", borderRadius: 8 }}>
                  <span style={{ color: "var(--accent)", display: "grid", placeContent: "center", flex: "none" }}>{icon}</span>{label}
                  {dot && <span style={{ width: 5, height: 5, borderRadius: "50%", background: dot, flex: "none" }} />}
                  {meta && <span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: metaColor || "var(--text-mute)", flex: "none" }}>{meta}</span>}
                </button>
              );
              return (<>
                <Chip onClick={() => setIntelOpen(true)} label="情报" meta={`${signalCount}`}
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12l6-6" /></svg>} />
                <Chip onClick={goAgents} label="智能体" meta={runningNow > 0 ? `${runningNow}` : undefined} metaColor="var(--good)" dot={runningNow > 0 ? "var(--good)" : undefined}
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="5" r="2.4" /><circle cx="5.5" cy="18" r="2.4" /><circle cx="18.5" cy="18" r="2.4" /><path d="M12 7.4v3M11 12l-4 4M13 12l4 4" /></svg>} />
                <Chip onClick={(e) => setMailRect(mailRect ? null : e.currentTarget.getBoundingClientRect())} label="邮件 & 应用" meta={totalUnread > 0 ? `${totalUnread}` : undefined} metaColor="var(--bad)"
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M4 7l8 6 8-6" /></svg>} />
                <Chip onClick={goDevices} label="设备"
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M2 20h20M9 16v4M15 16v4" /></svg>} />
                <Chip onClick={() => setReportCardOpen(true)} label="日报"
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 3h11l3 3v15H5z" /><path d="M8.5 11h7M8.5 14.5h7M8.5 18h4" /></svg>} />
                <Chip onClick={() => setInboxCardOpen(true)} label="收件箱" meta={inboxCount > 0 ? `${inboxCount}` : undefined} metaColor="var(--accent)" dot={inboxCount > 0 ? "var(--accent)" : undefined}
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 13h5l2 3h4l2-3h5" /><path d="M5 5h14l2 8v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4z" /></svg>} />
              </>);
            })()}
          </div>
          {/* 今日概览统计条已并入「综述」标注行 + 右栏 + 各面板，避免重复、压缩首屏高度 */}
        </div>
        <CoreOrb online={svcOnline > 0} onClick={() => setChatOpen(true)} />
        <div style={{ display: "grid", gap: 6, alignContent: "center", paddingRight: 18, animation: "cxRise .7s ease both" }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ font: "700 29px/1 'Space Grotesk',sans-serif", color: "var(--text)", letterSpacing: "-.01em" }}>{pad(now.getHours())}:{pad(now.getMinutes())}<span style={{ font: "600 13px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>:{pad(now.getSeconds())}</span></div>
            <div style={{ font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--text-mute)", marginTop: 2 }}>{now.getMonth() + 1}月{now.getDate()}日 {week}　{greet}</div>
          </div>
          {/* 生活/个人区（天气+星座，柔性 Space Grotesk）—— 与下方系统态（技术 mono）分开 register，
              不再让玄学数字和 CPU/RAM 挤一条。 */}
          <div style={{ display: "grid", gap: 5, justifyItems: "end", padding: "7px 9px", background: "var(--panel)", border: "1px solid var(--border-soft)", borderRadius: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ fontSize: 19, lineHeight: 1 }}>{wxEmoji(wx?.weather)}</span><span style={{ font: "700 16px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{wx?.ok ? `${wx.temperature}°` : "—"}</span><span style={{ font: "500 10.5px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>{wx?.city || "—"}　{wx?.weather || "—"}</span>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              {["天秤", "双鱼", "双子"].map((s) => { const h = horos[s]; const sc = typeof h?.score === "number" ? h.score : null; const tn = sc == null ? "var(--text-mute)" : sc >= 75 ? "var(--good)" : sc >= 45 ? "var(--warn)" : "var(--bad)"; return <span key={s} title={h?.advice || ""} style={{ ...row(4), font: "500 10px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}><b style={{ width: 5, height: 5, borderRadius: "50%", background: tn, display: "inline-block", boxShadow: `0 0 5px ${tn}` }} />{s} <b style={{ color: "var(--text)" }}>{sc ?? "—"}</b></span>; })}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, marginTop: 1 }}>
            <div style={{ position: "relative", width: 34, height: 34, flex: "none" }}>
              <svg width="34" height="34" viewBox="0 0 34 34" style={{ transform: "rotate(-90deg)" }}><circle cx="17" cy="17" r="14" fill="none" stroke="var(--border)" strokeWidth="3.5" /><circle cx="17" cy="17" r="14" fill="none" stroke="var(--accent)" strokeWidth="3.5" strokeLinecap="round" strokeDasharray="87.96" strokeDashoffset={health != null ? +(87.96 * (1 - health / 100)).toFixed(1) : 87.96} style={{ filter: "drop-shadow(0 0 4px var(--accent-line))", transition: "stroke-dashoffset .6s" }} /></svg>
              <div style={{ position: "absolute", inset: 0, display: "grid", placeContent: "center", font: "700 11px 'Space Grotesk'", color: "var(--text)" }}>{health ?? "—"}</div>
            </div>
            <div style={{ display: "grid", gap: 3, textAlign: "right" }}>
              <span style={{ font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--text-mute)", letterSpacing: ".08em" }}>系统健康</span>
              <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", font: "500 9.5px 'IBM Plex Mono',monospace", color: "var(--text-dim)" }}><span>CPU <b style={{ color: "var(--text)" }}>{cpuPct ?? "—"}%</b></span><span>RAM <b style={{ color: "var(--text)" }}>{ramPct ?? "—"}%</b></span><span>SSD <b style={{ color: "var(--warn)" }}>{ssdPct ?? "—"}%</b></span></div>
            </div>
          </div>
        </div>
      </div>

      {chatOpen && <JarvisChat onClose={() => setChatOpen(false)} />}

      {/* 工作区:上排 记事 + 感知(收窄);下排 = agent 多会话工作区(占满横向、给足终端高度,问题5)。整体不溢出视口。*/}
      <div style={{ display: "grid", gridTemplateRows: "minmax(0,0.78fr) minmax(0,1.5fr)", gap: 14, minHeight: 0, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 300px", gap: 14, minHeight: 0, overflow: "hidden" }}>
          <NotesTodoPanel notes={notes} onSaved={reloadNotes} onOpen={(id) => setOverlay({ open: true, id })} onAdd={() => setNoteTypePick(true)} />
          <SensePreview goSense={goSense} />
        </div>
        <AgentWorkspace goAgents={goAgents} themeMode={themeMode} />
      </div>

      {/* 邮件 & 应用气泡(锚在 hero 快速入口的「邮件」chip):Popover portal 到 body,不被裁切。 */}
      <Popover open={!!mailRect} onClose={() => setMailRect(null)} anchor={mailRect} width={260}>
        <div style={{ ...row(8), padding: "2px 6px 6px" }}><span style={mono(9, "var(--accent)")}>应用通知</span><span style={flex1} /><button onClick={() => setMailRect(null)} style={{ border: 0, background: "transparent", cursor: "pointer", color: "var(--text-mute)", font: "600 13px 'Space Grotesk'" }}>×</button></div>
        {notifApps.length === 0 && <div style={{ ...mono(10), padding: "6px" }}>暂无通知</div>}
        {[...notifApps].sort((a, b) => (b.count || 0) - (a.count || 0)).slice(0, 8).map((a) => (
          <button key={a.id} onClick={() => { openApp(a.name || a.id).catch(() => {}); setMailRect(null); }} className="cx-row" style={{ textAlign: "left", border: 0, background: "transparent", cursor: "pointer", display: "flex", alignItems: "center", gap: 9, padding: "6px 7px", borderRadius: 8, width: "100%" }}>
            <AppIcon a={a} size={20} />
            <span style={{ font: "500 11.5px 'Space Grotesk',sans-serif", color: "var(--text)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name || a.id}</span>
            {(a.count || 0) > 0 && <span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "#fff", background: "var(--bad)", borderRadius: 999, padding: "1px 7px" }}>{a.count}</span>}
          </button>
        ))}
      </Popover>

      {inboxCardOpen && <InboxCard onClose={() => setInboxCardOpen(false)} />}
      {reportCardOpen && <ReportCard onClose={() => setReportCardOpen(false)} />}
      {detailId && <IntelDetail id={detailId} onClose={() => setDetailId(null)} />}
      {intelOpen && <IntelFeedDrawer items={news} total={signalCount} pstyle={pstyle} catColor={catColor} onOpenItem={(id) => setDetailId(id)} goIntel={goIntel} onClose={() => setIntelOpen(false)} />}
      {overlay.open && <NotesOverlay openId={overlay.id} onClose={() => { setOverlay({ open: false }); reloadNotes(); }} goFull={(id) => { setOverlay({ open: false }); goNotes(id); }} />}
      {noteTypePick && <NoteTypePicker
        onClose={() => setNoteTypePick(false)}
        onBlank={() => { setNoteTypePick(false); setOverlay({ open: true }); }}
        onCreated={(id) => { setNoteTypePick(false); reloadNotes(); setOverlay({ open: true, id }); }}
      />}
    </div>
  );
}


// ============ AGENTS（P9 重构）============
// 真实交互终端：xterm.js ←→ 后端 PTY（/ws/term）。在这里跑的是 agent 的**原生 REPL**，
// 所以 claude 的 /model、/cost、/clear 这些原生斜杠命令会真实弹出、完整执行 —— 不是假壳。
const PTY_CAPABLE = ["claude", "codex", "cursor", "grok", "hermes", "openclaw", "shell"];
// PtyTerminal 已抽到 ./PtyTerminal.tsx 并在文件顶部 React.lazy 懒加载。

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
  const [termMode, setTermMode] = useState<"pty" | "task" | "runs">("pty");  // E2: 默认进真实交互终端；runs=受控执行台(M4)
  const [ptyKey, setPtyKey] = useState(0);                          // ++ = 重启 PTY 会话
  const termRef = useRef<HTMLPreElement | null>(null);
  const promptVoice = useWhisperRecorder({
    prompt: "LeoJarvis Agent 快速任务",
    onText: (text) => setPrompt((prev) => prev.trim() ? `${prev.trim()}\n${text}` : text),
    onError: (message) => setErr(`语音识别失败：${message}`),
  });
  const centerVoice = useWhisperRecorder({
    prompt: "LeoJarvis Agent 中央指令",
    onText: (text) => setCenterCmd((prev) => prev.trim() ? `${prev.trim()}\n${text}` : text),
    onError: (message) => setErr(`语音识别失败：${message}`),
  });

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
  const tagOf = (a: string): [string, string] => TAG[a] || [a.slice(0, 2).toUpperCase(), "var(--text-dim)"];
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
          <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>编排台</div>
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
            <button onClick={promptVoice.toggle} disabled={busy || promptVoice.transcribing} title="Whisper 语音输入" style={{ border: "1px solid var(--border)", cursor: busy || promptVoice.transcribing ? "default" : "pointer", background: promptVoice.recording ? "var(--bad)" : "var(--panel-3)", color: promptVoice.recording ? "#fff" : "var(--text-dim)", font: "600 10.5px 'Space Grotesk'", padding: "6px 10px", borderRadius: 7, opacity: busy || promptVoice.transcribing ? 0.55 : 1 }}>{promptVoice.transcribing ? "转写" : promptVoice.recording ? "停止" : "语音"}</button>
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
            {([["pty", "交互终端"], ["task", "任务流"], ["runs", "执行台"]] as const).map(([m, label]) => (
              <button key={m} onClick={() => setTermMode(m)} style={{ border: 0, cursor: "pointer", borderRadius: 7, padding: "5px 13px", font: "600 11px 'Space Grotesk',sans-serif", background: termMode === m ? "var(--accent)" : "transparent", color: termMode === m ? "#fff" : "var(--text-dim)", transition: "all .15s" }}>{label}</button>
            ))}
          </div>
          <span style={flex1} />
          {termMode === "runs" ? (
            <span style={{ ...row(5), flex: "none", font: "600 9.5px 'IBM Plex Mono',monospace", color: "var(--text-dim)" }}>受控执行 · 计划→确认→审计</span>
          ) : termMode === "pty" ? (
            <div style={{ ...row(8) }}>
              {(() => { const [tg, fg] = tagOf(ptyAgent); return <span style={{ ...row(5), font: "600 11px 'IBM Plex Mono',monospace", color: "var(--text-dim)" }}><b style={{ color: fg, fontWeight: 700 }}>{tg}</b>{ptyLabel} · 原生 REPL</span>; })()}
              <button onClick={() => setPtyKey((k) => k + 1)} title="重启这个交互会话（清空并重新启动 agent）" className="cx-chip" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", cursor: "pointer", borderRadius: 7, padding: "5px 11px", ...mono(9.5, "var(--text-dim)") }}>重启</button>
            </div>
          ) : cur ? (
            <span style={{ ...row(5), flex: "none", font: "600 9.5px 'IBM Plex Mono',monospace", color: cur.status === "running" ? "var(--good)" : "var(--text-mute)" }}><b style={{ width: 7, height: 7, borderRadius: "50%", background: cur.status === "running" ? "var(--good)" : "var(--text-mute)", display: "inline-block", boxShadow: cur.status === "running" ? "0 0 7px var(--good)" : "none", animation: cur.status === "running" ? "cxBreathe 2.5s ease infinite" : "none" }} />{cur.status === "running" ? "运行中" : "已结束"}</span>
          ) : <span style={mono(10)}>点左侧会话看输出</span>}
        </div>

        {/* 主体 */}
        {termMode === "runs" ? (
          <AgentRunsView />
        ) : termMode === "pty" ? (
          <Suspense fallback={<div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--text-mute)", font: "600 11px 'IBM Plex Mono',monospace" }}>终端加载中…</div>}>
            <PtyTerminal agent={ptyAgent} themeMode={themeMode} sessionKey={ptyKey} />
          </Suspense>
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
              ? <pre ref={termRef} style={{ margin: 0, padding: "14px 16px", background: "var(--term-bg)", font: "500 11.5px/1.62 'IBM Plex Mono',monospace", color: "var(--term-dim)", overflowY: "auto", minHeight: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{cur.output || "启动中…"}</pre>
              : curGw
                ? <div style={{ overflowY: "auto", minHeight: 0, display: "grid", placeContent: "center", textAlign: "center", padding: 30, gap: 12 }}>
                    <p style={{ margin: 0, font: "400 12.5px/1.75 'Space Grotesk',sans-serif", color: "var(--text-dim)", maxWidth: 420 }}>{curGw.docs || "本机常驻 agent 网关，一直在后台运行。"}</p>
                    <div style={{ ...sub, padding: "12px 14px", textAlign: "left", maxWidth: 420, margin: "0 auto" }}><div style={mono(9.5)}>在下方输入框直接给它发任务，等价于：</div><code style={{ display: "block", marginTop: 6, font: "500 11.5px 'IBM Plex Mono'", color: "var(--accent)" }}>{curGw.agent === "hermes" ? "hermes -z <任务>" : "openclaw agent <任务>"}</code></div>
                  </div>
                : <div style={{ overflowY: "auto", minHeight: 0, display: "grid", placeContent: "center", textAlign: "center", color: "var(--text-mute)", padding: 30 }}>
                    <div style={{ font: "600 14px 'Space Grotesk',sans-serif", marginBottom: 8, color: "var(--text-dim)" }}>一次性任务流</div>
                    <div style={{ font: "400 12px/1.7 'Space Grotesk',sans-serif", maxWidth: 340 }}>下面输入命令回车即可后台驱动（切到别的页面也不会终止）；或点左侧已有会话查看其输出。想要原生斜杠命令？切到 <b style={{ color: "var(--accent)" }}>交互终端</b>。</div>
                  </div>}
          </div>
        )}

        {/* 底部：PTY 模式给提示条；任务模式给输入条；执行台(runs)不给底栏 */}
        {termMode === "pty" ? (
          <div style={{ ...row(9), padding: "9px 14px", borderTop: "1px solid var(--border-soft)", background: "var(--panel)" }}>
            <span style={{ font: "700 13px 'IBM Plex Mono',monospace", color: "var(--accent)" }}>❯</span>
            <span style={{ font: "400 11px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", flex: 1 }}>直接在上方终端里敲 —— <b style={{ color: "var(--text)" }}>/model</b> <b style={{ color: "var(--text)" }}>/cost</b> <b style={{ color: "var(--text)" }}>/clear</b> 等<b style={{ color: "var(--accent)" }}>原生斜杠命令完整执行</b>（这是 {ptyLabel} 的真实 REPL，不是输入框）。左侧切 agent。</span>
          </div>
        ) : termMode === "task" ? (
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
            <button onClick={centerVoice.toggle} disabled={busy || centerVoice.transcribing || !target} title="Whisper 语音输入" style={{ border: "1px solid var(--border)", cursor: busy || centerVoice.transcribing || !target ? "default" : "pointer", background: centerVoice.recording ? "var(--bad)" : "var(--panel-2)", color: centerVoice.recording ? "#fff" : "var(--text-dim)", font: "600 10.5px 'Space Grotesk'", padding: "7px 10px", borderRadius: 7, opacity: busy || centerVoice.transcribing || !target ? 0.55 : 1 }}>{centerVoice.transcribing ? "转写" : centerVoice.recording ? "停止" : "语音"}</button>
            <button onClick={() => target && sendCenter(target)} disabled={busy || !target || !centerCmd.trim()} style={{ border: 0, cursor: busy || !target ? "default" : "pointer", background: "var(--accent)", color: "#fff", font: "600 11px 'Space Grotesk'", padding: "7px 14px", borderRadius: 7, opacity: busy || !target || !centerCmd.trim() ? 0.5 : 1 }}>{busy ? "…" : "发送"}</button>
          </div>
          {err && <div style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "var(--bad)" }}>{err}</div>}
          {cur && <div style={{ ...row(8) }}><span style={mono(9.5)}>pid {cur.pid} · {fmtAgo(cur.started)}前 · {(cur.output || "").length} 字符</span><span style={flex1} />{cur.status === "running" && <button onClick={() => stop(cur.id)} style={{ border: "1px solid var(--border)", background: "transparent", cursor: "pointer", borderRadius: 7, padding: "5px 13px", color: "var(--bad)", font: "600 10.5px 'Space Grotesk'" }}>停止</button>}</div>}
        </div>
        ) : null}
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
  const [translating, setTranslating] = useState(false);
  useEffect(() => {
    let live = true;
    setLoading(true); setErr(false); setItem(null); setTranslating(false);
    // 秒开:先拿原文(命中缓存则已是中文);若仍有英文待译,后台异步补译再替换。
    getBriefingItem(id).then((r) => {
      if (!live) return;
      if (r?.ok && r.item) {
        setItem(r.item);
        if (r.item.pending_translation) {
          setTranslating(true);
          translateBriefingItem(id).then((t) => { if (live && t?.ok && t.item) setItem(t.item); }).catch(() => {}).finally(() => { if (live) setTranslating(false); });
        }
      } else setErr(true);
    }).catch(() => { if (live) setErr(true); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [id]);
  useEffect(() => { const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, [onClose]);

  const [pf, pb] = priStyle(item?.priority);
  const time = tsToTime(item?.ts);
  const openUrl = () => { if (item?.url) window.open(item.url, "_blank", "noopener,noreferrer"); };
  const sectLbl: CSSProperties = { font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".14em", color: "var(--text-mute)", marginBottom: 8 };
  const bodyText: CSSProperties = { margin: 0, font: "400 14px/1.85 'Space Grotesk','PingFang SC',sans-serif", color: "var(--text-dim)", whiteSpace: "pre-wrap" };

  return (
    // 情报详情用 Sheet:叠在情报抽屉之上(更窄、z 更高、左留边距),不再与抽屉完全重叠。
    <Drawer open onClose={onClose} level="sheet" eyebrow="情报详情" title="详情">
        <div style={{ overflowY: "auto", minHeight: 0, padding: "20px 22px 28px" }}>
          {loading && (
            <div style={{ display: "grid", gap: 12, placeItems: "center", padding: "60px 0", textAlign: "center" }}>
              <div style={{ display: "flex", gap: 5 }}>{[0, 1, 2].map((i) => (<span key={i} style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)", animation: "cxType 1s ease-in-out infinite", animationDelay: `${i * 0.16}s` }} />))}</div>
              <span style={{ font: "500 12px 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>读取详情…</span>
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
              <div style={{ ...sectLbl, display: "flex", alignItems: "center", gap: 8 }}>
                <span>{item.source_detail_translated ? "全文 · 中文（已翻译）" : (translating || item.pending_translation ? "全文 · 原文" : "全文")}</span>
                {translating && (<span style={{ ...row(5), letterSpacing: 0, color: "var(--accent)", textTransform: "none" }}><span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--accent)", animation: "cxType 1s ease-in-out infinite" }} /><span style={{ font: "500 9.5px 'Space Grotesk',sans-serif" }}>翻译中…</span></span>)}
              </div>
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
    </Drawer>
  );
}

// ============ WorkDock 合并 M5：Confidence / Source 通用小组件 ============
// 置信度条：把 0..1 置信度可视化（与记忆置信度/judge score 同一语言）。单强调色，无第二色。
function Confidence({ value, label = true }: { value?: number; label?: boolean }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const pct = Math.round(v * 100);
  return (
    <span style={{ ...row(6), flex: "none" }} title={`置信度 ${pct}%`}>
      <span style={{ position: "relative", width: 42, height: 4, borderRadius: 999, background: "var(--panel-2)", overflow: "hidden", display: "inline-block" }}>
        <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pct}%`, background: v >= 0.6 ? "var(--accent)" : "var(--text-mute)", borderRadius: 999 }} />
      </span>
      {label && <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: v >= 0.6 ? "var(--accent)" : "var(--text-mute)" }}>{pct}%</span>}
    </span>
  );
}
// 来源引用 chip：每条 AI 衍生项都标明来自哪里（来源台账理念）。
const ORIGIN_LABEL: Record<string, string> = { email: "邮件", im: "消息", intel: "情报", agent: "执行", calendar: "日历", manual: "手动", task: "任务", action: "执行" };
function SourceChip({ kind }: { kind?: string }) {
  if (!kind) return null;
  return <span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "var(--text-mute)", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 999, padding: "2px 8px" }}>来源 · {ORIGIN_LABEL[kind] || kind}</span>;
}

// ============ WorkDock 合并 M2：任务收件箱（信息转任务） ============
function senseIcon(name: string): ReactNode {
  const p: Record<string, ReactNode> = {
    folder: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></>,
    monitor: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></>,
    clipboard: <><rect x="8" y="3" width="8" height="4" rx="1" /><path d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" /></>,
    pin: <><path d="M12 21s-6-5.5-6-10a6 6 0 1 1 12 0c0 4.5-6 10-6 10z" /><circle cx="12" cy="11" r="2.2" /></>,
    cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" /></>,
    network: <><path d="M5 12.5a10 10 0 0 1 14 0M8 16a5.5 5.5 0 0 1 8 0M2 9a15 15 0 0 1 20 0" /><circle cx="12" cy="19.5" r="1.2" fill="currentColor" stroke="none" /></>,
    devices: <><rect x="2" y="5" width="14" height="10" rx="2" /><rect x="17" y="8" width="5" height="11" rx="1.5" /><path d="M6 19h6" /></>,
    locale: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" /></>,
    bell: <><path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6" /><path d="M10 19a2 2 0 0 0 4 0" /></>,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">{p[name] || p.cpu}</svg>;
}
// 每种感知通道的专属"图形头"——各自的视觉语言,且与真实采到的数据联动(问题6/7)。
// 统一高度 92,卡片对齐;on=已接入(accent),并按 metrics/thumb 反映实时读数。
function SenseArt({ id, on, metrics, thumb }: { id: string; on: boolean; metrics?: Record<string, number>; thumb?: string }) {
  const c = on ? "var(--accent)" : "var(--text-mute)";
  const dim = on ? "var(--accent-soft)" : "var(--panel-3)";
  const m = metrics || {};
  const wrap = (kids: ReactNode, badge?: string) => (
    <div style={{ position: "relative", height: 92, borderRadius: 12, overflow: "hidden", background: `radial-gradient(120% 120% at 80% 0%, ${dim}, transparent), var(--panel-2)`, border: "1px solid var(--border-soft)", display: "grid", placeItems: "center" }}>
      {kids}
      {badge && <span style={{ position: "absolute", right: 8, bottom: 7, font: "600 9px 'IBM Plex Mono',monospace", color: "var(--accent)", background: "var(--accent-soft)", borderRadius: 6, padding: "2px 6px" }}>{badge}</span>}
    </div>
  );
  switch (id) {
    case "fs-folder": return wrap(<svg width="64" height="48" viewBox="0 0 64 48" fill="none"><path d="M6 12a3 3 0 0 1 3-3h12l4 4h24a3 3 0 0 1 3 3v22a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3z" stroke={c} strokeWidth="1.6" /><path d="M14 22h28M14 28h20M14 34h24" stroke={c} strokeWidth="1.4" opacity=".6" /></svg>, on && m.count ? `${m.count} 项` : undefined);
    case "screen":
      // 联动:有缩略图就直接展示采到的那一帧(thumb 仅本地显示,不投喂)。
      if (on && thumb) return (
        <div style={{ position: "relative", height: 92, borderRadius: 12, overflow: "hidden", border: "1px solid var(--accent)" }}>
          <img src={thumb} alt="屏幕快照" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          <span style={{ position: "absolute", left: 8, bottom: 7, font: "600 8.5px 'IBM Plex Mono'", color: "#fff", background: "rgba(0,0,0,.55)", borderRadius: 6, padding: "2px 6px" }}>已截一帧 · 本地</span>
        </div>
      );
      return wrap(<svg width="72" height="52" viewBox="0 0 72 52" fill="none"><rect x="8" y="6" width="56" height="34" rx="3" stroke={c} strokeWidth="1.6" /><path d="M26 46h20M36 40v6" stroke={c} strokeWidth="1.6" /><rect x="14" y="12" width="20" height="13" rx="1.5" fill={c} opacity=".25" /><path d="M40 14h16M40 19h12M40 24h16" stroke={c} strokeWidth="1.4" opacity=".6" /></svg>);
    case "clipboard": return wrap(<svg width="52" height="60" viewBox="0 0 52 60" fill="none"><rect x="10" y="10" width="32" height="44" rx="4" stroke={c} strokeWidth="1.6" /><rect x="19" y="6" width="14" height="9" rx="2" fill={c} opacity=".3" stroke={c} strokeWidth="1.4" /><path d="M18 26h16M18 33h16M18 40h10" stroke={c} strokeWidth="1.4" opacity=".6" /></svg>);
    case "geo": return wrap(<svg width="56" height="64" viewBox="0 0 56 64" fill="none"><path d="M28 56s16-14 16-30a16 16 0 1 0-32 0c0 16 16 30 16 30z" stroke={c} strokeWidth="1.6" /><circle cx="28" cy="26" r="6" fill={c} opacity=".3" stroke={c} strokeWidth="1.4" /></svg>);
    case "network": {
      // 联动:弧线条数随网络质量(rtt 越低越多弧),并标 rtt。
      const arcs = !on ? 1 : m.rtt != null ? (m.rtt < 80 ? 3 : m.rtt < 200 ? 2 : 1) : 3;
      return wrap(<svg width="72" height="52" viewBox="0 0 72 52" fill="none"><path d="M8 22a48 48 0 0 1 56 0" stroke={c} strokeWidth="1.8" opacity={arcs >= 3 ? .9 : .2} /><path d="M12 30a34 34 0 0 1 48 0" stroke={c} strokeWidth="1.8" opacity={arcs >= 2 ? 1 : .2} /><path d="M22 38a20 20 0 0 1 28 0" stroke={c} strokeWidth="1.8" opacity={arcs >= 1 ? 1 : .2} /><circle cx="36" cy="44" r="3.5" fill={c} /></svg>, on && m.rtt != null ? `${m.rtt}ms` : undefined);
    }
    case "media-devices": return wrap(<svg width="74" height="48" viewBox="0 0 74 48" fill="none"><circle cx="20" cy="24" r="11" stroke={c} strokeWidth="1.6" /><circle cx="20" cy="24" r="4" fill={c} opacity=".4" /><rect x="40" y="10" width="26" height="20" rx="3" stroke={c} strokeWidth="1.6" /><rect x="48" y="34" width="10" height="6" rx="1" fill={c} opacity=".4" /></svg>, on && (m.cam != null) ? `${m.cam}摄 ${m.mic ?? 0}麦` : undefined);
    case "locale": return wrap(<svg width="58" height="58" viewBox="0 0 58 58" fill="none"><circle cx="29" cy="29" r="22" stroke={c} strokeWidth="1.6" /><path d="M7 29h44M29 7a30 30 0 0 1 0 44M29 7a30 30 0 0 0 0 44" stroke={c} strokeWidth="1.3" opacity=".6" /></svg>);
    case "notify": return wrap(<svg width="56" height="60" viewBox="0 0 56 60" fill="none"><path d="M14 26a14 14 0 1 1 28 0c0 12 5 14 5 14H9s5-2 5-14z" stroke={c} strokeWidth="1.6" fill={c} fillOpacity={on ? .12 : 0} /><path d="M23 46a5 5 0 0 0 10 0" stroke={c} strokeWidth="1.6" />{on && <circle cx="42" cy="16" r="5" fill="var(--accent)" />}</svg>);
    case "env": {
      // 设备环境专属图:电池 + 电量填充随真实电量联动(消除掉默认通用图)。
      const lvl = on && m.battery != null ? Math.max(0, Math.min(100, m.battery)) : 0;
      const fillW = (28 * lvl) / 100;
      return wrap(
        <svg width="72" height="44" viewBox="0 0 72 44" fill="none">
          <rect x="14" y="13" width="36" height="20" rx="3.5" stroke={c} strokeWidth="1.8" />
          <rect x="51" y="19" width="4" height="8" rx="1.5" fill={c} />
          {on && m.battery != null && <rect x="17" y="16" width={fillW} height="14" rx="1.5" fill={m.charging ? "var(--good)" : "var(--accent)"} />}
          {on && m.charging === 1 && <path d="M32 14l-4 8h5l-3 8 8-11h-5z" fill="#fff" stroke={c} strokeWidth="0.6" />}
        </svg>,
        on && m.battery != null ? `${m.battery}%${m.charging ? "⚡" : ""}` : undefined,
      );
    }
    default: return wrap(<svg width="60" height="56" viewBox="0 0 60 56" fill="none"><rect x="14" y="14" width="32" height="32" rx="4" stroke={c} strokeWidth="1.6" /><path d="M22 6v6M38 6v6M22 50v6M38 50v6M4 22h6M4 36h6M50 22h6M50 36h6" stroke={c} strokeWidth="1.4" opacity=".6" /><rect x="24" y="24" width="12" height="12" rx="2" fill={c} opacity=".3" /></svg>);
  }
}

function Sense() {
  const [results, setResults] = useState<Record<string, SenseSaved>>(() => loadSenseState());
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { const h = (e: Event) => setResults((((e as CustomEvent).detail) || loadSenseState())); window.addEventListener("cx-sense-change", h); return () => window.removeEventListener("cx-sense-change", h); }, []);

  const run = async (ch: SenseChannel) => {
    setBusy(ch.id);
    try {
      const r = await ch.connect();
      let fed: string | undefined;
      if (r.status === "connected") { const ing = await ingestSensed(ch, r); fed = ing.ok ? `已投喂 · 收纳 ${ing.accepted ?? 0} 条` : (ing.reason ? `未投喂 · ${ing.reason}` : "未投喂"); }
      saveSenseStatus(ch.id, { status: r.status, fed, summary: r.summary, details: r.details, thumb: r.thumb, metrics: r.metrics, ts: Date.now() });
    } finally { setBusy(null); }
  };

  const statusTone = (s?: string) => s === "connected" ? "var(--good)" : s === "denied" ? "var(--bad)" : s === "unsupported" ? "var(--text-mute)" : "var(--warn)";
  const statusText = (s?: string) => ({ connected: "已接入", available: "可接入", unsupported: "不支持", denied: "被拒绝" } as Record<string, string>)[s || ""] || "未接入";
  const onCount = SENSE_CHANNELS.filter((ch) => results[ch.id]?.status === "connected").length;

  return (
    <div className="cx-page" style={{ height: "100%", overflowY: "auto", padding: 16, display: "grid", gap: 14, alignContent: "start" }}>
      <div style={{ ...panel, padding: "14px 16px", display: "grid", gap: 8 }}>
        <div style={{ ...row(8) }}><b style={{ font: "700 17px 'Space Grotesk',sans-serif", color: "var(--text)" }}>感知接入</b><span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "var(--accent)", background: "var(--accent-soft)", borderRadius: 999, padding: "2px 9px" }}>本地优先 · 手势触发</span><span style={flex1} /><span style={{ ...row(5), ...mono(10, onCount > 0 ? "var(--good)" : "var(--text-mute)") }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: onCount > 0 ? "var(--good)" : "var(--text-mute)", display: "inline-block" }} />{onCount}/{SENSE_CHANNELS.length} 已接入</span></div>
        <PageHelp what="每张卡是一种感知通道。点「授权」触发浏览器系统弹窗,通过后这条通道的信息会作为上下文喂给 Jarvis——让它知道你此刻的处境、在看什么、在哪、设备如何。"
          points={["授权状态会记住,切换页面不丢(本地保存)", "投喂前过隐私闸门:脱敏 + 红线词拦截,被拦会显示原因", "通道越全,Jarvis 的判断和主动提醒越贴合你当前实际情况"]} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(290px,1fr))", gap: 12, alignItems: "stretch" }}>
        {SENSE_CHANNELS.map((ch) => {
          const r = results[ch.id]; const supported = ch.isSupported(); const on = r?.status === "connected";
          // 统一卡片骨架:图形头 / 标题 / 说明 / 用途+隐私 / 读数 / 投喂态 / 按钮。
          // 中段(读数)用 1fr 吸收高度差,按钮永远贴底 → 所有卡片底部对齐。
          return (
            <div key={ch.id} className="cx-lift" style={{ ...panel, display: "grid", gridTemplateRows: "auto auto auto auto minmax(0,1fr) auto", gap: 9, borderColor: on ? "var(--accent)" : "var(--border)" }}>
              <SenseArt id={ch.id} on={on} metrics={r?.metrics} thumb={r?.thumb} />
              <div style={{ ...row(8) }}>
                <b style={{ font: "600 13.5px 'Space Grotesk',sans-serif", color: "var(--text)", flex: 1 }}>{ch.name}</b>
                <span style={{ ...row(5) }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: statusTone(r?.status), flex: "none", boxShadow: on ? "0 0 6px var(--good)" : "none" }} /><span style={mono(9.5)}>{r ? statusText(r.status) : supported ? "可接入" : "不支持"}</span></span>
              </div>
              <p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", minHeight: 34 }}>{ch.desc}</p>
              {/* 用途 + 隐私(问题7:说清每个通道干啥、隐私边界) */}
              <div style={{ display: "grid", gap: 4, padding: "8px 10px", borderRadius: 9, background: "var(--panel-2)", border: "1px solid var(--border-soft)" }}>
                <span style={{ ...row(5), font: "400 10px/1.45 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" style={{ flex: "none", marginTop: 1 }}><path d="M12 2a7 7 0 0 1 4 12.7V17H8v-2.3A7 7 0 0 1 12 2z" /><path d="M9 21h6" /></svg><span>{ch.purpose}</span></span>
                <span style={{ ...row(5), font: "400 9.5px/1.45 'Space Grotesk',sans-serif", color: "var(--text-mute)" }}><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flex: "none", marginTop: 1 }}><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg><span>{ch.privacy}</span></span>
              </div>
              <div style={{ minHeight: 0, overflowY: "auto", display: "grid", gap: 6, alignContent: "start" }}>
                {r?.details && r.details.length > 0 && <div style={{ ...sub, padding: "8px 10px", display: "grid", gap: 3 }}>{r.details.slice(0, 12).map((d, i) => <span key={i} style={{ font: "400 10.5px 'IBM Plex Mono',monospace", color: "var(--text-dim)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{d}</span>)}</div>}
                {r?.fed && <div style={{ font: "600 10px 'IBM Plex Mono',monospace", color: r.fed.startsWith("已投喂") ? "var(--good)" : "var(--text-mute)" }}>{r.fed}</div>}
              </div>
              <button onClick={() => run(ch)} disabled={!supported || busy === ch.id} className="cx-nav" style={{ border: "1px solid var(--accent)", cursor: supported && busy !== ch.id ? "pointer" : "default", font: "600 11.5px 'Space Grotesk'", padding: "8px 0", borderRadius: 9, color: supported ? (on ? "var(--accent)" : "#fff") : "var(--text-mute)", background: supported ? (on ? "var(--accent-soft)" : "var(--accent)") : "var(--panel-2)" }}>{busy === ch.id ? "读取中…" : on ? "重新感知" : "授权接入"}</button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AgentRunsView() {
  const [data, setData] = useState<AgentRunsOverview | null>(null);
  const load = () => getAgentRuns(48).then(setData).catch(() => setData((p) => p ?? { pending: [], recent: [] }));
  useEffect(() => { load(); const t = setInterval(load, 8000); const stop = subscribeNotify(() => load()); return () => { clearInterval(t); stop(); }; }, []);

  const verdictTone = (v?: string) => v === "deny" ? "var(--bad)" : v === "auto" ? "var(--good)" : "var(--warn)";
  const statusTone = (s?: string) => s === "denied" ? "var(--bad)" : (s === "ok" || s === "done" || s === "success") ? "var(--good)" : s === "error" ? "var(--bad)" : "var(--text-mute)";
  const statusText = (s?: string) => ({ ok: "已执行", done: "已执行", success: "已执行", denied: "已拦截", error: "失败", pending: "待确认" } as Record<string, string>)[s || ""] || s || "—";
  const c = data?.counts;
  const argPreview = (args?: Record<string, unknown>) => { try { const s = JSON.stringify(args || {}); return s.length > 80 ? s.slice(0, 80) + "…" : s; } catch { return ""; } };

  return (
    <div style={{ overflowY: "auto", minHeight: 0, padding: "14px 16px", display: "grid", gap: 14, alignContent: "start" }}>
      <div style={{ ...row(8), flexWrap: "wrap" }}>
        <span style={{ ...row(5), font: "600 10.5px 'IBM Plex Mono',monospace", background: "var(--panel-2)", color: "var(--text-dim)", borderRadius: 7, padding: "5px 9px" }}>待确认 <b style={{ color: "var(--warn)" }}>{c?.awaiting ?? 0}</b></span>
        <span style={{ ...row(5), font: "600 10.5px 'IBM Plex Mono',monospace", background: "var(--panel-2)", color: "var(--text-dim)", borderRadius: 7, padding: "5px 9px" }}>已执行 <b style={{ color: "var(--good)" }}>{c?.executed ?? 0}</b></span>
        <span style={{ ...row(5), font: "600 10.5px 'IBM Plex Mono',monospace", background: "var(--panel-2)", color: "var(--text-dim)", borderRadius: 7, padding: "5px 9px" }}>已拦截 <b style={{ color: "var(--bad)" }}>{c?.blocked ?? 0}</b></span>
        <span style={flex1} /><span style={mono(9.5)}>每 8s 刷新 · 行动闸门审计</span>
      </div>

      <div>
        <div style={{ ...lbl, marginBottom: 8 }}>待你确认（按策略需点头）</div>
        {data === null && <div style={{ ...mono(11), padding: "10px 0" }}>正在加载…</div>}
        {data !== null && (data.pending || []).length === 0 && <div style={{ ...mono(10.5), padding: "8px 0" }}>当前没有等待确认的动作。</div>}
        <div style={{ display: "grid", gap: 9 }}>
          {(data?.pending || []).map((p) => (
            <div key={p.id} style={{ ...sub, padding: "11px 12px", display: "grid", gap: 7 }}>
              <div style={{ ...row(8) }}>
                <span style={{ font: "600 11px 'IBM Plex Mono',monospace", color: "var(--text)" }}>{p.tool}</span>
                <span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: verdictTone(p.gate?.verdict), background: "var(--panel-3)", borderRadius: 999, padding: "2px 8px" }}>{p.gate?.label || "需确认"}</span>
                <span style={flex1} /><span style={mono(9.5, "var(--warn)")}>待确认</span>
              </div>
              {p.args && <code style={{ font: "500 10px 'IBM Plex Mono',monospace", color: "var(--text-dim)", wordBreak: "break-all" }}>{argPreview(p.args)}</code>}
              {p.reason && <span style={{ font: "400 10.5px 'Space Grotesk',sans-serif", color: "var(--text-mute)" }}>{p.reason}</span>}
              <span style={{ font: "400 9.5px 'Space Grotesk',sans-serif", color: "var(--text-mute)" }}>在「交互终端」或对话里确认/拒绝该动作。</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div style={{ ...lbl, marginBottom: 8 }}>执行审计 · 近 48h</div>
        {data !== null && (data.recent || []).length === 0 && <div style={{ ...mono(10.5), padding: "8px 0" }}>暂无执行记录。</div>}
        <div style={{ display: "grid", gap: 7 }}>
          {(data?.recent || []).map((r) => (
            <div key={r.id} style={{ ...row(9), padding: "8px 10px", background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: 9 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: statusTone(r.status), flex: "none" }} />
              <span style={{ font: "600 11px 'IBM Plex Mono',monospace", color: "var(--text-dim)", flex: "none", minWidth: 92, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.tool || "动作"}</span>
              <span style={{ font: "400 11px 'Space Grotesk',sans-serif", color: "var(--text-mute)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(r.detail || "").replace(/^args=\{\}\n?->\s*/, "")}</span>
              <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: statusTone(r.status), flex: "none" }}>{statusText(r.status)}</span>
              <span style={{ ...mono(9.5), flex: "none" }}>{fmtAgo(r.ts ? Math.floor(r.ts / 1000) : undefined)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ============ 问题6: 收件箱大卡片(点击呼出,去 tab) ============
function InboxCard({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<{ tasks: InboxTask[]; counts?: Record<string, number> } | null>(null);
  const [tab, setTab] = useState<"待确认" | "已确认" | "已完成">("待确认");
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const stateOf = { 待确认: "unconfirmed", 已确认: "confirmed", 已完成: "done" } as const;
  const load = () => getInbox("unconfirmed,confirmed,done").then(setData).catch(() => setData((p) => p ?? { tasks: [], counts: {} }));
  useEffect(() => { load(); const stop = subscribeNotify(() => load()); return () => stop(); }, []);
  const rebuild = async () => { setBusy(true); try { await rebuildInbox(48); await load(); } finally { setBusy(false); } };
  const act = async (id: string, state: "confirmed" | "done" | "ignored") => { await setInboxState(id, state); setSel(null); await load(); };
  const tasks = (data?.tasks || []).filter((t) => t.inbox_state === stateOf[tab]);
  const counts = data?.counts || {};
  const cur = tasks.find((t) => t.id === sel) || null;
  const tabs: ("待确认" | "已确认" | "已完成")[] = ["待确认", "已确认", "已完成"];
  return (
    <Modal open onClose={onClose} eyebrow="待办" title="任务收件箱" width={860} maxHeight={680}>
      <div style={{ display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, height: "100%" }}>
        <div style={{ ...row(10), padding: "12px 16px", borderBottom: "1px solid var(--border-soft)", flexWrap: "wrap" }}>
          <div style={{ flex: "none", display: "flex", gap: 5, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: 4 }}>
            {tabs.map((f) => (<button key={f} onClick={() => { setTab(f); setSel(null); }} style={{ border: 0, cursor: "pointer", font: "600 11px 'Space Grotesk'", padding: "6px 13px", borderRadius: 6, color: tab === f ? "#fff" : "var(--text-dim)", background: tab === f ? "var(--accent)" : "transparent" }}>{f} {(counts[stateOf[f]] ?? 0) || ""}</button>))}
          </div>
          <span style={flex1} />
          <button onClick={rebuild} disabled={busy} style={{ border: "1px solid var(--accent)", background: "var(--accent-soft)", color: "var(--accent)", cursor: "pointer", borderRadius: 9, padding: "7px 13px", font: "600 11px 'Space Grotesk'" }}>{busy ? "扫描中…" : "从情报抽取待办"}</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: cur ? "minmax(0,1fr) 320px" : "minmax(0,1fr)", minHeight: 0 }}>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "10px 16px", display: "grid", gap: 7, alignContent: "start" }}>
            {data === null && <div style={{ ...mono(11), padding: "20px 0", textAlign: "center" }}>加载中…</div>}
            {data !== null && tasks.length === 0 && <div style={{ ...mono(10.5), padding: "20px 0", textAlign: "center", lineHeight: 1.7 }}>{tab === "待确认" ? "没有待确认任务。收件箱只收真正需要你处理的事(邮件/IM @你、日程待办),资讯不会进。" : "暂无"}</div>}
            {tasks.map((t) => (
              <button key={t.id} onClick={() => setSel(t.id === sel ? null : t.id)} className="cx-lift" style={{ textAlign: "left", border: `1px solid ${t.id === sel ? "var(--accent)" : "var(--border-soft)"}`, background: t.id === sel ? "var(--accent-soft)" : "var(--panel-2)", borderRadius: 10, padding: "10px 12px", cursor: "pointer", display: "grid", gap: 4 }}>
                <div style={{ ...row(8) }}>
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: t.priority === "P1" ? "var(--bad)" : t.priority === "P3" ? "var(--text-mute)" : "var(--accent)", flex: "none" }} />
                  <b style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</b>
                  {t.origin && <span style={{ font: "600 8.5px 'IBM Plex Mono'", color: "var(--text-dim)", background: "var(--panel-3)", borderRadius: 999, padding: "2px 7px" }}>{t.origin}</span>}
                </div>
                {t.suggestion && <span style={{ font: "400 11px 'Space Grotesk'", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.suggestion}</span>}
              </button>
            ))}
          </div>
          {cur && (
            <div style={{ borderLeft: "1px solid var(--border-soft)", overflowY: "auto", minHeight: 0, padding: "14px 16px", display: "grid", gap: 11, alignContent: "start" }}>
              <b style={{ font: "600 14px/1.4 'Space Grotesk'", color: "var(--text)" }}>{cur.title}</b>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                <span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--accent)", background: "var(--accent-soft)", borderRadius: 999, padding: "3px 9px" }}>{cur.priority}</span>
                {cur.origin && <span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--text-dim)", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 999, padding: "3px 9px" }}>{cur.origin}</span>}
                {typeof cur.confidence === "number" && <span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--text-mute)" }}>置信 {Math.round(cur.confidence * 100)}%</span>}
              </div>
              {cur.suggestion && <div style={{ ...sub, padding: "10px 12px" }}><div style={{ ...lbl, marginBottom: 5 }}>建议</div><p style={{ margin: 0, font: "400 12.5px/1.6 'Space Grotesk'", color: "var(--text-dim)" }}>{cur.suggestion}</p></div>}
              {(cur as any).context_preview && <div style={{ ...sub, padding: "10px 12px" }}><div style={{ ...lbl, marginBottom: 5 }}>原文</div><p style={{ margin: 0, font: "400 11.5px/1.6 'Space Grotesk'", color: "var(--text-dim)", whiteSpace: "pre-wrap" }}>{(cur as any).context_preview}</p></div>}
              {(cur as any).reply_draft && <div style={{ ...sub, padding: "10px 12px" }}><div style={{ ...lbl, marginBottom: 5 }}>回复草稿</div><p style={{ margin: 0, font: "400 11.5px/1.6 'Space Grotesk'", color: "var(--text-dim)", whiteSpace: "pre-wrap" }}>{(cur as any).reply_draft}</p></div>}
              {cur.inbox_state === "unconfirmed" && <div style={{ ...row(8), marginTop: 2 }}>
                <button onClick={() => act(cur.id, "confirmed")} style={{ flex: 1, border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "9px 0", font: "600 12px 'Space Grotesk'" }}>确认</button>
                <button onClick={() => act(cur.id, "ignored")} style={{ flex: "none", border: "1px solid var(--border)", background: "transparent", color: "var(--text-mute)", cursor: "pointer", borderRadius: 8, padding: "9px 16px", font: "600 12px 'Space Grotesk'" }}>忽略</button>
              </div>}
              {cur.inbox_state === "confirmed" && <button onClick={() => act(cur.id, "done")} style={{ border: 0, background: "var(--good)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "9px 0", font: "600 12px 'Space Grotesk'" }}>标记完成</button>}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

// ============ 问题5: 日报大卡片(先生成→绿了再看→酷炫卡) ============
// 深入调研卡(问题2/D):从记事发起,多源搜索→读源→带来源可视化报告。
function ResearchCard({ onClose }: { onClose: () => void }) {
  const [goal, setGoal] = useState("");
  const [report, setReport] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => { if (!goal.trim() || busy) return; setBusy(true); setReport(""); try { const r = await researchReport(goal); setReport(r.html); } catch { setReport(""); } finally { setBusy(false); } };
  const ipt: CSSProperties = { background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px", color: "var(--text)", font: "400 12.5px 'Space Grotesk'", outline: "none" };
  return (
    <Modal open onClose={onClose} eyebrow="调研" title="深入调研" width={760} maxHeight={720}>
      <div style={{ padding: "16px 18px", display: "grid", gap: 12, minHeight: 0 }}>
        <div style={{ ...row(8) }}>
          <input value={goal} onChange={(e) => setGoal(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") run(); }} placeholder="调研目标(如:对比本地 LLM 推理框架)" style={{ ...ipt, flex: 1 }} />
          <button onClick={run} disabled={busy} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 9, padding: "9px 18px", font: "600 12px 'Space Grotesk'", flex: "none", opacity: busy ? 0.6 : 1 }}>{busy ? "调研中…" : "开始"}</button>
        </div>
        {busy && <div style={{ ...mono(11), padding: "24px 0", textAlign: "center" }}>多源搜索 + 读源 + 综合报告中…</div>}
        {report && <iframe title="report" srcDoc={report} style={{ width: "100%", height: "60vh", border: "1px solid var(--border)", borderRadius: 10, background: "#fff" }} />}
        {!report && !busy && <div style={{ ...mono(10.5), lineHeight: 1.7 }}>输入目标 → Jarvis 搜索多个来源、读全文、做目标导向抽取,生成带来源的可视化报告(需配置 Tavily/SearXNG 搜索源)。</div>}
      </div>
    </Modal>
  );
}

function ReportCard({ onClose }: { onClose: () => void }) {
  const [phase, setPhase] = useState<"idle" | "loading" | "ready">("idle");
  const [period, setPeriod] = useState<"today" | "week">("today");
  const [data, setData] = useState<WrapUp | null>(null);
  const gen = (p: "today" | "week") => { setPhase("loading"); setPeriod(p); getWrapup(p).then((d) => { setData(d); setPhase("ready"); }).catch(() => setPhase("idle")); };
  useEffect(() => { gen("today"); }, []);
  const s = data?.summary;
  return (
    <Modal open onClose={onClose} eyebrow="收尾" title={`${data?.label || "日报"}`} width={760} maxHeight={680}>
      <div style={{ display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, height: "100%" }}>
        <div style={{ ...row(10), padding: "12px 18px", borderBottom: "1px solid var(--border-soft)" }}>
          <div style={{ flex: "none", display: "flex", gap: 5, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: 4 }}>
            {(["today", "week"] as const).map((p) => (<button key={p} onClick={() => gen(p)} style={{ border: 0, cursor: "pointer", font: "600 11px 'Space Grotesk'", padding: "6px 14px", borderRadius: 6, color: period === p ? "#fff" : "var(--text-dim)", background: period === p ? "var(--accent)" : "transparent" }}>{p === "today" ? "今天" : "本周"}</button>))}
          </div>
          <span style={flex1} />
          <span style={{ ...row(5), ...mono(9.5, phase === "ready" ? "var(--good)" : "var(--warn)") }}>
            <b style={{ width: 6, height: 6, borderRadius: "50%", background: phase === "ready" ? "var(--good)" : "var(--warn)", display: "inline-block", animation: phase === "loading" ? "cxBreathe 1.2s ease infinite" : "none" }} />
            {phase === "loading" ? "生成中…" : phase === "ready" ? "已就绪" : "待生成"}
          </span>
        </div>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "18px 22px" }}>
          {phase === "loading" && (
            <div style={{ display: "grid", gap: 14, placeItems: "center", padding: "70px 0" }}>
              <div style={{ display: "flex", gap: 6 }}>{[0, 1, 2].map((i) => <span key={i} style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--accent)", animation: "cxType 1s ease-in-out infinite", animationDelay: `${i * 0.16}s` }} />)}</div>
              <span style={{ font: "500 12.5px 'Space Grotesk'", color: "var(--text-dim)" }}>正在综合今天的任务与执行,生成日报…</span>
            </div>
          )}
          {phase === "ready" && s && (
            <div style={{ display: "grid", gap: 16 }}>
              {s.headline && <div style={{ font: "600 18px/1.45 'Space Grotesk','PingFang SC'", color: "var(--text)", background: "linear-gradient(135deg,var(--accent-soft),transparent)", border: "1px solid var(--border)", borderRadius: 14, padding: "16px 18px" }}>{s.headline}</div>}
              {(s.highlights?.length ?? 0) > 0 && (
                <div style={{ display: "grid", gap: 7 }}>
                  <div style={lbl}>亮点</div>
                  {s.highlights!.map((h, i) => (<div key={i} style={{ ...row(9), alignItems: "flex-start" }}><span style={{ width: 18, height: 18, borderRadius: 6, background: "var(--accent-soft)", color: "var(--accent)", font: "700 9px 'IBM Plex Mono'", display: "grid", placeContent: "center", flex: "none", marginTop: 1 }}>{i + 1}</span><span style={{ font: "400 13px/1.6 'Space Grotesk'", color: "var(--text-dim)" }}>{h}</span></div>))}
                </div>
              )}
              {s.by_area && Object.keys(s.by_area).length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", gap: 10 }}>
                  {Object.entries(s.by_area).map(([area, txt]) => (<div key={area} style={{ ...sub, padding: "12px 14px", display: "grid", gap: 4 }}><span style={{ font: "600 11px 'Space Grotesk'", color: "var(--accent)" }}>{area}</span><span style={{ font: "400 12px/1.55 'Space Grotesk'", color: "var(--text-dim)" }}>{txt}</span></div>))}
                </div>
              )}
              {s.report && <div><div style={{ ...lbl, marginBottom: 6 }}>正文</div><p style={{ margin: 0, font: "400 13px/1.75 'Space Grotesk','PingFang SC'", color: "var(--text-dim)", whiteSpace: "pre-wrap" }}>{s.report}</p></div>}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div style={{ ...sub, padding: "12px 14px" }}><div style={{ ...row(7), marginBottom: 6 }}><span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--good)" }}>已完成</span><span style={flex1} /><b style={mono(11, "var(--good)")}>{data?.counts?.completed ?? 0}</b></div>{(data?.completed || []).slice(0, 6).map((it, i) => <div key={i} style={{ font: "400 11.5px/1.5 'Space Grotesk'", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>· {it.title}</div>)}</div>
                <div style={{ ...sub, padding: "12px 14px" }}><div style={{ ...row(7), marginBottom: 6 }}><span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--text-mute)" }}>未完成</span><span style={flex1} /><b style={mono(11, "var(--text-dim)")}>{data?.counts?.unfinished ?? 0}</b></div>{(data?.unfinished || []).slice(0, 6).map((it, i) => <div key={i} style={{ font: "400 11.5px/1.5 'Space Grotesk'", color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>· {it.title}</div>)}</div>
              </div>
              {s.next && <div style={{ ...row(8), background: "var(--accent-soft)", border: "1px solid var(--border)", borderRadius: 12, padding: "12px 16px" }}><span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--accent)", flex: "none" }}>明日</span><span style={{ font: "500 12.5px 'Space Grotesk'", color: "var(--text-dim)" }}>{s.next}</span></div>}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

// ============ 问题3+12: 首页 agent 工作区(真实多会话,可切换) ============
// 问题5:智能体工作区 = 真 PTY 多会话。一个 CLI = 一个持续交互终端(xterm,/ws/term),
// 像在自己 iTerm 里跑一样(claude 的 /model /clear 都真实可用,登录 shell 带凭证 → 不再 401)。
// 多个 agent 并行 = 多个标签,每个标签一个常驻挂载的 xterm;切换用 display 切,绝不卸载(卸载会杀掉 PTY)。
type PtyTab = { key: number; agent: string; label: string; initial?: string };
function AgentWorkspace({ goAgents, themeMode }: { goAgents: () => void; themeMode: Theme }) {
  const [tabs, setTabs] = useState<PtyTab[]>([]);
  const [activeKey, setActiveKey] = useState<number | null>(null);
  const [external, setExternal] = useState<ExternalAgent[]>([]);
  const [agentsList, setAgentsList] = useState<CliAgent[]>([]);
  const [launchAgent, setLaunchAgent] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const keyRef = useRef(1);
  const tagOf = (a: string): [string, string] => TAG[a] || [a.slice(0, 2).toUpperCase(), "var(--text-dim)"];

  useEffect(() => {
    let live = true;
    const poll = () => getCliSessions().then((d) => { if (live) setExternal(d.external || []); }).catch(() => {});
    poll(); const t = setInterval(poll, 4000); const stop = subscribeNotify(() => poll());
    getCliAgents().then((d) => {
      const av = (d.agents || []).filter((a) => a.installed && PTY_CAPABLE.includes(a.name));
      setAgentsList(av); setLaunchAgent((c) => c || av[0]?.name || "shell");
    }).catch(() => {});
    return () => { live = false; clearInterval(t); stop(); };
  }, []);

  const openSession = () => {
    const ag = launchAgent || "shell";
    const task = prompt.trim();
    const display = agentsList.find((a) => a.name === ag)?.display || ag;
    const key = keyRef.current++;
    const label = task ? `${display} · ${task.slice(0, 18)}` : display;
    setTabs((ts) => [...ts, { key, agent: ag, label, initial: task || undefined }]);
    setActiveKey(key);
    setPrompt("");
  };
  const closeTab = (key: number) => {
    const remaining = tabs.filter((t) => t.key !== key);
    setTabs(remaining);
    setActiveKey((cur) => (cur === key ? (remaining.slice(-1)[0]?.key ?? null) : cur));
  };

  const running = tabs.length + external.length;

  return (
    <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden" }}>
      {/* 顶部:标题 + 会话标签条 + 外部 agent 只读药丸 */}
      <div style={{ borderBottom: "1px solid var(--border-soft)", display: "grid", gap: 0 }}>
        <div style={{ ...row(8), padding: "11px 13px 8px" }}>
          <span style={lbl}>智能体工作区</span>
          <span style={{ ...row(4), ...mono(9.5, running > 0 ? "var(--good)" : "var(--text-mute)") }}>
            <b style={{ width: 6, height: 6, borderRadius: "50%", background: running > 0 ? "var(--good)" : "var(--text-mute)", display: "inline-block", boxShadow: running > 0 ? "0 0 6px var(--good)" : "none" }} />{running} 运行
          </span>
          <span style={flex1} />
          <button onClick={goAgents} className="cx-chip cx-navtip" data-tip="完整编排台" style={{ ...row(5), border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "5px 10px", font: "600 10px 'Space Grotesk'" }}>
            完整编排<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 6l6 6-6 6" /></svg>
          </button>
        </div>
        {(tabs.length > 0 || external.length > 0) && (
          <div style={{ ...row(6), padding: "0 11px 9px", overflowX: "auto", flexWrap: "nowrap" }}>
            {tabs.map((tb) => { const [tg, fg] = tagOf(tb.agent); const on = tb.key === activeKey; return (
              <div key={tb.key} onClick={() => setActiveKey(tb.key)} className="cx-chip" style={{ flex: "none", ...row(6), border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`, background: on ? "var(--accent-soft)" : "var(--panel-2)", borderRadius: 8, padding: "5px 8px 5px 8px", cursor: "pointer", maxWidth: 210 }}>
                <span style={{ width: 17, height: 17, borderRadius: 5, background: "var(--panel-3)", display: "grid", placeContent: "center", font: "700 8px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>
                <span style={{ font: "600 10.5px 'Space Grotesk',sans-serif", color: on ? "var(--accent)" : "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tb.label}</span>
                <button onClick={(e) => { e.stopPropagation(); closeTab(tb.key); }} title="关闭会话" style={{ flex: "none", border: 0, background: "transparent", color: "var(--text-mute)", cursor: "pointer", padding: 0, display: "grid", placeContent: "center" }}><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M18 6 6 18M6 6l12 12" /></svg></button>
              </div>
            ); })}
            {external.map((e) => { const [tg, fg] = tagOf(e.agent); return (
              <div key={`ext-${e.agent}`} title={e.kind === "gateway" ? `常驻网关 :${e.port}` : "你在终端/IDE 自己开的会话"} style={{ flex: "none", ...row(5), border: "1px dashed var(--border)", background: "transparent", borderRadius: 8, padding: "5px 9px", opacity: 0.8 }}>
                <span style={{ width: 15, height: 15, borderRadius: 4, background: "var(--panel-3)", display: "grid", placeContent: "center", font: "700 7.5px 'IBM Plex Mono'", color: fg, flex: "none" }}>{tg}</span>
                <span style={{ font: "500 10px 'Space Grotesk',sans-serif", color: "var(--text-mute)" }}>{e.display}</span>
                <b style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--good)", flex: "none", animation: "cxBreathe 3s ease infinite" }} />
              </div>
            ); })}
          </div>
        )}
      </div>

      {/* 中部:所有 PTY 终端常驻挂载,active 用 display 切换(绝不卸载 → 不杀 PTY) */}
      <div style={{ position: "relative", minHeight: 0, overflow: "hidden" }}>
        {tabs.length === 0 && (
          <div style={{ ...mono(11), height: "100%", display: "grid", placeContent: "center", textAlign: "center", lineHeight: 1.9, padding: "0 24px" }}>
            这里是真·交互终端 —— 选一个 agent,给个任务,直接开一个会话。<br />
            <span style={mono(10, "var(--text-mute)")}>和你在 iTerm 里跑 claude/codex 一样:原生斜杠命令、持续对话都在。多开几个就是并行多 agent。</span>
          </div>
        )}
        {tabs.map((tb) => (
          <div key={tb.key} style={{ position: "absolute", inset: 0, display: tb.key === activeKey ? "block" : "none" }}>
            <Suspense fallback={<div style={{ ...mono(10.5), padding: 16 }}>加载终端…</div>}>
              <PtyTerminal agent={tb.agent} themeMode={themeMode} sessionKey={tb.key} initialInput={tb.initial} visible={tb.key === activeKey} />
            </Suspense>
          </div>
        ))}
      </div>

      {/* 底部:选 agent + 任务 → 开一个新会话 */}
      <div style={{ borderTop: "1px solid var(--border-soft)", padding: "10px 12px" }}>
        <div style={{ ...row(8) }}>
          <select value={launchAgent} onChange={(e) => setLaunchAgent(e.target.value)} style={{ flex: "none", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 9px", color: "var(--text)", font: "600 11px 'Space Grotesk'", outline: "none", cursor: "pointer" }}>
            {agentsList.length === 0 && <option value="shell">Shell</option>}
            {agentsList.map((a) => <option key={a.name} value={a.name}>{a.display}</option>)}
          </select>
          <input value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") openSession(); }}
            placeholder={`给 ${agentsList.find((a) => a.name === launchAgent)?.display || launchAgent || "agent"} 一个任务,回车开会话（可留空,纯开终端）`}
            style={{ flex: 1, minWidth: 0, background: "var(--panel-3)", border: `1px solid ${prompt ? "var(--accent)" : "var(--border)"}`, borderRadius: 8, padding: "9px 12px", color: "var(--text)", font: "500 12px 'IBM Plex Mono',monospace", outline: "none" }} />
          <button onClick={openSession} style={{ flex: "none", border: 0, cursor: "pointer", background: "var(--accent)", color: "#fff", font: "600 11.5px 'Space Grotesk'", padding: "9px 16px", borderRadius: 8 }}>开会话</button>
        </div>
      </div>
    </div>
  );
}

function McpSettings() {
  const [st, setSt] = useState<McpStatus | null>(null);
  const load = () => getMcpStatus().then(setSt).catch(() => {});
  useEffect(() => { load(); }, []);
  const toggle = async (id: string, enabled: boolean) => { await patchMcpSettings({ [id]: { enabled } }).then((d) => setSt(d.status)).catch(() => {}); };
  const servers = st?.servers || [];
  const tone = (s?: string) => s === "ok" ? "var(--good)" : s === "needs_key" ? "var(--warn)" : "var(--text-mute)";
  return (
    <div style={{ padding: "14px 16px", display: "grid", gap: 11, alignContent: "start" }}>
      <PageHelp what="MCP = 给 Jarvis 接外部能力的标准接口(搜索、抓取、各类工具服务)。这里管理本机可用的 MCP 服务器、开关、密钥状态。"
        points={["绿=就绪可用,黄=缺密钥(去设置填),灰=已禁用", "开关控制是否启用该 MCP;启用后 agent 可调用其能力", "主流 MCP(Tavily 等)已内置,密钥在设置→相应项填"]} />
      {st?.summary && <div style={{ ...row(8), ...mono(10.5) }}><span style={{ color: "var(--good)" }}>就绪 {st.summary.ready}</span><span style={{ color: "var(--warn)" }}>缺密钥 {st.summary.needs_key}</span><span style={{ color: "var(--text-mute)" }}>禁用 {st.summary.disabled}</span><span style={flex1} /><span>共 {st.summary.total}</span></div>}
      {servers.map((s) => (
        <div key={s.id} style={{ ...sub, padding: "12px 14px", display: "grid", gap: 7 }}>
          <div style={{ ...row(9) }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: tone(s.status), flex: "none" }} />
            <b style={{ font: "600 13px 'Space Grotesk'", color: "var(--text)", flex: 1 }}>{s.name}</b>
            <span style={mono(9.5)}>{s.provider}</span>
            <label style={{ ...row(5), cursor: "pointer" }}><input type="checkbox" checked={!!s.enabled} onChange={(e) => toggle(s.id, e.target.checked)} /></label>
          </div>
          {s.message && <p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk'", color: "var(--text-dim)" }}>{s.message}</p>}
          {s.capabilities && s.capabilities.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>{s.capabilities.map((c) => <span key={c} style={{ font: "500 9.5px 'IBM Plex Mono'", color: "var(--text-dim)", background: "var(--panel-3)", borderRadius: 999, padding: "2px 8px" }}>{c}</span>)}</div>}
        </div>
      ))}
      {servers.length === 0 && <div style={{ ...mono(11), padding: "20px 0", textAlign: "center" }}>加载 MCP 状态…</div>}
    </div>
  );
}

function SkillsHub({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<"skills" | "mcp">("skills");
  return (
    <Modal open onClose={onClose} eyebrow="能力中枢" title="技能与 MCP" width={920} maxHeight={760}>
      <div style={{ display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, height: "100%" }}>
        <div style={{ ...row(8), padding: "12px 16px", borderBottom: "1px solid var(--border-soft)" }}>
          <div style={{ display: "flex", gap: 5, background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 9, padding: 4 }}>
            {([["skills", "技能库"], ["mcp", "MCP 服务"]] as const).map(([m, zh]) => (<button key={m} onClick={() => setTab(m)} style={{ border: 0, cursor: "pointer", borderRadius: 6, padding: "6px 14px", font: "600 11.5px 'Space Grotesk'", background: tab === m ? "var(--accent)" : "transparent", color: tab === m ? "#fff" : "var(--text-dim)" }}>{zh}</button>))}
          </div>
        </div>
        <div style={{ overflowY: "auto", minHeight: 0 }}>
          {tab === "skills" ? <SkillsPanel embedded /> : <McpSettings />}
        </div>
      </div>
    </Modal>
  );
}

// ============ B 技能库 ============
function SkillsPanel({ embedded = false }: { embedded?: boolean } = {}) {
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [sel, setSel] = useState<Skill | null>(null);
  const [importing, setImporting] = useState(false);
  const [imp, setImp] = useState<{ mode: "md" | "gh"; markdown: string; repo: string; path: string }>({ mode: "md", markdown: "", repo: "", path: "SKILL.md" });
  const [impMsg, setImpMsg] = useState("");
  const load = () => getSkills().then((d) => setSkills(d.skills || [])).catch(() => setSkills((p) => p ?? []));
  useEffect(() => { load(); }, []);
  const archive = async (id: string) => { await setSkillStatus(id, "deleted"); setSel(null); load(); };
  const doImport = async () => {
    setImpMsg("导入中…");
    const body = imp.mode === "md" ? { markdown: imp.markdown } : { repo: imp.repo, path: imp.path };
    const r = await importSkill(body).catch((e) => ({ ok: false, error: String(e) }));
    if (r.ok) { setImpMsg(""); setImporting(false); setImp({ ...imp, markdown: "", repo: "" }); load(); }
    else setImpMsg(r.error || "导入失败");
  };
  const all = skills || [];
  const srcZh: Record<string, string> = { distill: "自动提炼", teacher: "教师", manual: "手动", import: "导入" };
  const impIpt: CSSProperties = { background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", color: "var(--text)", font: "400 12.5px 'Space Grotesk'", outline: "none", width: "100%" };
  return (
    <div className={embedded ? "" : "cx-page"} style={{ height: embedded ? "auto" : "100%", overflowY: "auto", padding: 16, display: "grid", gap: 14, alignContent: "start" }}>
      <div style={{ ...panel, padding: "14px 16px", display: "grid", gap: 12 }}>
        <div style={{ ...row(12), flexWrap: "wrap" }}>
          <b style={{ font: "700 17px 'Space Grotesk',sans-serif", color: "var(--text)" }}>技能库</b>
          <span style={mono(11)}>{all.length} 条</span><span style={flex1} />
          <button onClick={() => setImporting(true)} style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--accent)", cursor: "pointer", borderRadius: 9, padding: "7px 14px", font: "600 11.5px 'Space Grotesk'" }}>导入</button>
        </div>
        <PageHelp what="可复用的「怎么做某件事」的步骤卡。Jarvis 完成一个成功的多步任务后会自动总结一条;你也能手动导入。"
          points={["来源:自动提炼(distill)/ 失败后教师补救(teacher)/ 手动导入(import)", "相关问题再来时,匹配的技能会自动注入到 Jarvis 的上下文里复用", "「导入」支持贴 SKILL.md 文本,或填公开 GitHub 仓库 owner/name + 路径"]} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 12 }}>
        {skills === null && <div style={{ ...mono(11), padding: "8px" }}>加载中…</div>}
        {skills !== null && all.length === 0 && <div style={{ ...panel, ...mono(10.5), lineHeight: 1.7, gridColumn: "1/-1" }}>还没有技能。当 Jarvis 完成一个多步任务(如排查磁盘、处理邮件),会自动把可复用的步骤总结成技能存这里。</div>}
        {all.map((s) => (
          <button key={s.id} onClick={() => setSel(s)} className="cx-lift" style={{ textAlign: "left", border: "1px solid var(--border-soft)", background: "var(--panel-2)", borderRadius: 12, padding: 13, display: "grid", gap: 6, cursor: "pointer" }}>
            <div style={{ ...row(7) }}><b style={{ font: "600 13.5px 'Space Grotesk',sans-serif", color: "var(--text)", flex: 1 }}>{s.name}</b><span style={{ font: "600 8.5px 'IBM Plex Mono',monospace", color: "var(--accent)", background: "var(--accent-soft)", borderRadius: 999, padding: "1px 7px" }}>{srcZh[s.source] || s.source}</span></div>
            <p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>适用:{s.when_to_use}</p>
            <div style={mono(9)}>用过 {s.use_count} 次 · {s.category}</div>
          </button>
        ))}
      </div>
      <Drawer open={!!sel} onClose={() => setSel(null)} eyebrow="技能" title={sel?.name || ""} width={480}
        footer={sel ? <button onClick={() => archive(sel.id)} style={{ border: "1px solid var(--border)", background: "transparent", color: "var(--text-mute)", cursor: "pointer", borderRadius: 9, padding: "8px 16px", font: "600 11.5px 'Space Grotesk'" }}>归档此技能</button> : undefined}>
        {sel && (
          <div style={{ padding: "16px 18px", display: "grid", gap: 12 }}>
            <div><div style={{ ...lbl, marginBottom: 6 }}>何时使用</div><p style={{ margin: 0, font: "400 13px/1.6 'Space Grotesk'", color: "var(--text-dim)" }}>{sel.when_to_use}</p></div>
            {sel.keywords.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{sel.keywords.map((k) => <span key={k} style={{ font: "500 11px 'Space Grotesk'", color: "var(--text-dim)", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 999, padding: "4px 10px" }}>{k}</span>)}</div>}
            <div><div style={{ ...lbl, marginBottom: 6 }}>步骤</div><pre style={{ margin: 0, font: "400 12.5px/1.7 'IBM Plex Mono',monospace", color: "var(--text-dim)", whiteSpace: "pre-wrap" }}>{sel.body}</pre></div>
          </div>
        )}
      </Drawer>
      <Modal open={importing} onClose={() => { setImporting(false); setImpMsg(""); }} title="导入技能" width={520}>
        <div style={{ padding: 16, display: "grid", gap: 12 }}>
          <div style={{ ...row(7) }}>
            {([["md", "贴 SKILL.md"], ["gh", "GitHub 仓库"]] as const).map(([m, zh]) => (
              <button key={m} onClick={() => setImp({ ...imp, mode: m })} style={{ border: 0, cursor: "pointer", borderRadius: 7, padding: "6px 13px", font: "600 11px 'Space Grotesk'", background: imp.mode === m ? "var(--accent)" : "var(--panel-2)", color: imp.mode === m ? "#fff" : "var(--text-dim)" }}>{zh}</button>
            ))}
          </div>
          {imp.mode === "md"
            ? <textarea value={imp.markdown} onChange={(e) => setImp({ ...imp, markdown: e.target.value })} rows={9} placeholder={"---\nname: 技能名\nwhen_to_use: 何时用\ncategory: ops\nkeywords: [关键词]\n---\n## Procedure\n1. ...\n## Verification\n- ..."} style={{ ...impIpt, resize: "vertical", fontFamily: "'IBM Plex Mono',monospace", fontSize: 11.5 }} />
            : <div style={{ display: "grid", gap: 8 }}>
                <input value={imp.repo} onChange={(e) => setImp({ ...imp, repo: e.target.value })} placeholder="owner/name(公开仓库)" style={impIpt} />
                <input value={imp.path} onChange={(e) => setImp({ ...imp, path: e.target.value })} placeholder="SKILL.md(仓库内路径)" style={impIpt} />
                <span style={mono(9.5)}>只读取公开仓库的该文件,经 SSRF 防护抓取。</span>
              </div>}
          {impMsg && <span style={{ font: "500 11px 'Space Grotesk'", color: impMsg === "导入中…" ? "var(--text-mute)" : "var(--accent)" }}>{impMsg}</span>}
          <button onClick={doImport} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 9, padding: "9px 0", font: "600 12.5px 'Space Grotesk'" }}>导入</button>
        </div>
      </Modal>
    </div>
  );
}

function Intel() {
  const [brief, setBrief] = useState<Briefing | null>(null);
  const [intelData, setIntelData] = useState<Intelligence | null>(null);
  const [filter, setFilter] = useState("全部");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [repoDetail, setRepoDetail] = useState<IntelRepo | null>(null);  // 问题3:GitHub 项目详情(不再一点就跳走)
  const filters = ["全部", "高优先", "中优先", "观察"];

  useEffect(() => {
    let live = true;
    const load = () => {
      getBriefing().then((b) => { if (live) setBrief(b); }).catch(() => { if (live) setBrief((p) => p ?? { items: [], counts: {} }); });
      getIntelligence().then((d) => { if (live) setIntelData(d); }).catch(() => { if (live) setIntelData((p) => p ?? {}); });
    };
    load();
    const t = setInterval(load, 90000);
    const stopNotify = subscribeNotify(() => { if (live) load(); });   // 情报命中 → 立即刷新
    return () => { live = false; clearInterval(t); stopNotify(); };
  }, []);

  // 后端已经按「时效窗口优先，同窗按重点」排序；前端只做展示过滤，不再二次按 ts 打乱。
  const items: BriefItem[] = briefingMainFeed(Array.isArray(brief?.items) ? brief!.items! : []);
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
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateRows: "auto auto minmax(0,1fr)", gap: 14, padding: 16, minHeight: 0 }}>
      <style>{"@keyframes cxSlideIn{from{transform:translateX(28px);opacity:.4}to{transform:translateX(0);opacity:1}}@keyframes cxFade{from{opacity:0}to{opacity:1}}"}</style>
      <PageHelp what="Jarvis 从 RSS / 网页监控 / GitHub 雷达 / 邮件等来源抓取信息,评分后按重点排序,供你快速扫读。"
        points={["点一条 → 右侧详情秒开(先显原文),英文正文会异步翻译成中文", "用「重要 / 没用」反馈,Jarvis 会据此调整对你的判断偏好", "这里只读不催办;真正要你做的事会被抽进收件箱"]} />
      <div style={{ ...panel, padding: "14px 16px", ...row(18), flexWrap: "wrap" }}>
        <div style={{ flex: "none", display: "flex", alignItems: "baseline", gap: 8 }}><b style={{ font: "700 26px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{total}</b><span style={mono(11)}>今日信号</span></div>
        <div style={{ flex: "none", display: "flex", gap: 8, font: "600 10.5px 'IBM Plex Mono',monospace" }}>
          <span style={{ ...row(5), background: "var(--bad-soft)", color: "var(--bad)", borderRadius: 7, padding: "5px 9px" }}>高优先 {nHigh}</span>
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
          <div style={headBar}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)" }}>GITHUB 雷达</span><span style={flex1} />{repos.length > 0 && (() => { const last = Math.max(...repos.map((r) => Number(r.observed_ts) || 0)); return last > 0 ? <span style={mono(9, "var(--text-mute)")}>刷新 {tsToTime(last)}</span> : null; })()}<span style={mono(10, "var(--text-dim)")}>高增速 · {repos.length}</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "12px 16px 16px", display: "grid", gap: 11, alignContent: "start" }}>
            {intelData === null && <div style={{ ...mono(11), padding: "16px 0", textAlign: "center" }}>正在加载雷达…</div>}
            {intelData !== null && repos.length === 0 && <div style={{ ...mono(11), padding: "16px 0", textAlign: "center" }}>暂无仓库</div>}
            {repos.map((rp, i) => { const speed = typeof rp.stars_per_day === "number" ? rp.stars_per_day : 0; const sg = repoSignal(speed); const name = rp.repo_full_name || "(未知仓库)"; const summary = rp.summary_zh || rp.display_description || rp.description || ""; const lang = rp.language || (Array.isArray(rp.display_topics) && rp.display_topics[0]) || ""; const pushed = githubPushedAgo(rp.pushed_at); return (
              <div key={rp.repo_full_name || i} onClick={() => setRepoDetail(rp)} className="cx-intel" style={{ border: "1px solid var(--border-soft)", background: "var(--panel-2)", borderRadius: 11, padding: 12, display: "grid", gap: 6, cursor: "pointer" }}><div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}><b style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</b><span style={{ flex: "none", font: "600 9px 'IBM Plex Mono',monospace", color: sg.fg, background: sg.bg, borderRadius: 999, padding: "2px 8px" }}>{sg.sig}</span></div>{summary && <p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{summary}</p>}<div style={{ display: "flex", gap: 12, font: "500 10px 'IBM Plex Mono',monospace", color: "var(--text-mute)", flexWrap: "wrap" }}>{lang && <span>{lang}</span>}<span>★ {compactNum(rp.stars)}</span>{speed > 0 && <span style={{ color: "var(--good)" }}>▲ {Math.round(speed)}/天</span>}{pushed && <span>{pushed}</span>}</div></div>
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
      {repoDetail && <GithubRepoDetail repo={repoDetail} onClose={() => setRepoDetail(null)} />}
    </div>
  );
}

// 问题3:GitHub 项目详情——先看清楚是个啥(中文介绍/指标/相关性/下一步),再决定要不要跳转。
function GithubRepoDetail({ repo, onClose }: { repo: IntelRepo; onClose: () => void }) {
  const name = repo.repo_full_name || "GitHub 项目";
  const speed = typeof repo.stars_per_day === "number" ? repo.stars_per_day : 0;
  const topics = Array.isArray(repo.display_topics) && repo.display_topics.length ? repo.display_topics : (Array.isArray(repo.topics) ? repo.topics : []);
  const block = (label: string, body?: string) => body ? (
    <div style={{ display: "grid", gap: 4 }}>
      <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".12em", color: "var(--text-mute)" }}>{label}</span>
      <p style={{ margin: 0, font: "400 12.5px/1.6 'Space Grotesk',sans-serif", color: "var(--text-dim)" }}>{body}</p>
    </div>
  ) : null;
  const footer = (
    <div style={{ ...row(8) }}>
      <span style={flex1} />
      {repo.url && <button onClick={() => window.open(repo.url, "_blank", "noopener,noreferrer")} style={{ ...row(6), border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 9, padding: "9px 16px", font: "600 12px 'Space Grotesk'" }}>
        打开 GitHub<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M7 17 17 7M9 7h8v8" /></svg>
      </button>}
    </div>
  );
  return (
    <Drawer open onClose={onClose} level="sheet" eyebrow="GitHub 项目" title={name} footer={footer}>
      <div style={{ display: "grid", gap: 14 }}>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", font: "500 11px 'IBM Plex Mono',monospace", color: "var(--text-dim)" }}>
          {repo.language && <span>语言 {repo.language}</span>}
          <span>★ {compactNum(repo.stars)}</span>
          {typeof repo.forks === "number" && <span>Fork {compactNum(repo.forks)}</span>}
          {speed > 0 && <span style={{ color: "var(--good)" }}>▲ {Math.round(speed)}/天</span>}
          {githubPushedAgo(repo.pushed_at) && <span>{githubPushedAgo(repo.pushed_at)}</span>}
        </div>
        {topics.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{topics.slice(0, 8).map((t, i) => <span key={i} style={{ font: "500 10.5px 'Space Grotesk',sans-serif", color: "var(--text-dim)", background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 999, padding: "3px 10px" }}>{t}</span>)}</div>}
        {block("项目介绍", repo.summary_zh || repo.display_description || repo.description)}
        {block("为什么进雷达", repo.why_zh)}
        {block("和你的关系", repo.relation_zh)}
        {block("建议下一步", repo.next_step_zh)}
      </div>
    </Drawer>
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
  if (s.source_url) return "[链]";
  if (s.source === "attachment_import") return "[附]";
  if (s.source === "source_text") return "[文]";
  return "[档]";
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
  async function del() { if (!selId) { onClose(); return; } if (!window.confirm("删除这条？")) return; try { await deleteNote(selId); onSaved(); onClose(); } catch { alert("删除失败，请重试"); } }
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
          <button onClick={() => setPinned((v) => !v)} title="置顶" style={{ border: "1px solid var(--border)", background: pinned ? "var(--accent-soft)" : "var(--panel-2)", cursor: "pointer", borderRadius: 7, width: 30, height: 30, display: "grid", placeContent: "center" }}><svg width="13" height="13" viewBox="0 0 24 24" fill={pinned ? "var(--accent)" : "none"} stroke={pinned ? "var(--accent)" : "var(--text-mute)"} strokeWidth="1.8"><path d="M9 4v6l-2 3v2h10v-2l-2-3V4z" /><path d="M12 17v3" /></svg></button>
          <button onClick={del} title="删除" style={{ border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--bad)", cursor: "pointer", borderRadius: 7, width: 30, height: 30, display: "grid", placeContent: "center" }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" /></svg></button>
          <button onClick={save} disabled={saving} style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", borderRadius: 8, padding: "7px 15px", font: "600 12px 'Space Grotesk'", opacity: saving ? 0.6 : 1 }}>{saving ? "保存中" : "保存"}</button>
        </div>
        <div style={{ ...row(7), padding: "8px 14px", borderBottom: "1px solid var(--border-soft)", flexWrap: "wrap" }}>
          {tool("B", () => insert("**粗体**"), "加粗")}{tool("H", () => insert("\n## 小标题\n"), "标题")}{tool("•", () => insert("\n- 列表项\n"), "列表")}{tool("链接", () => insert("[文字](https://)"))}{tool("图片", () => fileRef.current?.click(), "插入图片")}{tool("附件", () => attachRef.current?.click(), "插入附件")}
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
const STUDIO_ICON: Record<string, string> = { overview: "概览", faq: "问答", timeline: "时间线", briefing: "简报", study_guide: "学习" };

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
  const [researchOpen, setResearchOpen] = useState(false);  // 深入调研(问题2:从记事发起)
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
        <div style={{ ...row(8), padding: "13px 14px 9px" }}><span style={lbl}>笔记本</span><span style={flex1} /><span style={mono(9.5, "var(--accent)")}>{ws.sources.length} 来源</span></div>
        {/* 笔记本切换 */}
        <div style={{ ...row(6), padding: "0 12px 10px", overflowX: "auto", flexWrap: "nowrap" }}>
          {[{ name: "", note_count: 0, source_count: 0 } as NotebookMeta, ...notebooks.filter((n) => n.name && n.name !== "未归档"), ...notebooks.filter((n) => n.name === "未归档")].map((n) => { const on = nb === n.name; const label = n.name || "全部"; return (
            <button key={label} onClick={() => setNb(n.name)} className="cx-chip" style={{ flex: "none", border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`, background: on ? "var(--accent-soft)" : "var(--panel-2)", color: on ? "var(--accent)" : "var(--text-dim)", cursor: "pointer", borderRadius: 999, padding: "5px 12px", font: "600 11px 'Space Grotesk'" }}>{label}</button>
          ); })}
          <button onClick={() => { const name = window.prompt("新建笔记本名称："); if (name && name.trim()) { setNb(name.trim()); flash("已切到「" + name.trim() + "」，加来源即生效"); } }} title="新建笔记本" style={{ flex: "none", border: "1px dashed var(--border)", background: "transparent", color: "var(--text-mute)", cursor: "pointer", borderRadius: 999, padding: "5px 11px", font: "700 12px 'Space Grotesk'" }}>＋</button>
        </div>
        {/* 添加来源 */}
        <div style={{ ...row(6), padding: "0 12px 10px" }}>
          <button onClick={addUrl} className="cx-chip" style={{ flex: 1, border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "7px 4px", font: "600 11px 'Space Grotesk'" }}>＋ 链接</button>
          <button onClick={() => fileRef.current?.click()} className="cx-chip" style={{ flex: 1, border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "7px 4px", font: "600 11px 'Space Grotesk'" }}>＋ 文件</button>
          <button onClick={() => setTextModal(true)} className="cx-chip" style={{ flex: 1, border: "1px solid var(--border)", background: "var(--panel-2)", color: "var(--text-dim)", cursor: "pointer", borderRadius: 8, padding: "7px 4px", font: "600 11px 'Space Grotesk'" }}>＋ 文本</button>
          <input ref={fileRef} type="file" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) addFile(f); e.currentTarget.value = ""; }} />
        </div>
        {/* 深入调研:多源搜索→读源→带来源报告(问题2:并入记事) */}
        <div style={{ padding: "0 12px 10px" }}>
          <button onClick={() => setResearchOpen(true)} className="cx-chip" style={{ width: "100%", ...row(7), justifyContent: "center", border: "1px solid var(--accent)", background: "var(--accent-soft)", color: "var(--accent)", cursor: "pointer", borderRadius: 8, padding: "8px 0", font: "600 11.5px 'Space Grotesk'" }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>深入调研 → 生成报告
          </button>
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
          <span style={{ width: 30, height: 30, borderRadius: 9, background: "var(--accent-soft)", border: "1px solid var(--accent-line)", display: "grid", placeContent: "center", flex: "none", font: "600 11px 'IBM Plex Mono'", color: "var(--accent)" }}>NB</span>
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
          <div style={{ ...row(8) }}><span style={lbl}>工作室</span><span style={flex1} /></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 9 }}>
            {(ws.templates.length ? ws.templates : [{ id: "overview", label: "文档概览", tag: "" }, { id: "faq", label: "常见问答", tag: "" }, { id: "timeline", label: "时间线", tag: "" }, { id: "briefing", label: "简报文档", tag: "" }, { id: "study_guide", label: "学习指南", tag: "" }]).map((t) => (
              <button key={t.id} onClick={() => runStudio(t.id)} disabled={!!studioBusy || !ws.sources.length} className="cx-chip" style={{ border: "1px solid var(--border)", background: studioBusy === t.id ? "var(--accent-soft)" : "var(--panel-2)", color: "var(--text-dim)", cursor: ws.sources.length ? "pointer" : "default", borderRadius: 9, padding: "9px 6px", font: "600 11px 'Space Grotesk'", opacity: ws.sources.length ? 1 : 0.5, display: "grid", gap: 2, lineHeight: 1.2 }}>
                <span style={{ font: "600 9px 'IBM Plex Mono'", color: "var(--accent)" }}>{STUDIO_ICON[t.id] || "·"}</span>{studioBusy === t.id ? "生成中…" : t.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ ...row(8), padding: "8px 14px 8px", borderTop: "1px solid var(--border-soft)" }}><span style={lbl}>笔记 · NOTES</span><span style={flex1} /><span style={mono(9.5, "var(--text-dim)")}>{ws.notes.length}</span><button onClick={() => setEditId(null)} title="新建笔记" style={{ border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", width: 22, height: 22, borderRadius: 6, font: "700 14px 'Space Grotesk'", lineHeight: 0 }}>＋</button></div>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "0 10px 12px", display: "grid", gap: 7, alignContent: "start" }}>
          {ws.notes.length === 0 && <div style={{ ...mono(10), padding: "16px 6px", textAlign: "center", lineHeight: 1.7 }}>还没有笔记。<br />用上面的工作室一键生成，<br />或点 ＋ 手写一条。</div>}
          {ws.notes.map((n) => { const ai = (n.tags || []).includes("AI工作室") || n.source === "ai_studio" || n.source === "ai_transform"; return (
            <button key={n.id} onClick={() => setEditId(n.id)} className="cx-row" style={{ textAlign: "left", background: "var(--panel-2)", border: "1px solid var(--border-soft)", borderRadius: 10, padding: "9px 11px", cursor: "pointer", display: "grid", gap: 4 }}>
              <div style={{ ...row(6) }}>{n.pinned && <svg width="9" height="9" viewBox="0 0 24 24" fill="var(--accent)"><path d="M9 4v6l-2 3v2h10v-2l-2-3V4z" /></svg>}{ai && <span style={{ ...mono(8, "var(--accent)"), background: "var(--accent-soft)", borderRadius: 4, padding: "1px 5px" }}>AI</span>}<b style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{n.title || "未命名"}</b></div>
              <p style={{ margin: 0, font: "400 10.5px/1.5 'Space Grotesk',sans-serif", color: "var(--text-dim)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{n.excerpt || ""}</p>
            </button>
          ); })}
        </div>
      </div>

      {toast && <div className="cx-pop-in" style={{ position: "absolute", bottom: 22, left: "50%", transform: "translateX(-50%)", background: "var(--panel)", border: "1px solid var(--accent)", borderRadius: 999, padding: "8px 18px", font: "600 12px 'Space Grotesk'", color: "var(--text)", boxShadow: "var(--shadow)", zIndex: 50 }}>{toast}</div>}
      {researchOpen && <ResearchCard onClose={() => setResearchOpen(false)} />}

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
        {typeof m.battery_percent === "number" && <span style={mono(9.5)}>电池 <b style={{ color: "var(--text)" }}>{m.battery_percent}%</b>{m.battery_plugged ? " 充电" : ""}</span>}
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
// ============ 问题11: 设置·能力与自动化(给新增能力配齐自定义项) ============
function CapabilitiesSettings({ card, h2, Switch }: { card: CSSProperties; h2: (t: string, d: string) => ReactNode; Switch: (p: { on: boolean; onClick: () => void }) => ReactNode }) {
  const [cfg, setCfg] = useState<AssistantConfig | null>(null);
  const [mcp, setMcp] = useState<McpStatus | null>(null);
  const [sched, setSched] = useState(0);
  const [senseN, setSenseN] = useState(0);
  useEffect(() => {
    getAssistantConfig().then((d) => setCfg(d.config)).catch(() => {});
    getMcpStatus().then(setMcp).catch(() => {});
    getSchedule().then((d) => setSched(d.stats?.pending ?? (d.items?.length || 0))).catch(() => {});
    try { setSenseN(Object.values(loadSenseState()).filter((s) => s.status === "connected").length); } catch { /* ignore */ }
  }, []);
  const saveCfg = async (patch: Partial<AssistantConfig>) => { const d = await patchAssistantConfig(patch); setCfg(d.config); };
  const rows: { name: string; desc: string; right: ReactNode }[] = [
    { name: "主动助理", desc: "每日 check-in + 自定义后台自动任务(在 Jarvis 对话弹窗→主动助理 里配)", right: cfg ? Switch({ on: cfg.enabled, onClick: () => saveCfg({ enabled: !cfg.enabled }) }) : <span style={mono(10)}>…</span> },
    { name: "日程提醒", desc: `到点桌面/应内/iOS 推送。当前 ${sched} 条待办日程`, right: <span style={mono(10, "var(--text-dim)")}>{sched} 条</span> },
    { name: "感知接入", desc: `浏览器原生权限投喂上下文,授权状态已持久化。已接入 ${senseN} 个通道`, right: <span style={mono(10, senseN > 0 ? "var(--good)" : "var(--text-dim)")}>{senseN}/9</span> },
    { name: "MCP 服务", desc: "外部能力接入(搜索/抓取/工具)。在顶栏「技能与 MCP」里开关、填密钥", right: <span style={mono(10, "var(--text-dim)")}>{mcp?.summary ? `${mcp.summary.ready}/${mcp.summary.total} 就绪` : "…"}</span> },
    { name: "技能库", desc: "agent 自动提炼 + 手动/GitHub 导入,相关问题自动复用。顶栏「技能与 MCP」管理", right: <span style={mono(10, "var(--text-dim)")}>顶栏图标</span> },
    { name: "深入调研", desc: "多源搜索→读源→带来源报告。在 记事 里发起", right: <span style={mono(10, "var(--text-dim)")}>记事内</span> },
  ];
  return (<>
    {h2("能力与自动化", "这台 Jarvis 新增的能力总览与开关。更细的配置在各自的入口(对话弹窗 / 顶栏图标 / 各页)里。")}
    <div style={{ display: "grid", gap: 12, maxWidth: 640 }}>
      {rows.map((r) => (
        <div key={r.name} style={{ ...card, ...row(13) }}>
          <div style={{ flex: 1, minWidth: 0 }}><div style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>{r.name}</div><div style={{ font: "400 11px/1.5 'Space Grotesk'", color: "var(--text-mute)", marginTop: 2 }}>{r.desc}</div></div>
          <span style={{ flex: "none" }}>{r.right}</span>
        </div>
      ))}
      {cfg && (
        <div style={{ ...card, display: "grid", gap: 10 }}>
          <div style={{ font: "600 12.5px 'Space Grotesk'", color: "var(--text)" }}>助理身份</div>
          <input value={cfg.name} onChange={(e) => setCfg({ ...cfg, name: e.target.value })} onBlur={() => saveCfg({ name: cfg.name })} placeholder="名字" style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", color: "var(--text)", font: "400 12.5px 'Space Grotesk'", outline: "none" }} />
          <textarea value={cfg.persona} onChange={(e) => setCfg({ ...cfg, persona: e.target.value })} onBlur={() => saveCfg({ persona: cfg.persona })} rows={2} placeholder="人格/口吻" style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", color: "var(--text)", font: "400 12.5px 'Space Grotesk'", outline: "none", resize: "vertical" }} />
        </div>
      )}
      <div style={{ ...mono(10.5), lineHeight: 1.7 }}>更细配置位:邮件 IMAP / CalDAV 日历 / 搜索源(SearXNG·Brave·Tavily) 在 config/settings.toml 对应块;密钥不进 Git。</div>
    </div>
  </>);
}

type SetTab = "appearance" | "capabilities" | "models" | "sources" | "notify" | "amap" | "system";
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

  const tabMeta: [SetTab, string][] = [["appearance", "外观与动效"], ["capabilities", "能力与自动化"], ["models", "模型路由"], ["sources", "情报源"], ["notify", "通知"], ["amap", "高德地图"], ["system", "系统与守卫"]];
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
        <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--text-mute)", padding: "8px 10px 10px" }}>设置台</div>
        {tabMeta.map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{ textAlign: "left", border: 0, cursor: "pointer", ...row(10), padding: "11px 11px", borderRadius: 10, background: tab === id ? "var(--panel-2)" : "transparent" }}><span style={{ width: 3, height: 15, borderRadius: 3, background: tab === id ? "var(--accent)" : "transparent", flex: "none" }} /><div style={{ font: "600 12.5px 'Space Grotesk',sans-serif", color: tab === id ? "var(--text)" : "var(--text-dim)", whiteSpace: "nowrap" }}>{label}</div></button>
        ))}
        {savedAt > 0 && <div style={{ ...mono(9.5, "var(--good)"), padding: "10px 11px" }}>{saving ? "保存中…" : "已保存"}</div>}
      </div>

      <div style={{ ...panel, overflowY: "auto", minHeight: 0, padding: "24px 26px" }}>
        {tab === "appearance" && (<>
          {h2("外观与动效", "深色 / 浅色双主题，酒红冷光强调色。扫描线氛围可关。")}
          <div style={{ display: "grid", gap: 14, maxWidth: 620 }}>
            <div style={card}><div style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)", marginBottom: 12 }}>主题模式</div><div style={{ display: "flex", gap: 10 }}>{(["auto", "light", "dark"] as Theme[]).map((m) => (<button key={m} onClick={() => setTheme(m)} style={{ flex: 1, cursor: "pointer", border: `1px solid ${theme === m ? "var(--accent)" : "var(--border)"}`, background: theme === m ? "var(--accent-soft)" : "var(--panel)", color: theme === m ? "var(--accent)" : "var(--text-dim)", borderRadius: 10, padding: "12px 0", font: "600 13px 'Space Grotesk'" }}>{m === "auto" ? "跟随系统" : m === "light" ? "浅色" : "深色"}</button>))}</div></div>
            <div style={{ ...card, ...row(14) }}><div style={{ flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)" }}>强调色</div><div style={{ font: "400 11px 'Space Grotesk'", color: "var(--text-mute)", marginTop: 2 }}>酒红 burgundy（已应用全局）</div></div><span style={{ width: 30, height: 30, borderRadius: 9, background: "var(--accent)", boxShadow: "0 0 0 2px var(--panel),0 0 0 4px var(--accent)" }} /></div>
            <div style={{ ...card, ...row(14) }}><div style={{ flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk'", color: "var(--text)" }}>扫描线氛围</div><div style={{ font: "400 11px 'Space Grotesk'", color: "var(--text-mute)", marginTop: 2 }}>顶部冷光扫描（已收窄变慢）</div></div><Switch on={scan} onClick={toggleScan} /></div>
          </div>
        </>)}

        {tab === "capabilities" && <CapabilitiesSettings card={card} h2={h2} Switch={Switch} />}

        {tab === "models" && (<>
          {h2("模型路由", "全部 LLM 已切到 DeepSeek。首选失败自动回退到备选。")}
          <div style={{ display: "grid", gap: 12, maxWidth: 620 }}>
            {[["首选 · 中枢/判断/翻译", "deepseek-v4-flash", "已生效"], ["备选 · 自动回退", "deepseek-v4-pro", "待命"]].map(([role, model, st]) => (
              <div key={model} style={{ ...card, display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "center" }}>
                <div><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "var(--text)" }}>{role}</div><div style={{ font: "500 12px 'IBM Plex Mono',monospace", color: "var(--accent)", marginTop: 3 }}>{model}</div><div style={{ ...mono(9.5), marginTop: 2 }}>https://api.deepseek.com</div></div>
                <span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: st === "已生效" ? "var(--good)" : "var(--text-dim)", background: st === "已生效" ? "var(--good-soft)" : "var(--panel)", borderRadius: 999, padding: "5px 10px" }}>{st}</span>
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
