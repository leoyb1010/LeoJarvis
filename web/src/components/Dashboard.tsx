import { useEffect, useMemo, useState } from "react";
import {
  siClaude,
  siClaudecode,
  siCursor,
  siFastapi,
  siGooglegemini,
  siJavascript,
  siNextdotjs,
  siNodedotjs,
  siOllama,
  siPython,
  siReact,
  siTypescript,
  siVite,
  type SimpleIcon,
} from "simple-icons";
import {
  closeTerminalSession,
  connectRemoteLeoJarvis,
  createTerminalSession,
  getCockpitOverview,
  getRemoteCockpit,
  getTerminalSessions,
  listRemoteLeoJarvis,
  readTerminalSession,
  upgradeAiTool,
  writeTerminalSession,
  type AiToolStatus,
  type BriefingItem,
  type CockpitGithubCard,
  type CockpitOverview,
  type LocalNotificationApp,
  type RemoteLeoJarvisConnection,
  type ServiceRow,
  type TerminalSession,
} from "../api";
import { PageSkeleton } from "./Skeleton";
import { Modal } from "./Modal";
import { BriefingSignalDetail, GithubRepoDetail } from "./IntelligenceDetail";

type MetricSample = {
  ts: number;
  health: number;
  disk: number;
  load: number;
  loadPct: number;
  ram: number;
  service: number;
  intel: number;
  memory: number;
};

function percent(value: number, total: number) {
  if (!total) return 0;
  return Math.round((value / total) * 100);
}

function sampleFrom(data: CockpitOverview): MetricSample {
  return {
    ts: data.generated_at,
    health: data.health.score,
    disk: Number(data.health.system.disk_pct || 0),
    load: Number(data.health.system.load || 0),
    loadPct: Number(data.health.system.load_pct || 0),
    ram: Number(data.health.system.memory_used_pct || 0),
    service: percent(data.health.services_online, data.health.services_total || 1),
    intel: data.intelligence.events,
    memory: data.memory.pending + data.memory.later,
  };
}

function readStoredSamples(): MetricSample[] {
  try {
    const raw = localStorage.getItem("cortex-dashboard-samples");
    const rows = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(rows)) return [];
    return rows.filter((r) => r && typeof r.ts === "number").slice(-40);
  } catch {
    return [];
  }
}

function storeSamples(rows: MetricSample[]) {
  try {
    localStorage.setItem("cortex-dashboard-samples", JSON.stringify(rows.slice(-40)));
  } catch {
    /* localStorage optional */
  }
}

function fmtTime(ts?: number, ms = true) {
  if (!ts) return "—";
  return new Date(ms ? ts : ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function formatRepoSpeed(speed?: number | null) {
  if (speed == null || !Number.isFinite(speed)) return "观察";
  const value = Math.abs(speed) >= 10 ? speed.toFixed(0) : speed.toFixed(2);
  return `${speed > 0 ? "+" : ""}${value}/天`;
}

function evidenceList(item: BriefingItem) {
  const rows = (item.reasons || []).filter(Boolean);
  if (rows.length) return rows.slice(0, 4);
  if (item.why_important) return [item.why_important];
  return ["已通过情报评分进入驾驶舱。"];
}

function cleanTerminalOutput(value: string) {
  return value
    .replace(/\x1B\][^\x07]*(?:\x07|\x1B\\)/g, "")
    .replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, "")
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
}

