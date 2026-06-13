import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  addSshDevice,
  getDeviceOpsStatus,
  getDevices,
  getDevTools,
  getServices,
  getSystemOverview,
  previewDeviceOps,
  probeSshDevices,
  sendSelfHeartbeat,
  upgradeAiTool,
  type AiToolStatus,
  type DeviceOpsPreview,
  type DeviceOpsStatus,
  type DeviceOpsTarget,
  type DeviceSummary,
  type DevToolchain,
  type ServiceRow,
  type SystemModule,
  type SystemOverview,
} from "../../api";
import { PageSkeleton } from "../Skeleton";
import { Modal } from "../Modal";

function fmtTime(ts?: number) {
  return ts ? new Date(ts * 1000).toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "未检测";
}

function levelClass(level: string) {
  if (level === "异常") return "bad";
  if (level === "注意") return "warn";
  return "good";
}

const MODULE_ICON: Record<string, string> = {
  disk: "M4 6h16v4H4zM4 14h16v4H4z",
  cpu: "M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M6 6h12v12H6z M9 9h6v6H9z",
  memory: "M4 8h16v8H4z M7 8v8 M11 8v8 M15 8v8",
  network: "M12 4a8 8 0 0 0 0 16 M12 4a8 8 0 0 1 0 16 M4 12h16",
  thermal: "M12 3v10 M9 13a3 3 0 1 0 6 0 M10 3h4 M10 7h4",
  battery: "M3 8h16v8H3z M20 11h1v2h-1 M6 11h8",
};

function moduleProgress(module: SystemModule) {
  const pct = Number(module.metrics.used_pct ?? module.metrics.free_pct ?? 0);
  if (module.id === "memory" && module.metrics.free_pct != null) return Math.max(4, Math.min(100, 100 - pct));
  if (module.id === "cpu") {
    const loadV = Number(module.metrics.load_1 || 0);
    const cores = Number(module.metrics.cores || 1);
    return Math.max(4, Math.min(100, (loadV / Math.max(1, cores)) * 100));
  }
  if (module.id === "network") return module.metrics.online ? 80 : 8;
  return Math.max(4, Math.min(100, pct));
}

function Ring({ pct, tone, size = 56 }: { pct: number; tone: string; size?: number }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(100, pct)) / 100);
  return (
    <svg className={`sys-ring tone-${tone}`} viewBox="0 0 64 64" width={size} height={size}>
      <circle cx="32" cy="32" r={r} className="ring-track" />
      <circle cx="32" cy="32" r={r} className="ring-bar" strokeDasharray={c} strokeDashoffset={off} transform="rotate(-90 32 32)" />
    </svg>
  );
}

