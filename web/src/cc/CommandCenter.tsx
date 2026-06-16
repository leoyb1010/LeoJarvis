import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { getCliAgents, getCliSessions, runCliAgent, stopCliSession, fmtAgo, type CliAgent, type CliSession } from "./live";

const TAG: Record<string, [string, string]> = { claude: ["CC", "#ff7a45"], codex: ["CX", "#36d39a"], cursor: ["CU", "#4da3ff"], grok: ["GK", "#b69cff"], gemini: ["GM", "#ffb454"], opencode: ["OC", "#9aa6b2"] };

// Cortex · 指挥台 — pixel-faithful React port of the design (Cortex 驾驶舱重设计.dc.html).
// Pages: 驾驶舱 / 智能体 / 情报 / 设置台. Dark near-black + single amber cold-light accent.

const A = (f: string) => `/cc/${f}`; // design assets live in public/cc/

type Page = "cockpit" | "agents" | "intel" | "settings";
type SetTab = "models" | "sources" | "guard" | "mcp" | "devices" | "appearance";

const panel: CSSProperties = { background: "#0e1218", border: "1px solid #1c222b", borderRadius: 15, padding: 16 };
const sub: CSSProperties = { background: "#0b0e13", border: "1px solid #1c222b", borderRadius: 13 };
const lbl: CSSProperties = { font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".18em", color: "#6b7480" };
const mono = (s = 10, c = "#6b7480"): CSSProperties => ({ font: `500 ${s}px 'IBM Plex Mono',monospace`, color: c });
const row = (g = 8): CSSProperties => ({ display: "flex", alignItems: "center", gap: g });
const flex1: CSSProperties = { flex: 1 };

// ---- live waveform canvas (cx-cpu freq 5, cx-orch freq 8) ----
function useWave(id: string, freq: number, alive: React.MutableRefObject<boolean>) {
  useEffect(() => {
    let phase = Math.random() * 6;
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
      phase += 0.045;
      const draw = (alpha: number, lw: number) => {
        ctx.globalAlpha = alpha; ctx.lineWidth = lw; ctx.strokeStyle = "#ff7a45"; ctx.beginPath();
        for (let x = 0; x <= w; x += 2) {
          const env = 0.4 + 0.6 * Math.sin((x / w) * Math.PI);
          const y = h / 2 + Math.sin((x / w) * Math.PI * freq + phase) * (h * 0.3) * env * (0.6 + 0.4 * Math.sin(phase * 0.7 + x / 36));
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      };
      draw(0.22, 5); draw(1, 1.6); ctx.globalAlpha = 1;
    };
    run();
    return () => cancelAnimationFrame(raf);
  }, [id, freq, alive]);
}

export default function CommandCenter() {
  const [page, setPage] = useState<Page>("cockpit");
  const [tab, setTab] = useState<SetTab>("models");
  const [now, setNow] = useState(new Date());
  const [cmd, setCmd] = useState("");
  const [sync, setSync] = useState(true);
  const [scan, setScan] = useState(true);
  const alive = useRef(true);

  useWave("cx-cpu", 5, alive);
  useWave("cx-orch", 8, alive);

  useEffect(() => {
    alive.current = true;
    const clock = setInterval(() => setNow(new Date()), 1000);
    return () => { alive.current = false; clearInterval(clock); };
  }, []);

  const pad = (n: number) => String(n).padStart(2, "0");
  const clock = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  const META: Record<Page, [string, string]> = { cockpit: ["全景驾驶舱", "COCKPIT"], agents: ["智能体编排", "AGENTS · SYNC"], intel: ["情报中心", "INTELLIGENCE"], settings: ["设置台", "SETTINGS"] };
  const nav = (p: Page) => ({ fg: page === p ? "#ff7a45" : "#5a626d", bg: page === p ? "rgba(255,122,69,.09)" : "transparent", bar: page === p ? "#ff7a45" : "transparent" });

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
    <div style={{ height: "100vh", display: "grid", gridTemplateColumns: "68px 1fr", background: "#0a0c10", fontFamily: "'Space Grotesk','PingFang SC','Microsoft YaHei',sans-serif", overflow: "hidden" }}>
      <nav style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "14px 0", background: "#0c0f14", borderRight: "1px solid #161b22" }}>
        <img src={A("brand-mark.png")} alt="" style={{ width: 40, height: 40, borderRadius: 11, objectFit: "cover", boxShadow: "0 0 0 1px #262d37,0 0 18px rgba(255,122,69,.2)", marginBottom: 10 }} />
        {navBtn("cockpit", "驾驶舱", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="2" /><rect x="3" y="13.5" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" /></svg>)}
        {navBtn("agents", "智能体", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="5" r="2.4" /><circle cx="5.5" cy="18" r="2.4" /><circle cx="18.5" cy="18" r="2.4" /><path d="M12 7.4v3M11 12l-4 4M13 12l4 4" /></svg>)}
        {navBtn("intel", "情报", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12l6-6" /></svg>)}
        <span style={flex1} />
        {navBtn("settings", "设置台", <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></svg>)}
      </nav>

      <div style={{ display: "grid", gridTemplateRows: "58px 1fr", minWidth: 0, minHeight: 0 }}>
        <header style={{ ...row(16), padding: "0 18px", borderBottom: "1px solid #161b22", background: "#0b0e13" }}>
          <div style={{ flex: "none", minWidth: 128 }}>
            <div style={{ font: "600 14.5px 'Space Grotesk',sans-serif", color: "#e8ecf1", lineHeight: 1.1 }}>{META[page][0]}</div>
            <div style={{ font: "500 9px 'IBM Plex Mono',monospace", letterSpacing: ".2em", color: "#5a626d", marginTop: 2 }}>{META[page][1]}</div>
          </div>
          <div style={{ flex: 1, ...row(11), background: "#0e1218", border: "1px solid #232a33", borderRadius: 12, padding: "0 14px", height: 38, boxShadow: "inset 0 0 0 1px rgba(255,122,69,.04)" }}>
            <span style={{ font: "600 14px 'IBM Plex Mono',monospace", color: "#ff7a45" }}>&gt;_</span>
            <input value={cmd} onChange={(e) => setCmd(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") setCmd(""); }} placeholder="对它说一句话，或输入命令…" style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "#e8ecf1", font: "500 13.5px 'Space Grotesk',sans-serif" }} />
            <span style={{ display: "inline-block", width: 7, height: 15, background: "#ff7a45", animation: "cxBlink 1.1s step-end infinite" }} />
            <kbd style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "#6b7480", border: "1px solid #2a323d", borderRadius: 5, padding: "2px 6px" }}>⌘K</kbd>
          </div>
          <div style={{ flex: "none", ...row(9), font: "600 11px 'IBM Plex Mono',monospace" }}>
            <span style={{ ...row(5), background: "#0e1218", border: "1px solid #1c222b", borderRadius: 8, padding: "5px 9px", color: "#aab2bd" }}><b style={{ width: 6, height: 6, borderRadius: "50%", background: "#36d39a", display: "inline-block", animation: "cxBreathe 4s ease infinite" }} />健康 <b style={{ color: "#e8ecf1" }}>86</b></span>
            <span style={{ ...row(5), background: "#0e1218", border: "1px solid #1c222b", borderRadius: 8, padding: "5px 9px", color: "#aab2bd" }}>CPU <b style={{ color: "#e8ecf1" }}>27%</b></span>
            <span style={{ ...row(5), background: "#0e1218", border: "1px solid #1c222b", borderRadius: 8, padding: "5px 9px", color: "#aab2bd" }}>服务 <b style={{ color: "#36d39a" }}>5/6</b></span>
            <span style={{ width: 1, height: 20, background: "#262d37" }} />
            <span style={{ color: "#e8ecf1", letterSpacing: ".04em" }}>{clock}</span>
          </div>
        </header>

        <div style={{ position: "relative", minHeight: 0, overflow: "hidden", backgroundImage: "linear-gradient(rgba(255,255,255,.016) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.016) 1px,transparent 1px)", backgroundSize: "38px 38px", animation: "cxGrid 18s linear infinite" }}>
          <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 30, background: "linear-gradient(180deg,rgba(255,122,69,.045),transparent)", height: "30%", animation: "cxScan 8s linear infinite", opacity: scan ? 1 : 0 }} />

          {page === "cockpit" && <Cockpit goIntel={() => setPage("intel")} />}
          {page === "agents" && <Agents sync={sync} toggleSync={() => setSync((v) => !v)} />}
          {page === "intel" && <Intel />}
          {page === "settings" && <Settings tab={tab} setTab={setTab} scan={scan} toggleScan={() => setScan((v) => !v)} />}
        </div>
      </div>
    </div>
  );
}

