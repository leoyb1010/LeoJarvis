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
  getBriefingItem,
  getCockpitOverview,
  upgradeAiTool,
  type AiToolStatus,
  type BriefingItem,
  type CockpitGithubCard,
  type CockpitOverview,
  type LocalNotificationApp,
  type ServiceRow,
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
  const [detailLoadingId, setDetailLoadingId] = useState("");
  const [activeRepo, setActiveRepo] = useState<CockpitGithubCard | null>(null);
  const [activeTool, setActiveTool] = useState<AiToolStatus | null>(null);
  const [activeService, setActiveService] = useState<ServiceRow | null>(null);
  const [showHealthDetail, setShowHealthDetail] = useState(false);
  const [upgradingTool, setUpgradingTool] = useState("");
  const [upgradeResult, setUpgradeResult] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () => {
      getCockpitOverview()
        .then((res) => {
          if (!alive) return;
          setError("");
          setData(res);
          setSamples((prev) => {
            const next = [...prev.filter((row) => row.ts !== res.generated_at), sampleFrom(res)].slice(-40);
            try { localStorage.setItem("cortex-dashboard-samples", JSON.stringify(next)); } catch { /* optional */ }
            return next;
          });
        })
        .catch((err) => { if (alive) setError(String(err)); });
    };
    load();
    const t = window.setInterval(load, 8000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);

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

  const deviceScope = "本机";
  const statusTitle = "本机状态";
  const serviceTitle = "本机服务";
  const agentTitle = "本机编程服务";
  const appsTitle = "本机应用与邮件监控";
  const sourceMeta = "127.0.0.1:8787";
  const openSignalDetail = async (item: BriefingItem) => {
    setActiveSignal(item.source_detail_translated ? item : { ...item, detail: "", source_detail: "", source_detail_missing: false });
    setDetailLoadingId(item.event_id);
    try {
      const detailed = await getBriefingItem(item.event_id);
      setActiveSignal(detailed);
    } catch {
      setActiveSignal({ ...item, detail: "", source_detail: "详情翻译失败，请先打开来源查看原文。", source_detail_missing: false });
    } finally {
      setDetailLoadingId("");
    }
  };

  if (!data) return (
    <div className="dash">
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
      <div className="dash-device-switch card">
        <div>
          <span className="kicker">Device</span>
          <b>本机 LeoJarvis</b>
          <small>127.0.0.1:8787</small>
        </div>
        <em>本机实时驾驶舱</em>
      </div>

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
              return (
                <button
                  className={`dash-tool runtime-icon-card ${tool.installed ? "on" : "off"} ${tool.running ? "running" : ""} tone-${visual.tone} ${visual.icon || visual.image ? "has-real-icon" : "has-fallback-icon"}`}
                  key={tool.id}
                  onClick={() => setActiveTool(tool)}
                  title={`${tool.name} · ${!tool.installed ? "未安装" : tool.running ? "运行中" : "就绪"}`}
                >
                  <span className="runtime-icon-shell">
                    <RuntimeIcon visual={visual} />
                    <span className="status-lamp" />
                  </span>
                  <b>{visual.name}</b>
                  <i>{!tool.installed ? "未安装" : tool.running ? "运行中" : "就绪"}</i>
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
                <button className={`dash-signal-item ${index === 0 ? "lead" : ""}`} key={item.event_id} onClick={() => openSignalDetail(item)}>
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
          <BriefingSignalDetail item={activeSignal} evidence={evidenceList(activeSignal)} loading={detailLoadingId === activeSignal.event_id} />
        ) : null}
      </Modal>

      <Modal open={!!activeRepo} onClose={() => setActiveRepo(null)} kicker="GitHub 项目" title={activeRepo?.name} width={1040}
        footer={activeRepo?.url ? <a className="btn primary sm" href={activeRepo.url} target="_blank" rel="noreferrer">打开项目</a> : null}>
        {activeRepo ? (
          <GithubRepoDetail repo={activeRepo} />
        ) : null}
      </Modal>

      <Modal open={!!activeTool} onClose={() => { setActiveTool(null); setUpgradeResult(""); }} kicker={agentTitle} title={activeTool?.name}
        footer={activeTool?.can_upgrade ? <button className="btn sm primary" onClick={() => activeTool && doUpgradeTool(activeTool)} disabled={!!upgradingTool}>{upgradingTool ? "升级中" : "一键升级"}</button> : null}>
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
            {upgradeResult ? <pre className="toolResult">{upgradeResult}</pre> : null}
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