function MetricCard({ module, index }: { module: SystemModule; index: number }) {
  const tone = levelClass(module.level);
  return (
    <motion.article
      className={`sys-metric ${tone}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      title={module.advice}
    >
      <div className="sys-metric-head">
        <div className="sys-metric-ring">
          <Ring pct={moduleProgress(module)} tone={tone} size={46} />
          <svg className="sys-module-icon" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
            <path d={MODULE_ICON[module.id] || "M4 4h16v16H4z"} />
          </svg>
        </div>
        <em className={`sys-tag ${tone}`}>{module.level}</em>
      </div>
      <span className="sys-metric-name">{module.name}</span>
      <b className="sys-metric-value">{module.value}</b>
      <p className="sys-metric-sub">{module.summary}</p>
    </motion.article>
  );
}

function SectionHead({ title, desc, meta, children }: { title: string; desc?: string; meta?: string; children?: React.ReactNode }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {desc ? <p>{desc}</p> : null}
      </div>
      <div className="section-head-side">
        {meta ? <span className="section-meta">{meta}</span> : null}
        {children}
      </div>
    </div>
  );
}

function pct(value?: number | null) {
  return value == null ? "—" : `${Math.round(value)}%`;
}

// 卡片上只放得下短版本号；完整版本字符串在详情弹层里看。
function shortVersion(raw?: string) {
  if (!raw || raw === "未安装") return "—";
  const m = raw.match(/\d+\.\d+(?:\.\d+)?/);
  if (m) return `v${m[0]}`;
  return raw.length > 14 ? "已安装" : raw;
}

function ageLabel(seconds?: number) {
  if (seconds == null) return "刚刚";
  if (seconds < 60) return `${seconds}s 前`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m 前`;
  return `${Math.round(seconds / 3600)}h 前`;
}

function deviceTone(device: DeviceSummary) {
  if (!device.online) return "offline";
  if (device.status === "异常" || device.health < 65) return "bad";
  if (device.status === "注意" || device.health < 82) return "warn";
  return "good";
}

function DeviceCard({ device }: { device: DeviceSummary }) {
  const t = deviceTone(device);
  const m = device.metrics || {};
  return (
    <article className={`device-card ${t}`}>
      <div className="device-card-head">
        <div>
          <span className="device-kicker">{device.role || "mac"} · {device.model || device.host_name || "Mac"}</span>
          <h3>{device.device_name}</h3>
          <p>{device.host_name || device.device_id}</p>
          {device.remote_control ? (
            <span className={`rc-badge ${device.remote_control.connected ? "on" : "off"}`} title={device.remote_control.connected ? "远控隧道已连接，可在驾驶舱切换到这台机器" : device.remote_control.error || "远控通道未连接"}>
              {device.remote_control.connected ? "远控已连接" : "远控未连接"}
            </span>
          ) : null}
        </div>
        <div className="device-score"><b>{Math.round(device.health || 0)}</b><span>{device.online ? device.status : "离线"}</span></div>
      </div>
      <div className="device-metrics">
        <div><span>CPU</span><b>{pct(m.cpu_load_pct)}</b><em>{m.cpu_load ?? "—"} / {m.cpu_cores || "?"} 核</em></div>
        <div><span>RAM</span><b>{pct(m.ram_used_pct)}</b><em>{m.ram_total_gb ? `${m.ram_used_gb ?? "—"}G / ${m.ram_total_gb}G` : "内存"}</em></div>
        <div><span>SSD</span><b>{pct(m.ssd_used_pct)}</b><em>{m.ssd_free_gb != null ? `剩余 ${m.ssd_free_gb}G` : "磁盘"}</em></div>
        <div><span>温控</span><b>{m.thermal_pressure != null ? String(m.thermal_pressure) : "—"}</b><em>{device.modules?.thermal?.value || "热压力"}</em></div>
        <div><span>电源</span><b>{m.battery_percent != null ? `${m.battery_percent}%` : "—"}</b><em>{m.battery_plugged ? "外接电源" : "电池/未知"}</em></div>
        <div><span>网络</span><b>{m.network_latency_ms != null ? `${m.network_latency_ms}ms` : "—"}</b><em>{m.uptime_hours != null ? `运行 ${m.uptime_hours}h` : "连通性"}</em></div>
      </div>
      <div className="device-risks">
        {(device.risks || []).slice(0, 2).map((risk) => <span className={risk.level === "异常" ? "bad" : risk.level === "注意" ? "warn" : "good"} key={`${risk.title}-${risk.advice}`} title={risk.advice}><b>{risk.level}</b>{risk.title}</span>)}
        {(device.risks || []).length === 0 ? <span className="good"><b>健康</b>暂无风险项</span> : null}
      </div>
      <div className="device-foot"><span>{device.online ? "在线" : "离线"}</span><span>心跳 {ageLabel(device.age_seconds)}</span></div>
    </article>
  );
}

const OPS_ACTIONS = [
  ["status", "系统状态"],
  ["clean", "缓存清理预览"],
  ["optimize", "系统优化预览"],
  ["purge", "项目垃圾预览"],
  ["installers", "安装包扫描"],
  ["analyze", "磁盘地图"],
  ["apps", "应用列表"],
] as const;

function DeviceOpsCard({
  target,
  onPreview,
  busy,
}: {
  target: DeviceOpsTarget;
  onPreview: (target: DeviceOpsTarget, action: string) => void;
  busy: string;
}) {
  const ready = target.mole_installed;
  return (
    <article className={`ops-card ${ready ? "ready" : "missing"}`}>
      <div className="ops-card-head">
        <div>
          <span>{target.kind === "local" ? "本机" : "SSH 主机"} · {target.host || "localhost"}</span>
          <h3>{target.target_name}</h3>
          <p>{ready ? target.version || target.mo_path : target.error || target.install_hint}</p>
        </div>
        <b>{ready ? "Mole 就绪" : "需安装"}</b>
      </div>
      <div className="ops-actions">
        {OPS_ACTIONS.map(([id, label]) => (
          <button key={id} disabled={!ready || !!busy} onClick={() => onPreview(target, id)}>
            {busy === `${target.target_id}:${id}` ? "扫描中" : label}
          </button>
        ))}
      </div>
    </article>
  );
}

export function SystemView() {
  const [data, setData] = useState<SystemOverview | null>(null);
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [deviceOps, setDeviceOps] = useState<DeviceOpsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTool, setActiveTool] = useState<AiToolStatus | null>(null);
  const [upgradingTool, setUpgradingTool] = useState("");
  const [upgradeResult, setUpgradeResult] = useState("");
  const [activeService, setActiveService] = useState<ServiceRow | null>(null);
  const [opsResult, setOpsResult] = useState<DeviceOpsPreview | null>(null);
  const [opsBusy, setOpsBusy] = useState("");
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [ssh, setSsh] = useState({ name: "", host: "", user: "" });
  const [sshBusy, setSshBusy] = useState(false);
  const [sshError, setSshError] = useState("");
  const [devTools, setDevTools] = useState<DevToolchain | null>(null);
  const [deviceOpsRefreshing, setDeviceOpsRefreshing] = useState(false);
  const lastProbe = useRef(0);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [overview, serviceRows, deviceRows] = await Promise.all([getSystemOverview(), getServices(), getDevices()]);
      setData(overview);
      setServices(serviceRows);
      setDevices(deviceRows);
      getDevTools().then(setDevTools).catch(() => {});
      refreshDeviceOps(false);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
    // 远端 SSH 探测是慢操作（逐台连接），放到首屏渲染之后后台执行，
    // 完成后只静默刷新设备列表，避免“点击后很久才刷新出页面”。
    if (Date.now() - lastProbe.current > 45000) {
      lastProbe.current = Date.now();
      sendSelfHeartbeat().catch(() => {});
      probeSshDevices()
        .then(() => {
          getDevices().then(setDevices).catch(() => {});
          refreshDeviceOps(false);
        })
        .catch(() => {});
    }
  };

  useEffect(() => {
    load();
    const t = window.setInterval(load, 10000);
    return () => window.clearInterval(t);
  }, []);

  const serviceHealth = useMemo(() => {
    if (!services.length) return 0;
    return Math.round((services.filter((s) => s.online).length / services.length) * 100);
  }, [services]);

  const onlineDevices = useMemo(() => devices.filter((d) => d.online).length, [devices]);

  async function doUpgradeTool(tool: AiToolStatus) {
    if (!tool.can_upgrade) return;
    setUpgradingTool(tool.id);
    setUpgradeResult("");
    try {
      const res = await upgradeAiTool(tool.id);
      setUpgradeResult(`${res.ok ? "升级完成" : "升级失败"}：${res.command || tool.upgrade_command || ""}\n${res.output || res.error || ""}`);
      await load();
    } catch (err) {
      setUpgradeResult(String(err));
    } finally {
      setUpgradingTool("");
    }
  }

  async function addRemote() {
    if (!ssh.host.trim()) return;
    setSshBusy(true);
    setSshError("");
    try {
      await addSshDevice({ ...ssh, port: 22, enabled: true });
      await probeSshDevices();
      setSsh({ name: "", host: "", user: "" });
      setShowAddDevice(false);
      await load();
    } catch (err) {
      setSshError(String(err));
    } finally {
      setSshBusy(false);
    }
  }

  async function refreshDevices() {
    setSshBusy(true);
    try {
      await sendSelfHeartbeat();
      await probeSshDevices();
      setDevices(await getDevices());
      await refreshDeviceOps(true);
    } catch (err) {
      setError(String(err));
    } finally {
      setSshBusy(false);
    }
  }

  async function refreshDeviceOps(force = false) {
    setDeviceOpsRefreshing(true);
    try {
      setDeviceOps(await getDeviceOpsStatus(force));
    } catch (err) {
      if (force) setError(String(err));
    } finally {
      setDeviceOpsRefreshing(false);
    }
  }

  async function runOpsPreview(target: DeviceOpsTarget, action: string) {
    setOpsBusy(`${target.target_id}:${action}`);
    setOpsResult(null);
    try {
      setOpsResult(await previewDeviceOps(action, target.target_id));
    } catch (err) {
      setOpsResult({ ok: false, target_id: target.target_id, action, safe_mode: true, error: String(err) });
    } finally {
      setOpsBusy("");
    }
  }

  if (error && !data) return <div className="error">{error}</div>;

  const scoreTone = data ? (data.score >= 85 ? "good" : data.score >= 65 ? "warn" : "bad") : "good";
  const opsMeta = deviceOps
    ? `${deviceOps.summary.ready}/${deviceOps.summary.targets} 就绪${deviceOps.cache?.refreshing ? " · 更新中" : deviceOps.cache?.stale ? " · 缓存" : ""}`
    : deviceOpsRefreshing ? "检测中" : "待检测";

  return (
    <div className="system-view">
      <div className="page-head">
        <div>
          <div className="kicker">SystemGuard</div>
          <h1>系统与设备</h1>
          <p>先看本机资源与服务，再看所有 Mac 的健康卡。远端设备通过 SSH 只读采集健康摘要。</p>
        </div>
        <button className="btn primary" onClick={load} disabled={loading}>{loading ? "刷新中" : "立即刷新"}</button>
      </div>

      {!data ? <PageSkeleton head={false} cards={4} /> : (
        <>
          <section className={`sys-hero card ${scoreTone}`}>
            <div className="sys-hero-score">
              <div className="sys-hero-ring">
                <Ring pct={data.score} tone={scoreTone} size={84} />
                <b>{data.score}</b>
              </div>
              <div>
                <span className="sys-hero-label">整体健康度</span>
                <p>服务可用率 {serviceHealth}% · 设备在线 {onlineDevices}/{devices.length || 1} · 更新 {fmtTime(data.generated_at)}</p>
              </div>
            </div>
            <div className="sys-hero-risks">
              {data.risks.length === 0 ? <span className="risk-chip good"><b>健康</b>系统状态整体正常，继续保持。</span> :
                data.risks.slice(0, 3).map((risk) => (
                  <span className={`risk-chip ${levelClass(risk.level)}`} key={`${risk.title}-${risk.advice}`} title={risk.advice}>
                    <b>{risk.level}</b>{risk.title} · {risk.advice}
                  </span>
                ))}
            </div>
          </section>

          <div className="sys-metric-grid">
            {data.modules.map((module, index) => <MetricCard module={module} index={index} key={module.id} />)}
          </div>

          <SectionHead
            title="设备健康"
            desc="每台 Mac 只上报健康摘要，不读取文件内容。"
            meta={`${onlineDevices}/${devices.length} 在线`}
          >
            <button className="btn sm ghost" onClick={refreshDevices} disabled={sshBusy}>{sshBusy ? "探测中" : "重新探测"}</button>
            <button className="btn sm primary" onClick={() => setShowAddDevice(true)}>添加设备</button>
          </SectionHead>
          <div className="device-grid compact">
            {devices.map((device) => <DeviceCard device={device} key={device.device_id} />)}
            {devices.length === 0 ? <div className="empty">暂无设备心跳。</div> : null}
          </div>

          <SectionHead
            title="本地服务"
            desc="配置服务 + 自动发现的本机监听服务。点击查看详情。"
            meta={`${services.filter((s) => s.online).length}/${services.length} 在线`}
          />
          <div className="sys-service-grid">
            {services.length === 0 ? <div className="empty">暂无本地服务配置。</div> :
              services.map((s) => (
                <button className={`sys-service ${s.online ? "good" : "bad"}`} onClick={() => setActiveService(s)} key={`${s.name}:${s.port}`}>
                  <span className="dot" />
                  <div>
                    <b>{s.name}</b>
                    <small>{s.desc || "本地服务"} · :{s.port}</small>
                  </div>
                  <em>{s.online ? "在线" : "离线"}</em>
                </button>
              ))}
          </div>

          <SectionHead
            title="AI 开发工具"
            desc="常用 AI CLI 的安装、运行与版本状态，点击可一键升级。"
            meta={data.ai_tools.length ? `${data.ai_tools.filter((t) => t.installed).length}/${data.ai_tools.length} 已安装` : undefined}
          />
          <div className="sys-tool-grid">
            {data.ai_tools.map((tool) => (
              <button className={`sys-tool ${tool.installed ? "installed" : "missing"}`} onClick={() => setActiveTool(tool)} key={tool.id}>
                <span className="dot" />
                <div className="sys-tool-main">
                  <b>{tool.name}</b>
                  <em>{tool.installed ? (tool.running ? "运行中" : "已安装") : "未安装"}</em>
                </div>
                <div className="sys-tool-meta">
                  <span>{shortVersion(tool.current_version)}</span>
                  <span>{tool.update_state}</span>
                </div>
              </button>
            ))}
          </div>

          <SectionHead
            title="编程 / CLI 工具链"
            meta={devTools ? `${devTools.summary.installed}/${devTools.summary.total} 已安装` : "检测中"}
          />
          {!devTools ? <div className="empty">检测中…</div> : (
            <div className="devtool-cats">
              {Object.entries(devTools.categories).map(([cat, tools]) => (
                <section className="card devtool-cat" key={cat}>
                  <div className="devtool-cat-title">{cat}</div>
                  <div className="devtool-list">
                    {tools.map((t) => (
                      <div className={`devtool-row ${t.installed ? "on" : "off"}`} key={t.id} title={t.path || "未检测到"}>
                        <span className={`dot ${t.installed ? "good" : "bad"}`} />
                        <b>{t.name}</b>
                        <em>{t.installed ? t.version : "未安装"}</em>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}

          <div className="sys-bottom-grid">
            <section className="card sys-bottom-panel">
              <SectionHead
                title="设备管家"
                desc="Burrow/Mole 能力：清理、优化、扫描全部先走安全预览，不直接执行删除。"
                meta={opsMeta}
              >
                <button className="btn sm ghost" onClick={() => refreshDeviceOps(true)} disabled={deviceOpsRefreshing}>
                  {deviceOpsRefreshing ? "刷新中" : "刷新管家"}
                </button>
              </SectionHead>
              <div className="ops-grid">
                {(deviceOps?.targets || []).map((target) => (
                  <DeviceOpsCard target={target} onPreview={runOpsPreview} busy={opsBusy} key={target.target_id} />
                ))}
              </div>
              {opsResult ? (
                <div className={`ops-result ${opsResult.ok ? "ok" : "bad"}`}>
                  <div>
                    <b>{opsResult.action} · {opsResult.ok ? "预览完成" : "预览失败"}</b>
                    <span>{opsResult.command || opsResult.install_hint || opsResult.error}</span>
                  </div>
                  {opsResult.summary?.estimated_gb ? <strong>约 {opsResult.summary.estimated_gb} GB</strong> : null}
                  <pre>{opsResult.summary?.highlights?.join("\n") || opsResult.summary?.raw || opsResult.error || "暂无输出"}</pre>
                </div>
              ) : null}
            </section>

            <section className="card sys-bottom-panel">
              <SectionHead title="资源占用排行" desc="按 CPU 排序的高占用进程。" />
              <div className="process-list">
                {data.processes.map((proc) => (
                  <div className="process-row" key={`${proc.pid}-${proc.command}`}>
                    <b>{proc.command}</b>
                    <span>PID {proc.pid}</span>
                    <em>CPU {proc.cpu.toFixed(1)}% · 内存 {proc.memory.toFixed(1)}%</em>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <details className="raw-details raw-compact">
            <summary>高级详情：查看原始命令输出</summary>
            <pre className="toolResult">{data.raw || "暂无原始输出"}</pre>
          </details>
        </>
      )}

      <Modal open={showAddDevice} onClose={() => { setShowAddDevice(false); setSshError(""); }} kicker="SSH 设备" title="添加远程机器"
        footer={<button className="btn sm primary" onClick={addRemote} disabled={sshBusy || !ssh.host.trim()}>{sshBusy ? "连接中…" : "添加并探测"}</button>}>
        <div className="modal-form">
          <p className="modal-note">先在目标机授权本机 SSH 公钥（ssh-copy-id user@host），LeoJarvis 只读取 CPU、内存、磁盘和服务摘要，不读文件内容。</p>
          <label><span>名称</span><input placeholder="例如 Mac Studio" value={ssh.name} onChange={(e) => setSsh({ ...ssh, name: e.target.value })} /></label>
          <label><span>Host / IP</span><input placeholder="192.168.1.10 或 Tailscale IP" value={ssh.host} onChange={(e) => setSsh({ ...ssh, host: e.target.value })} /></label>
          <label><span>用户名</span><input placeholder="user" value={ssh.user} onChange={(e) => setSsh({ ...ssh, user: e.target.value })} /></label>
          {sshError ? <div className="error">{sshError}</div> : null}
        </div>
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
            <p className="modal-note">{activeTool.advice} · 检测 {fmtTime(activeTool.checked_at)}</p>
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
            <div><span>来源</span><b>{activeService.source || "配置"}</b></div>
            {activeService.process ? <div><span>进程</span><b>{activeService.process}</b></div> : null}
            {activeService.cwd ? <div><span>工作目录</span><b>{activeService.cwd}</b></div> : null}
            {activeService.address ? <div><span>监听地址</span><b>{activeService.address}</b></div> : null}
            <p className="modal-note">{activeService.desc || "本地服务"}</p>
            {activeService.command ? <p className="modal-note">{activeService.command}</p> : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