// 微型趋势线：保留克制，但加入低噪网格底，避免六格像生硬折线。
function Trend({ values, tone = "accent" }: { values: number[]; tone?: string }) {
  const w = 200;
  const h = 40;
  const pts = values.length >= 2 ? values : [values[0] || 0, values[0] || 0];
  const hi = Math.max(1, ...pts);
  const lo = Math.min(...pts);
  const span = Math.max(1, hi - lo);
  const sx = (i: number) => (i / Math.max(1, pts.length - 1)) * w;
  const sy = (v: number) => h - 3 - ((v - lo) / span) * (h - 6);
  const line = pts.map((v, i) => `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(" ");
  return (
    <svg className={`dash-trend tone-${tone}`} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={line} />
    </svg>
  );
}

type Stat = {
  label: string;
  value: string;
  unit?: string;
  hint: string;
  tone: "ok" | "warn" | "bad" | "neutral";
  values: number[];
};

function StatBlock({ stat, onClick }: { stat: Stat; onClick?: () => void }) {
  return (
    <button className={`dash-stat dash-${stat.tone} ${onClick ? "clickable" : ""}`} onClick={onClick} type="button">
      <div className="dash-stat-row">
        <span className="dash-stat-label">{stat.label}</span>
        <span className="dash-stat-dot" />
      </div>
      <div className="dash-stat-value">
        {stat.value}
        {stat.unit ? <i>{stat.unit}</i> : null}
      </div>
      <Trend values={stat.values} tone={stat.tone === "neutral" ? "accent" : stat.tone} />
      <div className="dash-stat-hint">{stat.hint}</div>
    </button>
  );
}

function SectionTitle({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="dash-section">
      <h2>{title}</h2>
      {meta ? <span>{meta}</span> : null}
    </div>
  );
}

function AppIcon({ app, size = 36 }: { app: LocalNotificationApp; size?: number }) {
  if (app.icon) {
    return <img className="dash-app-icon" src={app.icon} alt={app.name} width={size} height={size} />;
  }
  return <span className="dash-app-icon fallback" style={{ width: size, height: size }}>{app.name.slice(0, 1)}</span>;
}

function statusTone(status: string): "ok" | "warn" | "bad" | "neutral" {
  if (status === "有新通知" || status === "已读取邮件") return "ok";
  if (status === "无新通知") return "neutral";
  if (status === "未授权" || status === "未配置") return "warn";
  return "neutral";
}

function compactName(name: string) {
  return name
    .replace(/_/g, "-")
    .replace(/\bcli\b/i, "CLI")
    .replace(/\bcode\b/i, "Code")
    .replace(/\bapp\b/i, "App")
    .trim();
}

function initials(name: string, max = 3) {
  const cleaned = compactName(name);
  const parts = cleaned.split(/[^A-Za-z0-9]+/).filter(Boolean);
  if (!parts.length) return "S";
  if (parts.length === 1) {
    const single = parts[0];
    if (/^\d+$/.test(single)) return single.slice(0, max);
    return single.slice(0, max).toUpperCase();
  }
  return parts.slice(0, max).map((p) => p[0]).join("").toUpperCase();
}

type VisualSpec = {
  label: string;
  name: string;
  tone: string;
  icon?: SimpleIcon;
  image?: string;
};

function RuntimeIcon({ visual }: { visual: VisualSpec }) {
  if (visual.image) {
    return <img src={visual.image} alt="" />;
  }
  if (visual.icon) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d={visual.icon.path} fill={`#${visual.icon.hex}`} />
      </svg>
    );
  }
  return <span>{visual.label}</span>;
}

function serviceVisual(service: ServiceRow) {
  const key = `${service.name} ${service.desc || ""} ${service.process || ""} ${service.command || ""} ${service.cwd || ""}`.toLowerCase();
  if (key.includes("leojarvis")) return { label: "LJ", name: "LeoJarvis", tone: "brand", image: "/brand-mark.png" };
  if (key.includes("ollama")) return { label: "OL", name: "Ollama", tone: "agent", icon: siOllama };
  if (key.includes("leoapi")) return { label: "API", name: "LeoAPI", tone: "code" };
  if (key.includes("leonote")) return { label: "LN", name: "LeoNote", tone: "note", image: "/leonote-icon.png" };
  if (key.includes("leomoney")) return { label: "LM", name: "LeoMoney", tone: "money" };
  if (key.includes("cloudcli")) return { label: "CLI", name: "CloudCLI", tone: "code" };
  if (key.includes("claude-code-ui")) return { label: "CC", name: "Claude UI", tone: "agent", icon: siClaudecode };
  if (key.includes("openclaw")) return { label: "OC", name: "OpenClaw", tone: "agent" };
  if (key.includes("hermes-agent")) return { label: "HA", name: "Hermes", tone: "agent" };
  if (key.includes("agent-studio")) return { label: "AS", name: "Agent Studio", tone: "agent" };
  if (key.includes("growth-system")) return { label: "GS", name: "Growth", tone: "data" };
  if (key.includes("chinabridge")) return { label: "CB", name: "ChinaBridge", tone: "data" };
  if (key.includes("web-preview") || key.includes("vite")) return { label: "WEB", name: "Web Preview", tone: "web", icon: siVite };
  if (key.includes("next-app") || key.includes("next-server")) return { label: "NX", name: "Next App", tone: "web", icon: siNextdotjs };
  if (key.includes("fastapi")) return { label: "FA", name: compactName(service.name), tone: "code", icon: siFastapi };
  if (key.includes("python") || key.includes("uvicorn")) return { label: "PY", name: compactName(service.name), tone: "code", icon: siPython };
  if (key.includes("typescript")) return { label: "TS", name: compactName(service.name), tone: "code", icon: siTypescript };
  if (key.includes("react")) return { label: "RE", name: compactName(service.name), tone: "web", icon: siReact };
  if (key.includes("node")) return { label: "JS", name: compactName(service.name), tone: "web", icon: siNodedotjs };
  return { label: initials(service.name), name: compactName(service.name), tone: "neutral" };
}

