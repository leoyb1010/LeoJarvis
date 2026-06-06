import { useEffect, useMemo, useState } from "react";
import {
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
  if (status === "有新通知") return "ok";
  if (status === "无新通知") return "neutral";
  if (status === "未授权" || status === "未配置") return "warn";
  return "neutral";
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

  useEffect(() => {
    let alive = true;
    const load = () =>
      getCockpitOverview()
        .then((res) => {
          if (!alive) return;
          setData(res);
          setSamples((prev) => {
            const next = [...prev.filter((row) => row.ts !== res.generated_at), sampleFrom(res)].slice(-40);
            storeSamples(next);
            return next;
          });
        })
        .catch((err) => { if (alive) setError(String(err)); });
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

  if (error && !data) return <div className="error">{error}</div>;
  if (!data) return <PageSkeleton cards={8} />;

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
      {/* 本机状态：扁平指标块 */}
      <SectionTitle
        title="本机状态"
        meta={`健康 ${data.health.score} · CPU ${load.toFixed(2)} (${loadPct.toFixed(0)}%) · RAM ${ramPct ? `${ramPct.toFixed(0)}%` : "—"} · SSD ${diskPct}% · 更新 ${fmtTime(data.generated_at, false)}`}
      />
      <div className="dash-stats">
        {stats.map((stat) => <StatBlock stat={stat} key={stat.label} onClick={stat.label === "综合健康" ? () => setShowHealthDetail(true) : undefined} />)}
      </div>

      {/* 运行态势：本机服务 + 编程/Agent 工具 + 子智能体 */}
      <SectionTitle
        title="运行态势"
        meta={runtime
          ? `服务 ${runtime.services_online}/${runtime.services_total} · 工具 ${runtime.tools_ready}/${runtime.tools_total} · 子智能体 ${runtime.agents_running}`
          : undefined}
      />
      <div className="dash-runtime">
        <article className="dash-panel">
          <div className="dash-panel-head"><b>本机服务</b><span>{data.health.services_online}/{data.health.services_total} 在线</span></div>
          <div className="dash-svc-list">
            {data.services.map((svc) => (
              <button className={`dash-svc ${svc.online ? "online" : "offline"}`} key={svc.name} onClick={() => setActiveService(svc)}>
                <span className="dot" />
                <b>{svc.name}</b>
                <em>:{svc.port}</em>
                <i>{svc.online ? "在线" : "离线"}</i>
              </button>
            ))}
          </div>
        </article>

        <article className="dash-panel">
          <div className="dash-panel-head"><b>编程与 Agent</b><span>{runtime?.tools_running ?? 0} 运行中</span></div>
          <div className="dash-tool-list">
            {(runtime?.ai_tools || []).map((tool) => (
              <button className={`dash-tool ${tool.installed ? "on" : "off"} ${tool.running ? "running" : ""}`} key={tool.id} onClick={() => setActiveTool(tool)}>
                <span className="dot" />
                <b>{tool.name}</b>
                <i>{!tool.installed ? "未安装" : tool.running ? "运行中" : "就绪"}</i>
              </button>
            ))}
            {(runtime?.agents || []).map((agent) => (
              <div className={`dash-tool ${agent.status === "running" ? "running on" : "off"}`} key={agent.id}>
                <span className="dot" />
                <b>{agent.name}</b>
                <i>{agent.status === "running" ? "运行中" : agent.status}</i>
              </div>
            ))}
            {(runtime?.agents || []).length === 0 ? <div className="dash-mini-empty">暂无后台子智能体</div> : null}
          </div>
        </article>
      </div>

      {/* 应用与邮件：真实图标，点击查看详情 */}
      <SectionTitle
        title="应用与邮件监控"
        meta={`${newNotif} 个新通知信号 · 仅读取应用级计数，不抓取内容`}
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

      {/* 资讯：点击呼出详情卡片 */}
      <SectionTitle title="今日关键情报" meta="已筛选 · 已评分 · 已中文化 · 点击查看详情" />
      {topBriefing.length === 0 ? (
        <div className="empty">暂无足够高价值的信息进入驾驶舱。</div>
      ) : (
        <div className="dash-intel-layout">
          <button className="dash-intel-hero" onClick={() => setActiveSignal(topBriefing[0])}>
            <span className={`dash-pri pri-${topBriefing[0].priority || "观察"}`}>{topBriefing[0].priority || "观察"}</span>
            <h3>{topBriefing[0].title}</h3>
            <p>{topBriefing[0].take}</p>
            <div><em>{topBriefing[0].source}</em><em>{fmtTime(topBriefing[0].ts)}</em></div>
          </button>
          <div className="dash-intel-rail">
            {topBriefing.slice(1).map((item) => (
              <button className="dash-feed-card compact" key={item.event_id} onClick={() => setActiveSignal(item)}>
                <div className="dash-feed-top">
                  <span className={`dash-pri pri-${item.priority || "观察"}`}>{item.priority || "观察"}</span>
                  <em>{item.source}</em>
                </div>
                <b>{item.title}</b>
                <p>{item.take}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* GitHub：点击呼出详情卡片 */}
      <SectionTitle title="GitHub 高增速雷达" meta="只展示处理后项目 · 点击查看详情" />
      {repos.length === 0 ? (
        <div className="empty">暂无达到驾驶舱阈值的 GitHub 项目。</div>
      ) : (
        <div className="dash-repo-board">
          {repos.map((repo, index) => (
            <button className={`dash-repo-card ${index === 0 ? "hero" : ""}`} key={repo.name} onClick={() => setActiveRepo(repo)}>
              <div className="dash-repo-meta">
                <span>{repo.language || "项目"}</span>
                <b>{repo.speed ? `+${repo.speed}/天` : "观察"}</b>
              </div>
              <h3>{repo.name}</h3>
              <p>{repo.summary}</p>
              <div className="dash-repo-foot">
                <span>{repo.stars ? `${repo.stars.toLocaleString()} 星` : "星标观察中"}</span>
                <span>{repo.priority || "高优先"}</span>
              </div>
            </button>
          ))}
        </div>
      )}

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

      <Modal open={!!activeSignal} onClose={() => setActiveSignal(null)} kicker={activeSignal?.priority || "情报"} title={activeSignal?.title}
        footer={activeSignal?.url ? <a className="btn primary sm" href={activeSignal.url} target="_blank" rel="noreferrer">打开来源</a> : null}>
        {activeSignal ? (
          <div className="modal-rich">
            <p className="lead">{activeSignal.take}</p>
            <div className="modal-grid">
              <div><span>为什么重要</span><p>{activeSignal.why_important || "已通过情报评分进入驾驶舱。"}</p></div>
              <div><span>和我的关系</span><p>{activeSignal.relation || "与你的关注项、历史偏好相关。"}</p></div>
              <div><span>下一步</span><p>{activeSignal.next_step || "阅读原文，判断是否写入个人记事或持续关注。"}</p></div>
            </div>
            <div className="modal-meta">
              <span>{activeSignal.source}</span>
              <span>{activeSignal.domain_label || "情报"}</span>
              <span>评分 {activeSignal.score?.toFixed(2)}</span>
              <span>{fmtTime(activeSignal.ts)}</span>
            </div>
            {activeSignal.tags?.length ? <div className="modal-tags">{activeSignal.tags.slice(0, 8).map((t) => <span key={t}>{t}</span>)}</div> : null}
          </div>
        ) : null}
      </Modal>

      <Modal open={!!activeRepo} onClose={() => setActiveRepo(null)} kicker="GitHub 项目" title={activeRepo?.name}
        footer={activeRepo?.url ? <a className="btn primary sm" href={activeRepo.url} target="_blank" rel="noreferrer">打开项目</a> : null}>
        {activeRepo ? (
          <div className="modal-rich">
            <p className="lead">{activeRepo.summary}</p>
            <div className="modal-meta">
              <span>{activeRepo.stars ? `${activeRepo.stars.toLocaleString()} 星标` : "星标观察中"}</span>
              <span>{activeRepo.speed ? `+${activeRepo.speed}/天` : "观察"}</span>
              {activeRepo.language ? <span>{activeRepo.language}</span> : null}
              <span>评分 {activeRepo.score?.toFixed(2)}</span>
            </div>
            <div className="modal-grid">
              <div><span>推荐理由</span><p>{activeRepo.why}</p></div>
              <div><span>与我相关</span><p>{activeRepo.relation}</p></div>
              <div><span>下一步</span><p>{activeRepo.next_step}</p></div>
            </div>
            {activeRepo.tags?.length ? <div className="modal-tags">{activeRepo.tags.slice(0, 8).map((t) => <span key={t}>{t}</span>)}</div> : null}
          </div>
        ) : null}
      </Modal>

      <Modal open={!!activeTool} onClose={() => { setActiveTool(null); setUpgradeResult(""); }} kicker="编程 / Agent 工具" title={activeTool?.name}
        footer={activeTool?.can_upgrade ? <button className="btn primary sm" onClick={() => activeTool && doUpgradeTool(activeTool)} disabled={!!upgradingTool}>{upgradingTool ? "升级中" : "一键升级"}</button> : null}>
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

      <Modal open={!!activeService} onClose={() => setActiveService(null)} kicker="本机服务" title={activeService?.name}>
        {activeService ? (
          <div className="modal-kv">
            <div><span>状态</span><b className={activeService.online ? "tone-ok" : "tone-bad"}>{activeService.online ? "在线" : "离线"}</b></div>
            <div><span>端口</span><b>127.0.0.1:{activeService.port}</b></div>
            <div><span>进程 PID</span><b>{activeService.pid || "—"}</b></div>
            <div><span>可自动重启</span><b>{activeService.can_restart ? "是" : "否"}</b></div>
            <p className="modal-note">{activeService.desc || "本地服务"}</p>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