// ============ COCKPIT ============
function Cockpit({ goIntel }: { goIntel: () => void }) {
  const svc = (name: string, port: number, online: boolean) => ({ name, port, dot: online ? "#36d39a" : "#ff5d5d", glow: online ? "rgba(54,211,154,.6)" : "rgba(255,93,93,.5)" });
  const services = [svc("LeoJarvis", 8787, true), svc("Ollama", 11434, true), svc("LeoNote", 3000, true), svc("LeoAPI", 8000, true), svc("LeoMoney", 5001, false), svc("CloudCLI", 7070, true)];
  const PRI: Record<string, [string, string]> = { 高优先: ["#fff", "#ff5d5d"], 简报: ["#ff7a45", "rgba(255,122,69,.16)"], 观察: ["#aab2bd", "rgba(255,255,255,.06)"] };
  const intelTop = [
    { pri: "高优先", source: "Hacker News", time: "08:12", title: "Anthropic 发布新一代本地代理协议" },
    { pri: "高优先", source: "邮件", time: "07:58", title: "投资人回信：下周见面确认" },
    { pri: "简报", source: "GitHub Trending", time: "07:40", title: "local-first AI agent 框架一周 star 翻倍" },
  ];
  const steps = [{ cmd: "disk_hotspots", status: "完成", bar: "#36d39a" }, { cmd: "system_status", status: "完成", bar: "#36d39a" }, { cmd: "rm -rf caches", status: "待确认", bar: "#ffb454" }];
  const suggestions = ["本地服务都还活着吗", "今天有什么高优先情报", "派 3 个子智能体并行", "整理今天的记事"];
  const mails = [{ f: "mail.png", n: "Mail", c: 3 }, { f: "wechat.png", n: "微信", c: 12 }, { f: "telegram.png", n: "Telegram", c: 5 }, { f: "popo.png", n: "POPO", c: 0 }, { f: "mailmaster.png", n: "网易邮箱", c: 1 }];
  const notes = [{ when: "今天 09:02", title: "LeoJarvis V2 重构要点", body: "中枢对话 + 工具总线 + 行动闸门；驾驶舱并入记事小区域。" }, { when: "昨天 22:14", title: "情报源清单", body: "补充 arXiv、雪球、V2EX 三个源到 sources.toml。" }];
  const T = (time: string, title: string, done: boolean) => ({ time, title, check: done ? "✓" : "", box: done ? "#ff7a45" : "#3a424d", fill: done ? "#ff7a45" : "transparent", timeFg: done ? "#6b7480" : "#ff7a45", titleFg: done ? "#6b7480" : "#e8ecf1" });
  const todos = [T("10:00", "评估 Claude 本地代理协议", false), T("14:30", "修复 LeoMoney 掉线", false), T("已完成", "巡检磁盘热点", true)];

  return (
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateColumns: "298px minmax(0,1fr) 330px", gap: 14, padding: 16, minHeight: 0 }}>
      {/* LEFT */}
      <div style={{ display: "grid", gridTemplateRows: "auto auto minmax(0,1fr)", gap: 14, minHeight: 0 }}>
        <div style={panel}>
          <div style={{ ...row(8), marginBottom: 13 }}><span style={lbl}>SYSTEM HEALTH</span><span style={flex1} /><span style={mono(10, "#36d39a")}>● 平稳</span></div>
          <div style={row(16)}>
            <div style={{ position: "relative", width: 92, height: 92, flex: "none" }}>
              <svg width="92" height="92" viewBox="0 0 92 92" style={{ transform: "rotate(-90deg)" }}><circle cx="46" cy="46" r="40" fill="none" stroke="#1c222b" strokeWidth="7" /><circle cx="46" cy="46" r="40" fill="none" stroke="#ff7a45" strokeWidth="7" strokeLinecap="round" strokeDasharray="251.3" strokeDashoffset="35.2" style={{ filter: "drop-shadow(0 0 5px rgba(255,122,69,.6))" }} /></svg>
              <div style={{ position: "absolute", inset: 0, display: "grid", placeContent: "center", textAlign: "center" }}><div style={{ font: "700 30px 'Space Grotesk',sans-serif", color: "#e8ecf1", lineHeight: 1, animation: "cxGlow 5s ease infinite" }}>86</div></div>
            </div>
            <div style={{ display: "grid", gap: 8, flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", font: "500 11px 'IBM Plex Mono',monospace" }}><span style={{ color: "#aab2bd" }}>SSD</span><b style={{ color: "#e8ecf1" }}>74%</b></div>
              <div style={{ height: 4, borderRadius: 4, background: "#1c222b", overflow: "hidden" }}><i style={{ display: "block", height: "100%", width: "74%", background: "#ffb454", borderRadius: 4 }} /></div>
              <div style={{ display: "flex", justifyContent: "space-between", font: "500 11px 'IBM Plex Mono',monospace" }}><span style={{ color: "#aab2bd" }}>RAM</span><b style={{ color: "#e8ecf1" }}>68%</b></div>
              <div style={{ height: 4, borderRadius: 4, background: "#1c222b", overflow: "hidden" }}><i style={{ display: "block", height: "100%", width: "68%", background: "#36d39a", borderRadius: 4 }} /></div>
            </div>
          </div>
        </div>

        <div style={panel}>
          <div style={{ ...row(8), marginBottom: 4 }}><span style={lbl}>CPU · LIVE</span><span style={flex1} /><b style={{ font: "700 15px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>2.14<i style={{ font: "500 10px 'IBM Plex Mono'", color: "#6b7480", fontStyle: "normal" }}> /8核</i></b></div>
          <canvas id="cx-cpu" style={{ width: "100%", height: 44, display: "block" }} />
        </div>

        <div style={{ ...panel, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0 }}>
          <div style={{ ...row(8), marginBottom: 12 }}><span style={lbl}>LOCAL SERVICES</span><span style={flex1} /><span style={mono(10, "#aab2bd")}>5/6</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, overflowY: "auto", minHeight: 0, alignContent: "start" }}>
            {services.map((s) => (
              <div key={s.name} style={{ ...row(8), background: "#0b0e13", border: "1px solid #1a2029", borderRadius: 10, padding: "9px 10px" }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.dot, flex: "none", boxShadow: `0 0 7px ${s.glow}` }} />
                <div style={{ minWidth: 0 }}><div style={{ font: "600 11.5px 'Space Grotesk',sans-serif", color: "#e8ecf1", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</div><div style={mono(9)}>:{s.port}</div></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* MID — AGENT 中枢 */}
      <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", minHeight: 0, overflow: "hidden" }}>
        <div style={{ ...row(9), padding: "16px 18px 12px", borderBottom: "1px solid #161b22" }}><img src={A("brand-mark.png")} alt="" style={{ width: 26, height: 26, borderRadius: 7, objectFit: "cover" }} /><div><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "#ff7a45" }}>AGENT 中枢</div></div><span style={flex1} /><span style={mono(10)}>工具总线 · 行动闸门</span></div>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 11 }}>
          <div style={{ alignSelf: "flex-end", maxWidth: "78%", background: "#ff7a45", color: "#1a0f08", font: "500 13.5px 'Space Grotesk',sans-serif", padding: "10px 14px", borderRadius: 13, borderBottomRightRadius: 4, lineHeight: 1.5 }}>看看我磁盘为什么快满了</div>
          <div style={{ alignSelf: "flex-start", display: "grid", gap: 6, width: "90%" }}>
            {steps.map((st) => (
              <div key={st.cmd} style={{ ...row(9), background: "#0b0e13", border: "1px solid #1a2029", borderLeft: `3px solid ${st.bar}`, borderRadius: 9, padding: "8px 11px" }}><code style={{ font: "600 11.5px 'IBM Plex Mono',monospace", color: st.bar }}>{st.cmd}</code><span style={flex1} /><span style={mono(10)}>{st.status}</span></div>
            ))}
          </div>
          <div style={{ alignSelf: "flex-start", maxWidth: "90%", background: "#0b0e13", border: "1px solid #1c222b", color: "#cdd3db", font: "400 13.5px/1.62 'Space Grotesk',sans-serif", padding: "12px 15px", borderRadius: 13, borderBottomLeftRadius: 4 }}>已扫描系统盘：占用 74%。最大三个热点是 ~/Library/Caches (18G)、Docker 镜像 (12G)、Xcode DerivedData (9G)。需要我清理可回收的缓存吗？</div>
          <div style={{ alignSelf: "flex-start", ...row(9), background: "rgba(255,180,84,.07)", border: "1px solid rgba(255,180,84,.3)", borderRadius: 11, padding: "10px 13px", maxWidth: "90%" }}><span style={{ font: "600 10.5px 'IBM Plex Mono',monospace", color: "#ffb454", whiteSpace: "nowrap" }}>⚠ 待确认</span><code style={{ font: "500 11.5px 'IBM Plex Mono',monospace", color: "#ffd9a0", overflow: "hidden", textOverflow: "ellipsis" }}>rm -rf ~/Library/Caches/*</code><button style={{ border: 0, cursor: "pointer", background: "#ffb454", color: "#1a0f08", font: "600 10.5px 'Space Grotesk'", padding: "5px 11px", borderRadius: 6, whiteSpace: "nowrap" }}>确认</button></div>
        </div>
        <div style={{ padding: "12px 18px 16px", borderTop: "1px solid #161b22" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginBottom: 11 }}>
            {suggestions.map((sug) => (<button key={sug} className="cx-chip" style={{ border: "1px solid #232a33", background: "#0b0e13", color: "#aab2bd", cursor: "pointer", font: "500 11.5px 'Space Grotesk',sans-serif", padding: "6px 11px", borderRadius: 999 }}>{sug}</button>))}
          </div>
          <div style={{ ...row(10), background: "#0b0e13", border: "1px solid #232a33", borderRadius: 11, padding: "0 14px", height: 42 }}><span style={{ font: "600 13px 'IBM Plex Mono',monospace", color: "#ff7a45" }}>&gt;</span><input placeholder="继续对话…" style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "#e8ecf1", font: "500 13px 'Space Grotesk',sans-serif" }} /><button style={{ border: 0, cursor: "pointer", background: "#ff7a45", color: "#1a0f08", font: "600 11px 'Space Grotesk'", padding: "6px 13px", borderRadius: 7 }}>发送</button></div>
        </div>
      </div>

      {/* RIGHT */}
      <div style={{ display: "grid", gap: 14, overflowY: "auto", minHeight: 0, alignContent: "start", paddingRight: 2 }}>
        <div style={panel}>
          <div style={{ ...row(8), marginBottom: 12 }}><span style={lbl}>今日情报</span><span style={flex1} /><button onClick={goIntel} style={{ border: 0, background: "transparent", cursor: "pointer", font: "500 10px 'IBM Plex Mono',monospace", color: "#ff7a45" }}>查看全部 28 →</button></div>
          <div style={{ display: "grid", gap: 10 }}>
            {intelTop.map((it, i) => (
              <button key={i} className="cx-intel" style={{ textAlign: "left", border: 0, cursor: "pointer", background: "transparent", padding: "0 0 10px", borderBottom: "1px solid #161b22", display: "grid", gap: 4 }}><div style={row(7)}><span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: PRI[it.pri][0], background: PRI[it.pri][1], borderRadius: 999, padding: "2px 7px" }}>{it.pri}</span><span style={mono(9.5)}>{it.source} · {it.time}</span></div><b style={{ font: "600 12.5px/1.4 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{it.title}</b></button>
            ))}
          </div>
        </div>
        <div style={panel}>
          <div style={{ ...row(8), marginBottom: 13 }}><span style={lbl}>应用与邮件</span><span style={flex1} /><span style={mono(9)}>仅读计数</span></div>
          <div style={{ display: "flex", gap: 12 }}>
            {mails.map((m) => (
              <div key={m.n} style={{ position: "relative" }}>
                <img src={A(m.f)} alt={m.n} style={{ width: 38, height: 38, borderRadius: 10, display: "block", boxShadow: "0 0 0 1px #1c222b", opacity: m.c ? 1 : 0.5 }} />
                {m.c > 0 && <span style={{ position: "absolute", top: -5, right: -5, minWidth: 17, height: 17, padding: "0 4px", borderRadius: 9, background: "#ff5d5d", color: "#fff", font: "700 9px 'IBM Plex Mono'", display: "grid", placeContent: "center", border: "2px solid #0e1218" }}>{m.c}</span>}
              </div>
            ))}
          </div>
        </div>
        <div style={panel}>
          <div style={{ ...row(8), marginBottom: 12 }}><img src={A("leonote-icon.png")} alt="" style={{ width: 15, height: 15, borderRadius: 4 }} /><span style={lbl}>个人记事</span><span style={flex1} /><span style={{ font: "500 15px 'IBM Plex Mono',monospace", color: "#ff7a45", lineHeight: 0.6 }}>+</span></div>
          {notes.map((nt, i) => (
            <div key={i} style={{ borderLeft: "2px solid #232a33", padding: "0 0 9px 10px", marginBottom: 8 }}><div style={{ ...mono(9), marginBottom: 3 }}>{nt.when}</div><b style={{ font: "600 12px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{nt.title}</b><p style={{ margin: "3px 0 0", font: "400 11px/1.5 'Space Grotesk',sans-serif", color: "#8b94a0" }}>{nt.body}</p></div>
          ))}
        </div>
        <div style={panel}>
          <div style={{ ...row(8), marginBottom: 12 }}><span style={lbl}>今日日程</span></div>
          <div style={{ display: "grid", gap: 9 }}>
            {todos.map((td, i) => (
              <div key={i} style={row(10)}><span style={{ width: 14, height: 14, borderRadius: 5, border: `1.5px solid ${td.box}`, background: td.fill, flex: "none", display: "grid", placeContent: "center", font: "700 8px 'IBM Plex Mono'", color: "#0a0c10" }}>{td.check}</span><b style={{ font: "500 11.5px 'IBM Plex Mono',monospace", color: td.timeFg, flex: "none", width: 56 }}>{td.time}</b><span style={{ font: "500 12px 'Space Grotesk',sans-serif", color: td.titleFg }}>{td.title}</span></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ AGENTS ============
function Agents({ sync, toggleSync }: { sync: boolean; toggleSync: () => void }) {
  const [agents, setAgents] = useState<CliAgent[]>([]);
  const [sessions, setSessions] = useState<CliSession[]>([]);
  const [sel, setSel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    getCliAgents().then((d) => { setAgents(d.agents); const inst = d.agents.find((a) => a.installed); if (inst) setSel((s) => s || inst.name); }).catch(() => {});
    const poll = () => getCliSessions().then((d) => setSessions(d.sessions)).catch(() => {});
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { document.querySelectorAll("[data-term]").forEach((el) => { (el as HTMLElement).scrollTop = el.scrollHeight; }); }, [sessions]);

  const installed = agents.filter((a) => a.installed);
  const running = sessions.filter((s) => s.status === "running");

  async function run() {
    if (!prompt.trim() || !sel || busy) return;
    setBusy(true); setErr("");
    try { const r = await runCliAgent(sel, prompt.trim(), "~"); if (!r.ok) setErr(r.error || "启动失败"); else { setPrompt(""); getCliSessions().then((d) => setSessions(d.sessions)).catch(() => {}); } }
    catch (e: any) { setErr(String(e?.message || e)); } finally { setBusy(false); }
  }
  async function stop(id: string) { await stopCliSession(id).catch(() => {}); getCliSessions().then((d) => setSessions(d.sessions)).catch(() => {}); }

  const sFg = sync ? "#36d39a" : "#6b7480", sBg = sync ? "rgba(54,211,154,.1)" : "transparent", sBorder = sync ? "rgba(54,211,154,.4)" : "#2a323d";
  const tagOf = (a: string): [string, string] => TAG[a] || [a.slice(0, 2).toUpperCase(), "#9aa6b2"];

  return (
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateColumns: "minmax(0,1fr) 294px", gap: 14, padding: 16, minHeight: 0 }}>
      <div style={{ display: "grid", gridTemplateRows: "auto auto minmax(0,1fr)", gap: 14, minHeight: 0 }}>
        <div style={{ ...panel, padding: "14px 16px", ...row(16) }}>
          <div style={{ flex: "none" }}><div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "#6b7480" }}>编排台 · ORCHESTRATOR</div><div style={{ font: "600 16px 'Space Grotesk',sans-serif", color: "#e8ecf1", marginTop: 3, whiteSpace: "nowrap" }}>{running.length} 个 CLI agent 运行中</div></div>
          <canvas id="cx-orch" style={{ flex: 1, height: 38, display: "block", minWidth: 0 }} />
          <div style={{ flex: "none", textAlign: "right" }}><div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "#6b7480" }}>已装 AGENT</div><div style={{ font: "700 15px 'IBM Plex Mono',monospace", color: "#ff7a45", marginTop: 3 }}>{installed.length}</div></div>
          <span style={{ width: 1, height: 34, background: "#262d37", flex: "none" }} />
          <button onClick={toggleSync} style={{ flex: "none", ...row(8), border: `1px solid ${sBorder}`, background: sBg, cursor: "pointer", borderRadius: 9, padding: "8px 12px", color: sFg, font: "600 11.5px 'Space Grotesk',sans-serif" }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: sFg, boxShadow: `0 0 8px ${sFg}` }} />同步观察 {sync ? "开" : "关"}</button>
        </div>

        <div style={{ ...panel, padding: "12px 14px", display: "grid", gap: 9 }}>
          <div style={{ ...row(7), flexWrap: "wrap" }}>
            {installed.map((a) => { const [tg, fg] = tagOf(a.name); const on = sel === a.name; return (
              <button key={a.name} onClick={() => setSel(a.name)} style={{ ...row(6), border: `1px solid ${on ? fg : "#232a33"}`, background: on ? "rgba(255,122,69,.06)" : "#0b0e13", cursor: "pointer", borderRadius: 9, padding: "6px 11px" }}><span style={{ font: "700 10px 'IBM Plex Mono',monospace", color: fg }}>{tg}</span><span style={{ font: "600 12px 'Space Grotesk',sans-serif", color: on ? "#e8ecf1" : "#aab2bd" }}>{a.display}</span></button>
            ); })}
            {installed.length === 0 && <span style={mono(11)}>检测本机 agent 中…</span>}
          </div>
          <div style={{ ...row(9), background: "#0b0e13", border: "1px solid #232a33", borderRadius: 10, padding: "0 12px", height: 40 }}>
            <span style={{ font: "600 13px 'IBM Plex Mono',monospace", color: "#ff7a45" }}>$</span>
            <input value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") run(); }} placeholder={`给 ${sel || "agent"} 一个任务，回车真实发起…`} style={{ flex: 1, background: "transparent", border: 0, outline: "none", color: "#e8ecf1", font: "500 13px 'Space Grotesk',sans-serif" }} />
            <button onClick={run} disabled={busy} style={{ border: 0, cursor: busy ? "default" : "pointer", background: busy ? "#3a2a1d" : "#ff7a45", color: "#1a0f08", font: "600 11px 'Space Grotesk'", padding: "6px 14px", borderRadius: 7 }}>{busy ? "启动中" : "运行"}</button>
          </div>
          {err && <div style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "#ff8a8a" }}>{err}</div>}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: sessions.length ? "1fr 1fr" : "1fr", gap: 14, overflowY: "auto", minHeight: 0, alignContent: "start", paddingRight: 2 }}>
          {sessions.length === 0 && (
            <div style={{ ...panel, padding: "40px 20px", textAlign: "center", color: "#6b7480" }}><div style={{ font: "600 13px 'Space Grotesk',sans-serif", marginBottom: 6, color: "#aab2bd" }}>还没有运行中的 CLI agent</div><div style={{ font: "400 12px 'Space Grotesk',sans-serif" }}>上面选一个 agent、输入任务，回车即可在本系统内真实驱动它，输出会实时流到这里。</div></div>
          )}
          {sessions.map((s) => { const [tg, fg] = tagOf(s.agent); const live = s.status === "running"; const lamp = live ? "#36d39a" : "#6b7480"; return (
            <div key={s.id} style={{ background: "#0b0e13", border: `1px solid ${live ? "#26313a" : "#1a2029"}`, borderRadius: 14, display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", overflow: "hidden", minHeight: 220, boxShadow: live ? "0 0 0 1px rgba(255,122,69,.05),0 8px 30px rgba(0,0,0,.3)" : "none" }}>
              <div style={{ ...row(9), padding: "12px 13px 10px" }}>
                <span style={{ width: 30, height: 30, borderRadius: 8, background: "#11161d", border: "1px solid #1c222b", display: "grid", placeContent: "center", font: "700 11px 'IBM Plex Mono',monospace", color: fg, flex: "none" }}>{tg}</span>
                <div style={{ minWidth: 0, flex: 1 }}><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{s.name}</div><div style={{ ...mono(9.5), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>$ {s.prompt}</div></div>
                <span style={{ ...row(5), flex: "none", font: "600 9.5px 'IBM Plex Mono',monospace", color: lamp }}><b style={{ width: 7, height: 7, borderRadius: "50%", background: lamp, display: "inline-block", boxShadow: `0 0 7px ${lamp}`, animation: live ? "cxBreathe 2.5s ease infinite" : "none" }} />{live ? "运行中" : "已结束"} · {fmtAgo(s.started)}</span>
              </div>
              <pre data-term={s.id} style={{ margin: 0, padding: "11px 13px", background: "#070a0d", borderTop: "1px solid #1a2029", font: "500 11px/1.6 'IBM Plex Mono',monospace", color: "#9aa6b2", overflowY: "auto", minHeight: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{s.output || "启动中…"}</pre>
              <div style={{ display: "flex", gap: 7, padding: "10px 13px", borderTop: "1px solid #1a2029" }}>
                <span style={{ ...mono(9.5), alignSelf: "center" }}>pid {s.pid}</span>
                <span style={flex1} />
                {live && <button onClick={() => stop(s.id)} style={{ border: "1px solid #3a2626", background: "transparent", cursor: "pointer", borderRadius: 7, padding: "5px 11px", color: "#ff5d5d", font: "600 10.5px 'Space Grotesk'" }}>停止</button>}
              </div>
            </div>
          ); })}
        </div>
      </div>

      <div style={{ ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 16px 11px", borderBottom: "1px solid #161b22" }}><div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "#6b7480" }}>同步时间线</div><div style={{ font: "500 10px 'Space Grotesk',sans-serif", color: "#8b94a0", marginTop: 4 }}>跨 agent 事件 · 实时汇聚</div></div>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "14px 16px", display: "grid", gap: 13, alignContent: "start" }}>
          {sessions.length === 0 && <p style={{ margin: 0, ...mono(11) }}>发起 CLI agent 后，运行事件会汇聚到这里。</p>}
          {sessions.map((s) => { const [, tone] = tagOf(s.agent); return (
            <div key={s.id} style={{ display: "grid", gap: 4, borderLeft: `2px solid ${tone}`, paddingLeft: 11 }}><div style={row(7)}><span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: tone }}>{s.name}</span><span style={mono(9)}>{fmtAgo(s.started)}前</span></div><p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk',sans-serif", color: "#aab2bd" }}>{s.status === "running" ? "运行中" : "已结束"} · {s.prompt}</p></div>
          ); })}
        </div>
      </div>
    </div>
  );
}

// ============ INTEL ============
function Intel() {
  const PRI: Record<string, [string, string]> = { 高优先: ["#fff", "#ff5d5d"], 简报: ["#ff7a45", "rgba(255,122,69,.16)"], 观察: ["#aab2bd", "rgba(255,255,255,.06)"] };
  const I = (pri: string, source: string, time: string, title: string, take: string, rel: number) => ({ pri, source, time, title, take, rel });
  const intel = [
    I("高优先", "Hacker News", "08:12", "Anthropic 发布新一代本地代理协议", "与你的 MCP / 本地助理方向高度相关，建议今天读完并评估接入。", 96),
    I("高优先", "邮件", "07:58", "投资人回信：下周见面确认", "已读取邮件主题，非内容；建议尽快回复确认时间。", 91),
    I("简报", "GitHub Trending", "07:40", "local-first AI agent 框架一周 star 翻倍", "架构思路可借鉴到 LeoJarvis 的工具总线。", 81),
    I("简报", "雪球", "07:20", "你关注的持仓出现异动信号", "非紧急，已并入生活段简报。", 74),
    I("观察", "arXiv", "06:55", "长期记忆确认队列的可解释召回", "与你的待确认记忆机制呼应，留作参考。", 63),
    I("简报", "V2EX", "06:40", "本地优先工具讨论热帖", "社区在聊隐私与本机算力，可关注观点。", 60),
    I("观察", "少数派", "06:10", "Mac 效率工具年度盘点", "和设备管家方向相关，留作参考。", 52),
    I("简报", "高德", "昨天", "通勤路线施工提醒", "明早出行可能受影响，建议提前 15 分钟。", 55),
    I("观察", "小宇宙", "昨天", "AI 助理播客新一期", "话题与个人超级助理相关，闲时可听。", 48),
    I("观察", "Reddit", "昨天", "r/LocalLLaMA 本周高赞", "本地模型推理优化讨论，留作技术参考。", 45),
  ];
  const REPO = (name: string, lang: string, speed: number, stars: string, sig: string, summary: string) => {
    const SG: Record<string, [string, string]> = { 爆发: ["#fff", "#ff5d5d"], 加速: ["#fff", "rgba(255,122,69,.85)"], 升温: ["#ff7a45", "rgba(255,122,69,.16)"] };
    return { name, lang, speed, stars, sig, summary, sigFg: SG[sig][0], sigBg: SG[sig][1] };
  };
  const repos = [REPO("local-agent/core", "Rust", 142, "8.4k", "爆发", "本地优先代理运行时，内置工具闸门与审计。"), REPO("mcp-tools/gateway", "TypeScript", 88, "3.1k", "加速", "统一 MCP 网关，聚合搜索 / GitHub / 地图工具。"), REPO("agent-os/runtime", "Go", 64, "2.2k", "加速", "多智能体编排运行时，支持并行子任务。"), REPO("whisper-live", "Python", 31, "12k", "升温", "实时语音转写，可用于语音指令输入。"), REPO("memory-vec", "Rust", 22, "1.1k", "升温", "可解释向量记忆库，带召回审计。")];
  const [filter, setFilter] = useState("全部");
  const filters = ["全部", "高优先", "简报", "观察"];
  const sources = [{ name: "RSS · 12 源", count: "活跃", dot: "#36d39a" }, { name: "网页变化监控", count: "6", dot: "#36d39a" }, { name: "GitHub 雷达", count: "10 query", dot: "#36d39a" }, { name: "邮件 IMAP", count: "已连", dot: "#36d39a" }, { name: "ICS 日历", count: "待配置", dot: "#6b7480" }];
  const targets = ["AI 助理", "MCP", "个人助理", "local-first", "agent", "本地算力"];
  const shown = filter === "全部" ? intel : intel.filter((it) => it.pri === filter);
  const headBar = { ...row(8), padding: "15px 16px 12px", borderBottom: "1px solid #161b22" };
  const col = { ...panel, padding: 0, display: "grid", gridTemplateRows: "auto minmax(0,1fr)", minHeight: 0, overflow: "hidden" } as CSSProperties;
  return (
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateRows: "auto minmax(0,1fr)", gap: 14, padding: 16, minHeight: 0 }}>
      <div style={{ ...panel, padding: "14px 16px", ...row(18), flexWrap: "wrap" }}>
        <div style={{ flex: "none", display: "flex", alignItems: "baseline", gap: 8 }}><b style={{ font: "700 26px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>28</b><span style={mono(11)}>今日信号</span></div>
        <div style={{ flex: "none", display: "flex", gap: 8, font: "600 10.5px 'IBM Plex Mono',monospace" }}>
          <span style={{ ...row(5), background: "rgba(255,93,93,.12)", color: "#ff8a8a", borderRadius: 7, padding: "5px 9px" }}>高优先 3</span>
          <span style={{ ...row(5), background: "rgba(255,122,69,.12)", color: "#ff9d6e", borderRadius: 7, padding: "5px 9px" }}>简报 12</span>
          <span style={{ ...row(5), background: "rgba(255,255,255,.05)", color: "#aab2bd", borderRadius: 7, padding: "5px 9px" }}>观察 13</span>
        </div>
        <span style={{ flex: 1, minWidth: 20 }} />
        <div style={{ flex: "none", display: "flex", gap: 5, background: "#0b0e13", border: "1px solid #1c222b", borderRadius: 9, padding: 4 }}>
          {filters.map((f) => (<button key={f} onClick={() => setFilter(f)} style={{ border: 0, cursor: "pointer", font: "600 11px 'Space Grotesk',sans-serif", padding: "6px 13px", borderRadius: 6, color: filter === f ? "#1a0f08" : "#aab2bd", background: filter === f ? "#ff7a45" : "transparent", transition: "all .16s", whiteSpace: "nowrap" }}>{f}</button>))}
        </div>
        <span style={{ flex: "none", ...mono(10) }}>已读 12 · 已忽略 41</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.45fr) minmax(0,1fr) 286px", gap: 14, minHeight: 0 }}>
        <div style={col}>
          <div style={headBar}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "#6b7480" }}>信号流 · 已筛选评分</span><span style={flex1} /><span style={mono(10, "#aab2bd")}>{shown.length} 条</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "8px 16px 16px" }}>
            {shown.map((it, i) => (
              <button key={i} className="cx-intel" style={{ textAlign: "left", width: "100%", border: 0, cursor: "pointer", background: "transparent", padding: "13px 0", borderBottom: "1px solid #161b22", display: "grid", gap: 6 }}>
                <div style={row(8)}><span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: PRI[it.pri][0], background: PRI[it.pri][1], borderRadius: 999, padding: "2px 8px" }}>{it.pri}</span><span style={mono(10)}>{it.source} · {it.time}</span><span style={flex1} /><span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: "#ff7a45" }}>相关 {it.rel}</span></div>
                <b style={{ font: "600 14px/1.4 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{it.title}</b>
                <p style={{ margin: 0, font: "400 12px/1.55 'Space Grotesk',sans-serif", color: "#8b94a0" }}>{it.take}</p>
              </button>
            ))}
          </div>
        </div>
        <div style={col}>
          <div style={headBar}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "#6b7480" }}>GITHUB 雷达</span><span style={flex1} /><span style={mono(10, "#aab2bd")}>高增速</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "12px 16px 16px", display: "grid", gap: 11, alignContent: "start" }}>
            {repos.map((rp) => (
              <div key={rp.name} style={{ border: "1px solid #1a2029", background: "#0b0e13", borderRadius: 11, padding: 12, display: "grid", gap: 6 }}><div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}><b style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{rp.name}</b><span style={{ font: "600 9px 'IBM Plex Mono',monospace", color: rp.sigFg, background: rp.sigBg, borderRadius: 999, padding: "2px 8px" }}>{rp.sig}</span></div><p style={{ margin: 0, font: "400 11.5px/1.5 'Space Grotesk',sans-serif", color: "#8b94a0" }}>{rp.summary}</p><div style={{ display: "flex", gap: 12, font: "500 10px 'IBM Plex Mono',monospace", color: "#6b7480" }}><span>{rp.lang}</span><span>★ {rp.stars}</span><span style={{ color: "#36d39a" }}>▲ {rp.speed}/天</span></div></div>
            ))}
          </div>
        </div>
        <div style={col}>
          <div style={headBar}><span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "#6b7480" }}>来源 & 关注项</span></div>
          <div style={{ overflowY: "auto", minHeight: 0, padding: "14px 16px" }}>
            <div style={{ position: "relative", width: "100%", height: 120, display: "grid", placeContent: "center", marginBottom: 14 }}>
              <svg width="120" height="120" viewBox="0 0 120 120" style={{ opacity: 0.5 }}><circle cx="60" cy="60" r="52" fill="none" stroke="#1c222b" /><circle cx="60" cy="60" r="34" fill="none" stroke="#1c222b" /><circle cx="60" cy="60" r="16" fill="none" stroke="#1c222b" /><line x1="60" y1="8" x2="60" y2="112" stroke="#1c222b" /><line x1="8" y1="60" x2="112" y2="60" stroke="#1c222b" /></svg>
              <div style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "conic-gradient(from 0deg,rgba(255,122,69,.35),transparent 60%)", WebkitMaskImage: "radial-gradient(circle,transparent 0,#000 1px)", maskImage: "radial-gradient(circle,transparent 0,#000 1px)", animation: "cxSweep 4s linear infinite" }} />
              <span style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", font: "600 9px 'IBM Plex Mono'", color: "#6b7480", letterSpacing: ".1em" }}>SCAN</span>
            </div>
            <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".12em", color: "#6b7480", marginBottom: 9 }}>已接入来源</div>
            <div style={{ display: "grid", gap: 7, marginBottom: 16 }}>
              {sources.map((sc) => (<div key={sc.name} style={row(9)}><span style={{ width: 6, height: 6, borderRadius: "50%", background: sc.dot, flex: "none" }} /><span style={{ font: "500 12px 'Space Grotesk',sans-serif", color: "#aab2bd", flex: 1 }}>{sc.name}</span><span style={mono(10)}>{sc.count}</span></div>))}
            </div>
            <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".12em", color: "#6b7480", marginBottom: 9 }}>关注项</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {targets.map((tg) => (<span key={tg} style={{ font: "500 11px 'Space Grotesk',sans-serif", color: "#aab2bd", background: "#0b0e13", border: "1px solid #1c222b", borderRadius: 999, padding: "5px 10px" }}>{tg}</span>))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ SETTINGS ============
function Settings({ tab, setTab, scan, toggleScan }: { tab: SetTab; setTab: (t: SetTab) => void; scan: boolean; toggleScan: () => void }) {
  const tabMeta: [SetTab, string, string][] = [["models", "模型路由", "MODELS"], ["sources", "情报源", "SOURCES"], ["guard", "服务与阈值", "GUARD"], ["mcp", "MCP 网关", "MCP"], ["devices", "SSH 设备", "DEVICES"], ["appearance", "外观与动效", "APPEARANCE"]];
  const ST: Record<string, [string, string]> = { 在线: ["#36d39a", "rgba(54,211,154,.12)"], 已配置: ["#ff7a45", "rgba(255,122,69,.14)"], 待授权: ["#ffb454", "rgba(255,180,84,.14)"] };
  const sw = (on: boolean) => ({ swBg: on ? "#ff7a45" : "#1c222b", swBorder: on ? "#ff7a45" : "#2a323d", swKnob: on ? "#0a0c10" : "#6b7480", swX: on ? 18 : 2 });
  const Switch = ({ on }: { on: boolean }) => { const s = sw(on); return <span style={{ width: 36, height: 21, borderRadius: 999, background: s.swBg, position: "relative", flex: "none", border: `1px solid ${s.swBorder}` }}><i style={{ position: "absolute", top: 2, left: s.swX, width: 15, height: 15, borderRadius: "50%", background: s.swKnob, transition: "left .18s" }} /></span>; };
  const h2 = (t: string, d: string) => (<div style={{ marginBottom: 22 }}><h2 style={{ margin: 0, font: "600 20px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{t}</h2><p style={{ margin: "6px 0 0", font: "400 13px/1.6 'Space Grotesk',sans-serif", color: "#8b94a0", maxWidth: 560 }}>{d}</p></div>);
  const routes = [{ role: "中枢 Agent", key: "routing.agent", endpoint: "https://api.anthropic.com/v1", model: "claude-sonnet-4.5", status: "在线" }, { role: "判断引擎", key: "routing.judge", endpoint: "http://127.0.0.1:11434/v1", model: "qwen2.5:14b (本地)", status: "在线" }, { role: "嵌入", key: "routing.embed", endpoint: "http://127.0.0.1:11434", model: "nomic-embed-text", status: "在线" }];
  const sourceRows = [{ name: "Hacker News RSS", detail: "https://news.ycombinator.com/rss", kind: "RSS", dot: "#36d39a", on: true }, { name: "GitHub 雷达", detail: "AI agent · MCP · local-first", kind: "雷达", dot: "#36d39a", on: true }, { name: "雪球关注", detail: "持仓与自选监控", kind: "API", dot: "#36d39a", on: true }, { name: "网页变化 · 官网", detail: "anthropic.com/news", kind: "网页", dot: "#36d39a", on: true }, { name: "ICS 日历", detail: "未配置 URL", kind: "日历", dot: "#6b7480", on: false }];
  const gSvc = [["LeoJarvis", 8787, "#36d39a", "开"], ["Ollama", 11434, "#36d39a", "关"], ["LeoNote", 3000, "#36d39a", "开"], ["LeoAPI", 8000, "#36d39a", "开"], ["LeoMoney", 5001, "#ff5d5d", "开"], ["CloudCLI", 7070, "#36d39a", "关"]] as [string, number, string, string][];
  const thresholds = [{ label: "SSD 告警阈值", val: "88%", pct: "88%" }, { label: "CPU 负载告警", val: "120%", pct: "75%" }, { label: "RAM 告警阈值", val: "90%", pct: "90%" }, { label: "系统巡检频率", val: "5 分钟", pct: "40%" }];
  const mcpRows = [{ tag: "TV", name: "Tavily Search", scope: "网页搜索 / Extract", key: "tvly-••••••••••••3f2a", status: "已配置", on: true }, { tag: "GH", name: "GitHub MCP", scope: "仓库 / release / topic", key: "ghp_••••••••••••a91c", status: "在线", on: true }, { tag: "AM", name: "高德地图", scope: "地理 / 路线 / POI", key: "未设置", status: "待授权", on: false }];
  const devices = [{ name: "本机 Mac", host: "127.0.0.1 · arm64", lamp: "#36d39a", statusText: "在线", meta: "健康 86 · 5/6 服务" }, { name: "工作站 · studio", host: "192.168.1.20 · ssh", lamp: "#36d39a", statusText: "已连接", meta: "CPU 12% · 只读" }, { name: "云主机 · sg-1", host: "10.0.4.7 · tunnel", lamp: "#ffb454", statusText: "待探测", meta: "上次 2 小时前" }];
  const slider = (val: string, pct: string, label: string) => (
    <div><div style={{ ...row(10), marginBottom: 9 }}><span style={{ font: "600 12px 'Space Grotesk'", color: "#e8ecf1" }}>{label}</span><span style={flex1} /><span style={{ font: "600 12px 'IBM Plex Mono'", color: "#ff7a45" }}>{val}</span></div><div style={{ height: 5, borderRadius: 5, background: "#1c222b", position: "relative" }}><i style={{ display: "block", height: "100%", width: pct, background: "#ff7a45", borderRadius: 5 }} /><span style={{ position: "absolute", top: "50%", left: pct, transform: "translate(-50%,-50%)", width: 13, height: 13, borderRadius: "50%", background: "#e8ecf1", boxShadow: "0 0 0 3px rgba(255,122,69,.25)" }} /></div></div>
  );
  const dash: CSSProperties = { border: "1px dashed #2a323d", background: "transparent", cursor: "pointer", borderRadius: 13, padding: 13, color: "#6b7480", font: "600 12px 'Space Grotesk'" };
  return (
    <div className="cx-page" style={{ height: "100%", display: "grid", gridTemplateColumns: "208px minmax(0,1fr)", gap: 14, padding: 16, minHeight: 0 }}>
      <div style={{ ...panel, padding: 12, display: "grid", gap: 3, alignContent: "start" }}>
        <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "#6b7480", padding: "8px 10px 10px" }}>设置台 · CONSOLE</div>
        {tabMeta.map(([id, label, en]) => (
          <button key={id} onClick={() => setTab(id)} style={{ textAlign: "left", border: 0, cursor: "pointer", ...row(10), padding: "10px 11px", borderRadius: 10, background: tab === id ? "#11161d" : "transparent", transition: "all .16s" }}><span style={{ width: 3, height: 15, borderRadius: 3, background: tab === id ? "#ff7a45" : "transparent", flex: "none" }} /><div style={{ minWidth: 0 }}><div style={{ font: "600 12.5px 'Space Grotesk',sans-serif", color: tab === id ? "#e8ecf1" : "#8b94a0", whiteSpace: "nowrap" }}>{label}</div><div style={{ font: "500 8.5px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "#5a626d", whiteSpace: "nowrap" }}>{en}</div></div></button>
        ))}
      </div>

      <div style={{ ...panel, overflowY: "auto", minHeight: 0, padding: "24px 26px" }}>
        {tab === "models" && (<>
          {h2("模型路由", "端点无关 · JSON 动作协议。任意 OpenAI 兼容接口都能驱动中枢、判断引擎与嵌入。")}
          <div style={{ display: "grid", gap: 12, maxWidth: 680 }}>
            {routes.map((r) => (<div key={r.key} style={{ ...sub, padding: 16, display: "grid", gridTemplateColumns: "120px 1fr auto", gap: 14, alignItems: "center" }}><div><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{r.role}</div><div style={{ ...mono(9.5), marginTop: 2 }}>{r.key}</div></div><div style={{ minWidth: 0 }}><div style={{ font: "500 12.5px 'IBM Plex Mono',monospace", color: "#aab2bd", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.endpoint}</div><div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "#ff7a45", marginTop: 3 }}>{r.model}</div></div><span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: ST[r.status][0], background: ST[r.status][1], borderRadius: 999, padding: "5px 10px", whiteSpace: "nowrap" }}>{r.status}</span></div>))}
            <button className="cx-dash" style={dash}>+ 新增路由</button>
          </div>
          <div style={{ marginTop: 22, maxWidth: 680, ...sub, padding: 16 }}><div style={{ ...row(10), marginBottom: 12 }}><span style={{ font: "600 12px 'Space Grotesk'", color: "#e8ecf1" }}>采样温度</span><span style={flex1} /><span style={{ font: "600 12px 'IBM Plex Mono'", color: "#ff7a45" }}>0.35</span></div><div style={{ height: 5, borderRadius: 5, background: "#1c222b", position: "relative" }}><i style={{ display: "block", height: "100%", width: "35%", background: "#ff7a45", borderRadius: 5 }} /><span style={{ position: "absolute", top: "50%", left: "35%", transform: "translate(-50%,-50%)", width: 14, height: 14, borderRadius: "50%", background: "#e8ecf1", boxShadow: "0 0 0 3px rgba(255,122,69,.25)" }} /></div></div>
        </>)}

        {tab === "sources" && (<>
          {h2("情报源", "RSS / 网页变化 / GitHub 雷达 / 邮件 / 日历。新条目进入事件流并交由判断器分诊。")}
          <div style={{ display: "grid", gap: 10, maxWidth: 680 }}>
            {sourceRows.map((s) => (<div key={s.name} style={{ ...sub, borderRadius: 12, padding: "14px 16px", ...row(13) }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: s.dot, flex: "none", boxShadow: s.on ? "0 0 7px rgba(54,211,154,.6)" : "none" }} /><div style={{ flex: 1, minWidth: 0 }}><div style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "#e8ecf1" }}>{s.name}</div><div style={{ ...mono(10), marginTop: 2 }}>{s.detail}</div></div><span style={mono(10)}>{s.kind}</span><Switch on={s.on} /></div>))}
          </div>
        </>)}

        {tab === "guard" && (<>
          {h2("服务与阈值", "后台巡检频率与告警阈值。低风险只读自动执行，重启等高风险操作需确认。")}
          <div style={{ display: "grid", gap: 18, maxWidth: 680 }}>
            <div style={{ display: "grid", gap: 10 }}>
              {gSvc.map(([name, port, dot, auto]) => (<div key={name} style={{ ...sub, borderRadius: 12, padding: "13px 16px", ...row(13) }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: dot, flex: "none" }} /><span style={{ font: "600 13px 'Space Grotesk',sans-serif", color: "#e8ecf1", flex: 1 }}>{name}</span><span style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "#6b7480" }}>127.0.0.1:{port}</span><span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: auto === "开" ? "#36d39a" : "#6b7480" }}>自动重启 {auto}</span></div>))}
            </div>
            <div style={{ display: "grid", gap: 16, ...sub, padding: 18 }}>{thresholds.map((th) => slider(th.val, th.pct, th.label))}</div>
          </div>
        </>)}

        {tab === "mcp" && (<>
          {h2("MCP 网关", "密钥优先从环境变量读取，也可本机保存到 data/user_settings.json（不进 Git）。")}
          <div style={{ display: "grid", gap: 12, maxWidth: 680 }}>
            {mcpRows.map((m) => (<div key={m.name} style={{ ...sub, padding: 16, display: "grid", gap: 12 }}><div style={row(11)}><span style={{ width: 30, height: 30, borderRadius: 8, background: "#11161d", border: "1px solid #1c222b", display: "grid", placeContent: "center", font: "700 11px 'IBM Plex Mono'", color: "#ff7a45", flex: "none" }}>{m.tag}</span><div style={{ flex: 1 }}><div style={{ font: "600 13px 'Space Grotesk'", color: "#e8ecf1" }}>{m.name}</div><div style={{ font: "500 10px 'IBM Plex Mono'", color: "#6b7480" }}>{m.scope}</div></div><Switch on={m.on} /></div><div style={{ ...row(10), background: "#070a0d", border: "1px solid #1a2029", borderRadius: 9, padding: "9px 12px" }}><span style={{ font: "500 10px 'IBM Plex Mono'", color: "#6b7480" }}>KEY</span><code style={{ flex: 1, font: "500 11.5px 'IBM Plex Mono'", color: "#aab2bd", letterSpacing: ".06em" }}>{m.key}</code><span style={{ font: "600 9.5px 'IBM Plex Mono'", color: ST[m.status][0], background: ST[m.status][1], borderRadius: 999, padding: "3px 9px" }}>{m.status}</span></div></div>))}
          </div>
        </>)}

        {tab === "devices" && (<>
          {h2("SSH 设备", "只用 SSH 公钥（不存密码）。只读采集健康摘要，不读取文件内容。")}
          <div style={{ display: "grid", gap: 10, maxWidth: 680 }}>
            {devices.map((d) => (<div key={d.name} style={{ ...sub, padding: "15px 16px", ...row(14) }}><span style={{ width: 34, height: 34, borderRadius: 9, background: "#11161d", border: "1px solid #1c222b", display: "grid", placeContent: "center", flex: "none", color: d.lamp }}><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg></span><div style={{ flex: 1, minWidth: 0 }}><div style={{ font: "600 13px 'Space Grotesk'", color: "#e8ecf1" }}>{d.name}</div><div style={{ font: "500 10px 'IBM Plex Mono'", color: "#6b7480" }}>{d.host}</div></div><div style={{ textAlign: "right" }}><div style={{ font: "600 11px 'IBM Plex Mono'", color: d.lamp }}>{d.statusText}</div><div style={{ font: "500 9.5px 'IBM Plex Mono'", color: "#6b7480", marginTop: 2 }}>{d.meta}</div></div></div>))}
            <button className="cx-dash" style={dash}>+ 添加设备</button>
          </div>
        </>)}

        {tab === "appearance" && (<>
          {h2("外观与动效", "指挥台主题。冷光强调色、动效强度与环境氛围可调。")}
          <div style={{ display: "grid", gap: 14, maxWidth: 680 }}>
            <div style={{ ...sub, padding: 16 }}><div style={{ font: "600 12px 'Space Grotesk'", color: "#e8ecf1", marginBottom: 12 }}>强调色</div><div style={{ display: "flex", gap: 10 }}><span style={{ width: 30, height: 30, borderRadius: 9, background: "#ff7a45", boxShadow: "0 0 0 2px #0b0e13,0 0 0 4px #ff7a45" }} /><span style={{ width: 30, height: 30, borderRadius: 9, background: "#36d39a" }} /><span style={{ width: 30, height: 30, borderRadius: 9, background: "#4da3ff" }} /><span style={{ width: 30, height: 30, borderRadius: 9, background: "#b69cff" }} /></div></div>
            <div style={{ ...sub, padding: 16, ...row(14) }}><div style={{ flex: 1 }}><div style={{ font: "600 12px 'Space Grotesk'", color: "#e8ecf1" }}>扫描线氛围</div><div style={{ font: "400 11px 'Space Grotesk'", color: "#6b7480", marginTop: 2 }}>顶部冷光扫描叠加</div></div><button onClick={toggleScan} style={{ width: 40, height: 23, border: `1px solid ${scan ? "#ff7a45" : "#2a323d"}`, borderRadius: 999, background: scan ? "#ff7a45" : "#1c222b", position: "relative", cursor: "pointer", flex: "none" }}><i style={{ position: "absolute", top: 2, left: scan ? 18 : 2, width: 16, height: 16, borderRadius: "50%", background: scan ? "#0a0c10" : "#6b7480", transition: "left .18s" }} /></button></div>
            <div style={{ ...sub, padding: 16 }}><div style={{ font: "600 12px 'Space Grotesk'", color: "#e8ecf1", marginBottom: 12 }}>动效强度</div><div style={{ display: "flex", gap: 5, background: "#070a0d", border: "1px solid #1c222b", borderRadius: 9, padding: 4 }}>{["克制", "适中", "酷炫"].map((m, i) => (<span key={m} style={{ flex: 1, textAlign: "center", font: "600 11.5px 'Space Grotesk'", padding: 7, borderRadius: 6, background: i === 2 ? "#ff7a45" : "transparent", color: i === 2 ? "#1a0f08" : "#6b7480", cursor: "pointer" }}>{m}</span>))}</div></div>
          </div>
        </>)}
      </div>
    </div>
  );
}