function toolVisual(tool: AiToolStatus) {
  const key = `${tool.id} ${tool.name}`.toLowerCase();
  if (key.includes("claude_code")) return { label: "CC", name: "Claude Code", tone: "agent", icon: siClaudecode };
  if (key.includes("claude")) return { label: "CL", name: "Claude", tone: "agent", icon: siClaude };
  if (key.includes("codex")) return { label: "CX", name: "Codex CLI", tone: "brand", image: "/codex-icon.png" };
  if (key.includes("gemini")) return { label: "G", name: "Gemini CLI", tone: "agent", icon: siGooglegemini };
  if (key.includes("cursor")) return { label: "CR", name: "Cursor CLI", tone: "code", icon: siCursor };
  if (key.includes("opencode")) return { label: "OC", name: "OpenCode", tone: "code" };
  if (key.includes("aider")) return { label: "AI", name: "Aider", tone: "agent" };
  if (key.includes("crush")) return { label: "CH", name: "Crush", tone: "agent" };
  if (key.includes("grok")) return { label: "GB", name: "Grok Build", tone: "agent" };
  if (key.includes("ollama")) return { label: "OL", name: "Ollama", tone: "agent", icon: siOllama };
  if (key.includes("node")) return { label: "JS", name: compactName(tool.name), tone: "web", icon: siJavascript };
  return { label: initials(tool.name), name: compactName(tool.name), tone: "neutral" };
}

export function Dashboard() {
  const [data, setData] = useState<CockpitOverview | null>(null);
  const [samples, setSamples] = useState<MetricSample[]>(() => readStoredSamples());
  const [error, setError] = useState("");
  const [activeApp, setActiveApp] = useState<LocalNotificationApp | null>(null);
  const [activeSignal, setActiveSignal] = useState<BriefingItem | null>(null);
  const [activeRepo, setActiveRepo] = useState<CockpitGithubCard | null>(null);
  const [activeTool, setActiveTool] = useState<AiToolStatus | null>(null);
  const [activeService, setActiveService] = useState<ServiceRow | null>(null);
  const [showHealthDetail, setShowHealthDetail] = useState(false);
  const [upgradingTool, setUpgradingTool] = useState("");
  const [upgradeResult, setUpgradeResult] = useState("");
  const [remotes, setRemotes] = useState<RemoteLeoJarvisConnection[]>([]);
  const [activeDevice, setActiveDevice] = useState("local");
  const [deviceError, setDeviceError] = useState("");
  const [terminalSession, setTerminalSession] = useState<TerminalSession | null>(null);
  const [terminalDevice, setTerminalDevice] = useState("local");
  const [terminalOutput, setTerminalOutput] = useState("");
  const [terminalInput, setTerminalInput] = useState("");
  const [terminalBusy, setTerminalBusy] = useState(false);
  const [terminalError, setTerminalError] = useState("");
  // 后台仍在运行的 CLI 会话（关闭弹层后不杀进程），用于在工具卡上标记“后台运行中”。
  const [bgSessions, setBgSessions] = useState<TerminalSession[]>([]);

  useEffect(() => {
    let alive = true;
    // 远端连接状态会随隧道建立从“未连接”变“已连接”，必须随轮询刷新，
    // 否则首屏拿到的离线状态会一直留在下拉里，远端永远显示离线。
    const refreshRemotes = () =>
      listRemoteLeoJarvis().then((rows) => { if (alive) setRemotes(rows); }).catch(() => {});
    const load = () => {
      setDeviceError("");
      const dataPromise = activeDevice === "local"
        ? getCockpitOverview()
        : getRemoteCockpit(activeDevice).then((res) => {
            if (!res.ok || !res.data) throw new Error(res.error || "远程 LeoJarvis 未连接");
            return res.data;
          });
      dataPromise
        .then((res) => {
          if (!alive) return;
          setError("");
          setDeviceError("");
          setData(res);
          setSamples((prev) => {
            const key = activeDevice === "local" ? "cortex-dashboard-samples" : `cortex-dashboard-samples-${activeDevice}`;
            const next = [...prev.filter((row) => row.ts !== res.generated_at), sampleFrom(res)].slice(-40);
            try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* optional */ }
            return next;
          });
        })
        .catch((err) => { if (alive) { setError(String(err)); setDeviceError(String(err)); } });
    };
    refreshRemotes();
    load();
    const t = window.setInterval(() => { load(); refreshRemotes(); }, 8000);
    return () => { alive = false; window.clearInterval(t); };
  }, [activeDevice]);

  // 后台 CLI 会话清单：标记哪些工具有正在后台运行的控制台，可一键重新挂载。
  useEffect(() => {
    let alive = true;
    const poll = () => getTerminalSessions(activeDevice)
      .then((rows) => { if (alive) setBgSessions(rows.filter((s) => s.running)); })
      .catch(() => {});
    poll();
    const t = window.setInterval(poll, 5000);
    return () => { alive = false; window.clearInterval(t); };
  }, [activeDevice, terminalSession?.id]);

  useEffect(() => {
    if (!terminalSession?.id) return;
    let alive = true;
    const read = async () => {
      try {
        const res = await readTerminalSession(terminalSession.id, terminalDevice);
        if (!alive) return;
        if (res.output) setTerminalOutput((prev) => `${prev}${res.output}`.slice(-50000));
        if (res.session) setTerminalSession(res.session);
      } catch (err) {
        if (alive) setTerminalError(String(err));
      }
    };
    read();
    const t = window.setInterval(read, 700);
    return () => { alive = false; window.clearInterval(t); };
  }, [terminalSession?.id, terminalDevice]);

  const series = useMemo(() => ({
    health: samples.map((s) => s.health),
    disk: samples.map((s) => s.disk),
    load: samples.map((s) => s.load),
    loadPct: samples.map((s) => s.loadPct),
    ram: samples.map((s) => s.ram),
    service: samples.map((s) => s.service),
    intel: samples.map((s) => s.intel),
    memory: samples.map((s) => s.memory),
  }), [samples]);
  const terminalDisplay = useMemo(() => cleanTerminalOutput(terminalOutput), [terminalOutput]);

  const validRemotes = remotes.filter((r) => r.enabled !== false);
  const switchLabel = activeDevice === "local" ? "本机 LeoJarvis"
    : validRemotes.find((r) => r.id === activeDevice)?.name
    || "远程设备";
  const switchSub = activeDevice === "local" ? "127.0.0.1:8787"
    : validRemotes.find((r) => r.id === activeDevice)?.host
    || "";
  const isLocalDevice = activeDevice === "local";
  const deviceScope = isLocalDevice ? "本机" : "远端";
  const statusTitle = isLocalDevice ? "本机状态" : "远程状态";
  const serviceTitle = isLocalDevice ? "本机服务" : "远端服务";
  const agentTitle = isLocalDevice ? "本机编程服务" : "远端编程服务";
  const appsTitle = isLocalDevice ? "本机应用与邮件监控" : "远端应用与邮件监控";
  const sourceMeta = isLocalDevice ? "127.0.0.1:8787" : switchSub;
  const onDeviceChange = (value: string) => {
    setActiveDevice(value);
    setData(null);
    setSamples([]);
    setActiveApp(null);
    setActiveSignal(null);
    setActiveRepo(null);
    setActiveTool(null);
    setActiveService(null);
    setUpgradeResult("");
    setTerminalSession(null);
    setTerminalOutput("");
    setTerminalInput("");
    setTerminalError("");
  };
  const reconnectActive = async () => {
    if (activeDevice === "local") return;
    setDeviceError("正在重连…");
    try {
      const res = await connectRemoteLeoJarvis(activeDevice);
      if (!res.ok) {
        setDeviceError(res.error || "重连失败");
        return;
      }
      setDeviceError("");
      setData(null);
    } catch (err) {
      setDeviceError(String(err));
    }
  };
  const deviceSwitch = (
    <div className="dash-device-switch card">
      <div>
        <span className="kicker">Device Switch</span>
        <b>{switchLabel}</b>
        <small>{switchSub}</small>
      </div>
      <select value={activeDevice} onChange={(e) => onDeviceChange(e.target.value)}>
        <option value="local">本机 LeoJarvis</option>
        {validRemotes.length ? <optgroup label="远程 LeoJarvis 实例">{validRemotes.map((r) => <option key={r.id} value={r.id}>{r.name || r.host}{r.connected ? " · 已连接" : " · 未连接"}</option>)}</optgroup> : null}
      </select>
      {deviceError ? (
        <em className="device-error">
          {deviceError}
          {!isLocalDevice ? <button className="btn sm ghost" onClick={reconnectActive}>立即重连</button> : null}
        </em>
      ) : <em>{isLocalDevice ? "本机实时驾驶舱" : "通过 SSH tunnel 读取远程完整驾驶舱"}</em>}
    </div>
  );

  // 切换设备时保持设备切换条常驻，下方再显示骨架/错误，避免整页骨架把下拉藏起来。
  if (!data) return (
    <div className="dash">
      {deviceSwitch}
      {error ? <div className="error">{error}</div> : <PageSkeleton head={false} hero={false} cards={6} />}
    </div>
  );

  const notifications = data.notifications?.apps || [];
  const topBriefing = (data.briefing.top || []).filter((b) => b.kind !== "github_repo");
  const repos = data.intelligence.top_repos || [];
  const runtime = data.runtime;
  const diskPct = Number(data.health.system.disk_pct || 0);
  const ramPct = Number(data.health.system.memory_used_pct || 0);
  const load = Number(data.health.system.load || 0);
  const loadPct = Number(data.health.system.load_pct || 0);
  const cores = data.health.system.cores || 1;
  const servicePct = percent(data.health.services_online, data.health.services_total || 1);
  const memoryPending = data.memory.pending + data.memory.later;
  const newNotif = notifications.reduce((s, a) => s + (a.has_new ? Math.max(1, a.count) : 0), 0);

  async function doUpgradeTool(tool: AiToolStatus) {
    if (!tool.can_upgrade) return;
    if (!isLocalDevice) {
      setUpgradeResult("当前展示的是远端工具状态。为了避免误操作，本机 App 不会直接对远端执行升级；请登录对应远端主机后再升级。");
      return;
    }
    setUpgradingTool(tool.id);
    setUpgradeResult("");
    try {
      const res = await upgradeAiTool(tool.id);
      setUpgradeResult(`${res.ok ? "升级完成" : "升级失败"}：${res.command || tool.upgrade_command || ""}\n${res.output || res.error || ""}`);
      const next = await getCockpitOverview();
      setData(next);
    } catch (err) {
      setUpgradeResult(String(err));
    } finally {
      setUpgradingTool("");
    }
  }

  // 仅“脱离”：停止前端轮询、清空本地显示，但不杀进程——CLI 继续在后台独立运行。
  function detachToolTerminal() {
    setTerminalSession(null);
    setTerminalOutput("");
    setTerminalInput("");
    setTerminalError("");
  }

  // 显式“结束会话”：真正杀掉后台 CLI 进程。
  async function endToolTerminal() {
    if (terminalSession) {
      try { await closeTerminalSession(terminalSession.id, terminalDevice); } catch { /* best-effort */ }
    }
    detachToolTerminal();
    getTerminalSessions(activeDevice).then((rows) => setBgSessions(rows.filter((s) => s.running))).catch(() => {});
  }

  // 打开/重新挂载控制台：后端遇到同工具的后台会话会自动重新挂载并回放完整上下文。
  async function openToolTerminal(tool: AiToolStatus) {
    if (!tool.installed || terminalBusy) return;
    setTerminalBusy(true);
    setTerminalError("");
    setTerminalOutput("");
    setTerminalInput("");
    setTerminalSession(null);
    try {
      const res = await createTerminalSession(tool.id, "", activeDevice);
      if (!res.ok || !res.session) throw new Error(res.error || "CLI 控制台启动失败");
      setTerminalDevice(activeDevice);
      setTerminalSession(res.session);
      setTerminalOutput(res.output || "");
    } catch (err) {
      setTerminalError(String(err));
    } finally {
      setTerminalBusy(false);
    }
  }

  async function sendTerminalText() {
    if (!terminalSession || !terminalInput.trim()) return;
    const text = terminalInput.endsWith("\n") ? terminalInput : `${terminalInput}\n`;
    setTerminalInput("");
    try {
      await writeTerminalSession(terminalSession.id, text, terminalDevice);
    } catch (err) {
      setTerminalError(String(err));
    }
  }

  const stats: Stat[] = [
    {
      label: "综合健康",
      value: String(data.health.score),
      hint: data.health.score >= 80 ? "系统状态平稳" : `${data.health.attention_items?.length || 0} 个关注项，点击查看`,
      tone: data.health.score >= 80 ? "ok" : data.health.score >= 60 ? "warn" : "bad",
      values: series.health,
    },
    {
      label: "CPU 负载",
      value: `${load.toFixed(2)}`,
      hint: `${loadPct.toFixed(0)}% / ${cores} 核 · 1分钟平均`,
      tone: loadPct >= 120 ? "bad" : loadPct >= 80 ? "warn" : "ok",
      values: series.loadPct,
    },
    {
      label: "RAM 使用",
      value: ramPct ? String(ramPct.toFixed(0)) : "—",
      unit: ramPct ? "%" : undefined,
      hint: ramPct ? "内存压力与可用页估算" : "等待系统返回",
      tone: ramPct >= 90 ? "bad" : ramPct >= 78 ? "warn" : "ok",
      values: series.ram,
    },
    {
      label: "SSD 占用",
      value: String(diskPct),
      unit: "%",
      hint: "系统盘空间",
      tone: diskPct >= 88 ? "bad" : diskPct >= 75 ? "warn" : "ok",
      values: series.disk,
    },
    {
      label: "服务可用",
      value: `${data.health.services_online}/${data.health.services_total}`,
      hint: `在线率 ${servicePct}%`,
      tone: servicePct >= 80 ? "ok" : servicePct > 0 ? "warn" : "bad",
      values: series.service,
    },
    {
      label: "情报信号",
      value: String(data.intelligence.events),
      hint: "近 72 小时",
      tone: "neutral",
      values: series.intel,
    },
    {
      label: "记忆待确认",
      value: String(memoryPending),
      hint: "需人工确认",
      tone: memoryPending ? "warn" : "ok",
      values: series.memory,
    },
  ];

  return (
    <div className="dash">
      {deviceSwitch}

      <SectionTitle
        title={statusTitle}
        meta={`健康 ${data.health.score} · CPU ${load.toFixed(2)} (${loadPct.toFixed(0)}%) · RAM ${ramPct ? `${ramPct.toFixed(0)}%` : "—"} · SSD ${diskPct}% · 更新 ${fmtTime(data.generated_at, false)}`}
      />
      <div className="dash-stats">
        {stats.map((stat) => <StatBlock stat={stat} key={stat.label} onClick={stat.label === "综合健康" ? () => setShowHealthDetail(true) : undefined} />)}
      </div>

      <SectionTitle
        title="运行态势"
        meta={runtime
          ? `${deviceScope} · 服务 ${runtime.services_online}/${runtime.services_total} · 工具 ${runtime.tools_ready}/${runtime.tools_total} · 子智能体 ${runtime.agents_running}`
          : undefined}
      />
      <div className="dash-runtime">
        <article className="dash-panel">
          <div className="dash-panel-head"><b>{serviceTitle}</b><span>{data.health.services_online}/{data.health.services_total} 在线</span></div>
          <div className="dash-svc-list">
            {data.services.map((svc) => {
              const visual = serviceVisual(svc);
              return (
                <button
                  className={`dash-svc runtime-icon-card ${svc.online ? "online" : "offline"} tone-${visual.tone} ${visual.icon || visual.image ? "has-real-icon" : "has-fallback-icon"}`}
                  key={`${svc.name}:${svc.port}`}
                  onClick={() => setActiveService(svc)}
                  title={`${svc.name} · 127.0.0.1:${svc.port} · ${svc.online ? "在线" : "离线"}`}
                >
                  <span className="runtime-icon-shell">
                    <RuntimeIcon visual={visual} />
                    <span className="status-lamp" />
                  </span>
                  <b>{visual.name}</b>
                  <em>:{svc.port}</em>
                </button>
              );
            })}
          </div>
        </article>

        <article className="dash-panel">
          <div className="dash-panel-head"><b>{agentTitle}</b><span>{runtime?.tools_running ?? 0} 运行中</span></div>
          <div className="dash-tool-list">
            {(runtime?.ai_tools || []).map((tool) => {
              const visual = toolVisual(tool);
              const hasBg = bgSessions.some((s) => s.tool_id === tool.id);
              return (
                <button
                  className={`dash-tool runtime-icon-card ${tool.installed ? "on" : "off"} ${hasBg || tool.running ? "running" : ""} ${hasBg ? "has-bg" : ""} tone-${visual.tone} ${visual.icon || visual.image ? "has-real-icon" : "has-fallback-icon"}`}
                  key={tool.id}
                  onClick={() => setActiveTool(tool)}
                  title={`${tool.name} · ${!tool.installed ? "未安装" : hasBg ? "后台控制台运行中" : tool.running ? "运行中" : "就绪"}`}
                >
                  <span className="runtime-icon-shell">
                    <RuntimeIcon visual={visual} />
                    <span className="status-lamp" />
                  </span>
                  <b>{visual.name}</b>
                  <i>{!tool.installed ? "未安装" : hasBg ? "后台运行" : tool.running ? "运行中" : "就绪"}</i>
                </button>
              );
            })}
            {(runtime?.agents || []).map((agent) => (
              <div className={`dash-tool runtime-icon-card ${agent.status === "running" ? "running on" : "off"} tone-agent has-fallback-icon`} key={agent.id}>
                <span className="runtime-icon-shell">
                  <span>{initials(agent.name)}</span>
                  <span className="status-lamp" />
                </span>
                <b>{compactName(agent.name)}</b>
                <i>{agent.status === "running" ? "运行中" : agent.status}</i>
              </div>
            ))}
            {(runtime?.agents || []).length === 0 ? <div className="dash-mini-empty">暂无后台子智能体</div> : null}
          </div>
        </article>
      </div>

      <SectionTitle
        title={appsTitle}
        meta={`${deviceScope} ${sourceMeta} · ${newNotif} 个新通知信号 · 仅读取应用级计数，不抓取内容`}
      />
      <div className="dash-apps">
        {notifications.map((app) => (
          <button className={`dash-app dash-${statusTone(app.status)}`} key={app.id} onClick={() => setActiveApp(app)}>
            <AppIcon app={app} />
            <div className="dash-app-info">
              <b>{app.name}</b>
              <span>{app.category || "应用"}</span>
            </div>
            <div className="dash-app-state">
              {app.has_new ? <em className="badge">{app.count}</em> : null}
              <i>{app.status}</i>
            </div>
          </button>
        ))}
      </div>

      <SectionTitle title="今日情报与雷达" meta="处理后信息 · 点击查看详情" />
      <div className="dash-signal-grid">
        <section className="dash-signal-panel">
          <div className="dash-signal-head">
            <div>
              <b>资讯情报</b>
              <span>已筛选 · 已评分 · 已中文化</span>
            </div>
            <em>{topBriefing.length} 条</em>
          </div>
          {topBriefing.length === 0 ? <div className="empty compact">暂无足够高价值的信息进入驾驶舱。</div> : (
            <div className="dash-signal-list">
              {topBriefing.slice(0, 6).map((item, index) => (
                <button className={`dash-signal-item ${index === 0 ? "lead" : ""}`} key={item.event_id} onClick={() => setActiveSignal(item)}>
                  <div>
                    <span className={`dash-pri pri-${item.priority || "观察"}`}>{item.priority || "观察"}</span>
                    <em>{item.source} · {fmtTime(item.ts)}</em>
                  </div>
                  <b>{item.title}</b>
                  <p>{item.take}</p>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="dash-signal-panel">
          <div className="dash-signal-head">
            <div>
              <b>GitHub 雷达</b>
              <span>近期项目 · 高增速 · 高相关</span>
            </div>
            <em>{repos.length} 项</em>
          </div>
          {repos.length === 0 ? <div className="empty compact">暂无达到驾驶舱阈值的 GitHub 项目。</div> : (
            <div className="dash-repo-compact">
              {repos.slice(0, 6).map((repo, index) => (
                <button className={`dash-repo-row ${index === 0 ? "lead" : ""}`} key={repo.name} onClick={() => setActiveRepo(repo)}>
                  <div className="dash-repo-row-top">
                    <span>{repo.language || "项目"}</span>
                    <b>{formatRepoSpeed(repo.speed)}</b>
                  </div>
                  <h3>{repo.name}</h3>
                  <p>{repo.summary}</p>
                  <div className="dash-repo-row-foot">
                    <span>{repo.stars ? `${repo.stars.toLocaleString()} 星` : "星标观察中"}</span>
                    <span>{repo.priority || "高优先"}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* ===== 详情弹层 ===== */}
      <Modal open={showHealthDetail} onClose={() => setShowHealthDetail(false)} kicker="综合健康" title={`健康值 ${data.health.score}`}>
        <div className="modal-rich">
          <p className="lead">健康值是 SSD 空间、CPU 负载、RAM 压力、本地服务在线率和待确认记忆共同计算的综合分，不是单独的 CPU 数字。</p>
          <div className="health-attention-list">
            {(data.health.attention_items || []).length === 0 ? (
              <div className="modal-info-block"><span>当前无关注项</span><p>系统盘、负载、服务和记忆队列都处于可接受区间。</p></div>
            ) : (data.health.attention_items || []).map((item) => (
              <div className={`health-attention ${item.level === "异常" ? "bad" : "warn"}`} key={`${item.label}-${item.detail}`}>
                <b>{item.label}</b><em>{item.level}</em><p>{item.detail}</p>
              </div>
            ))}
          </div>
          <div className="modal-meta">
            <span>CPU {load.toFixed(2)} / {cores} 核</span>
            <span>RAM {ramPct ? `${ramPct.toFixed(0)}%` : "—"}</span>
            <span>SSD {diskPct}%</span>
            <span>服务 {data.health.services_online}/{data.health.services_total}</span>
          </div>
        </div>
      </Modal>

      <Modal open={!!activeApp} onClose={() => setActiveApp(null)} kicker={activeApp?.category} title={activeApp ? (
        <span className="modal-app-title">
          {activeApp.icon ? <img src={activeApp.icon} alt="" width={28} height={28} /> : null}
          {activeApp.name}
        </span>
      ) : ""}>
        {activeApp ? (
          <div className="modal-kv">
            <div><span>通知状态</span><b className={`tone-${statusTone(activeApp.status)}`}>{activeApp.status}</b></div>
            <div><span>未读通知</span><b>{activeApp.has_new ? activeApp.count : 0}</b></div>
            <div><span>运行状态</span><b>{activeApp.running ? "运行中" : "未运行"}</b></div>
            <div><span>已安装</span><b>{activeApp.installed ? "是" : "否"}</b></div>
            <div><span>检测时间</span><b>{fmtTime(activeApp.checked_at, false)}</b></div>
            <p className="modal-note">{activeApp.detail}</p>
            {activeApp.id === "mail" && activeApp.recent?.length ? (
              <div className="modal-info-block">
                <span>最近读取到的邮件</span>
                <ul className="mail-recent-list">
                  {activeApp.recent.slice(0, 6).map((mail, i) => (
                    <li key={`${mail.ts || i}-${mail.title || i}`}>
                      <b>{mail.title || "（无主题邮件）"}</b>
                      <em>{mail.source || "Apple Mail"} · {fmtTime(mail.ts)}</em>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {activeApp.mechanism ? (
              <div className="modal-info-block">
                <span>如何看到通知</span>
                <p>{activeApp.mechanism}</p>
              </div>
            ) : null}
            {activeApp.setup ? (
              <div className="modal-info-block">
                <span>{activeApp.id === "mail" ? "如何配置邮件" : "如何启用"}</span>
                <p>{activeApp.setup}</p>
              </div>
            ) : null}
            <p className="modal-note privacy">{data.notifications?.privacy}</p>
          </div>
        ) : null}
      </Modal>

      <Modal open={!!activeSignal} onClose={() => setActiveSignal(null)} kicker={activeSignal?.priority || "情报"} title={activeSignal?.title} width={1040}
        footer={activeSignal?.url ? <a className="btn primary sm" href={activeSignal.url} target="_blank" rel="noreferrer">打开来源</a> : null}>
        {activeSignal ? (
          <BriefingSignalDetail item={activeSignal} evidence={evidenceList(activeSignal)} />
        ) : null}
      </Modal>

      <Modal open={!!activeRepo} onClose={() => setActiveRepo(null)} kicker="GitHub 项目" title={activeRepo?.name} width={1040}
        footer={activeRepo?.url ? <a className="btn primary sm" href={activeRepo.url} target="_blank" rel="noreferrer">打开项目</a> : null}>
        {activeRepo ? (
          <GithubRepoDetail repo={activeRepo} />
        ) : null}
      </Modal>

      <Modal open={!!activeTool} onClose={() => { setActiveTool(null); setUpgradeResult(""); detachToolTerminal(); }} kicker={agentTitle} title={activeTool?.name}
        footer={activeTool ? (
          <div className="modal-actions">
            {activeTool.installed ? (
              terminalSession ? (
                <>
                  <button className="btn sm ghost" onClick={() => { setActiveTool(null); setUpgradeResult(""); detachToolTerminal(); }}>最小化（后台运行）</button>
                  <button className="btn sm danger" onClick={() => void endToolTerminal()}>结束会话</button>
                </>
              ) : <button className="btn sm primary" onClick={() => void openToolTerminal(activeTool)} disabled={terminalBusy}>{terminalBusy ? "启动中" : (bgSessions.some((s) => s.tool_id === activeTool.id) ? "重新挂载控制台" : "打开控制台")}</button>
            ) : null}
            {activeTool.can_upgrade && isLocalDevice ? <button className="btn sm" onClick={() => activeTool && doUpgradeTool(activeTool)} disabled={!!upgradingTool}>{upgradingTool ? "升级中" : "一键升级"}</button> : null}
          </div>
        ) : null}>
        {activeTool ? (
          <div className="modal-kv">
            <div><span>安装状态</span><b>{activeTool.installed ? "已安装" : "未安装"}</b></div>
            <div><span>当前版本</span><b>{activeTool.current_version}</b></div>
            <div><span>最新版本</span><b>{activeTool.latest_version}</b></div>
            <div><span>更新</span><b>{activeTool.update_state}</b></div>
            <div><span>包管理器</span><b>{activeTool.package_manager || "—"}</b></div>
            <div><span>运行状态</span><b>{activeTool.running ? "运行中" : "未运行"}</b></div>
            <div><span>启动命令</span><b><code>{activeTool.launch}</code></b></div>
            {activeTool.upgrade_command ? <div><span>升级命令</span><b><code>{activeTool.upgrade_command}</code></b></div> : null}
            {activeTool.path ? <p className="modal-note"><code>{activeTool.path}</code></p> : null}
            <p className="modal-note">{activeTool.advice}</p>
            {!isLocalDevice ? <p className="modal-note">当前为远端设备：控制台通过远端 LeoJarvis 白名单接口启动；升级操作仍需登录远端主机确认。</p> : null}
            {upgradeResult ? <pre className="toolResult">{upgradeResult}</pre> : null}
            {terminalError ? <p className="modal-note tone-bad">{terminalError}</p> : null}
            {terminalSession ? (
              <section className="cli-console">
                <div className="cli-console-head">
                  <b>{terminalSession.tool_name}</b>
                  <span>{terminalSession.running ? "运行中" : `已结束 ${terminalSession.exit_code ?? ""}`} · {terminalSession.command}</span>
                </div>
                <pre>{terminalDisplay || "控制台已启动，等待输出…"}</pre>
                <div className="cli-console-input">
                  <input
                    value={terminalInput}
                    placeholder="输入命令或提示，Enter 发送"
                    onChange={(e) => setTerminalInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") void sendTerminalText(); }}
                  />
                  <button className="btn sm primary" onClick={() => void sendTerminalText()} disabled={!terminalInput.trim() || !terminalSession.running}>发送</button>
                </div>
              </section>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <Modal open={!!activeService} onClose={() => setActiveService(null)} kicker={serviceTitle} title={activeService?.name}>
        {activeService ? (
          <div className="modal-kv">
            <div><span>状态</span><b className={activeService.online ? "tone-ok" : "tone-bad"}>{activeService.online ? "在线" : "离线"}</b></div>
            <div><span>服务端口</span><b>{deviceScope} 127.0.0.1:{activeService.port}</b></div>
            <div><span>进程 PID</span><b>{activeService.pid || "—"}</b></div>
            <div><span>可自动重启</span><b>{activeService.can_restart ? "是" : "否"}</b></div>
            <div><span>来源</span><b>{activeService.source || "配置"}</b></div>
            {activeService.process ? <div><span>进程</span><b>{activeService.process}</b></div> : null}
            {activeService.cwd ? <div><span>工作目录</span><b>{activeService.cwd}</b></div> : null}
            {activeService.address ? <div><span>监听地址</span><b>{activeService.address}</b></div> : null}
            <p className="modal-note">{activeService.desc || serviceTitle}</p>
            {activeService.command ? <p className="modal-note">{activeService.command}</p> : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
