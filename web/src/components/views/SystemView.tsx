import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  getServices,
  getSystemOverview,
  upgradeAiTool,
  type AiToolStatus,
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
  disk: "M4 6h16v4H4zM4 14h16v4H4z",          // 抽象图标，纯描边
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

// 扁平进度环：纯 SVG 描边，无渐变。
function Ring({ pct, tone }: { pct: number; tone: string }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(100, pct)) / 100);
  return (
    <svg className={`sys-ring tone-${tone}`} viewBox="0 0 64 64" width="56" height="56">
      <circle cx="32" cy="32" r={r} className="ring-track" />
      <circle cx="32" cy="32" r={r} className="ring-bar" strokeDasharray={c} strokeDashoffset={off} transform="rotate(-90 32 32)" />
    </svg>
  );
}

function ModuleCard({ module, index }: { module: SystemModule; index: number }) {
  const tone = levelClass(module.level);
  return (
    <motion.article
      className={`sys-module ${tone}`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      <div className="sys-module-ring">
        <Ring pct={moduleProgress(module)} tone={tone} />
        <svg className="sys-module-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path d={MODULE_ICON[module.id] || "M4 4h16v16H4z"} />
        </svg>
      </div>
      <div className="sys-module-body">
        <div className="sys-module-top">
          <span>{module.name}</span>
          <em className={`sys-tag ${tone}`}>{module.level}</em>
        </div>
        <b>{module.value}</b>
        <p>{module.summary}</p>
        <small>{module.advice}</small>
      </div>
    </motion.article>
  );
}

function ServiceTile({ service, onOpen }: { service: ServiceRow; onOpen: (s: ServiceRow) => void }) {
  return (
    <button className={`sys-service ${service.online ? "good" : "bad"}`} onClick={() => onOpen(service)}>
      <span className="dot" />
      <div>
        <b>{service.name}</b>
        <small>{service.desc || "本地服务"} · :{service.port}</small>
      </div>
      <em>{service.online ? "在线" : "离线"}</em>
    </button>
  );
}

function ToolCard({ tool, onOpen }: { tool: AiToolStatus; onOpen: (t: AiToolStatus) => void }) {
  return (
    <button className={`sys-tool ${tool.installed ? "installed" : "missing"}`} onClick={() => onOpen(tool)}>
      <span className="dot" />
      <div className="sys-tool-main">
        <b>{tool.name}</b>
        <em>{tool.installed ? (tool.running ? "运行中" : "已安装") : "未安装"}</em>
      </div>
      <div className="sys-tool-meta">
        <span>v{tool.current_version === "未安装" ? "—" : tool.current_version}</span>
        <span>{tool.update_state}</span>
      </div>
    </button>
  );
}

export function SystemView() {
  const [data, setData] = useState<SystemOverview | null>(null);
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTool, setActiveTool] = useState<AiToolStatus | null>(null);
  const [upgradingTool, setUpgradingTool] = useState("");
  const [upgradeResult, setUpgradeResult] = useState("");
  const [activeService, setActiveService] = useState<ServiceRow | null>(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [overview, serviceRows] = await Promise.all([getSystemOverview(), getServices()]);
      setData(overview);
      setServices(serviceRows);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
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

  if (error && !data) return <div className="error">{error}</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="kicker">SystemGuard</div>
          <h1>系统状态</h1>
          <p>按磁盘、CPU、内存、网络、本地服务和 AI 开发工具拆开展示。默认只给判断和建议，原始命令输出收进高级详情。</p>
          {data ? (
            <div className="risk-strip-inline">
              {data.risks.slice(0, 4).map((risk) => (
                <span className={levelClass(risk.level)} key={`${risk.title}-${risk.advice}`}>
                  <b>{risk.level}</b>{risk.title} · {risk.advice}
                </span>
              ))}
            </div>
          ) : null}
        </div>
        <button className="btn primary" onClick={load} disabled={loading}>{loading ? "刷新中" : "立即刷新"}</button>
      </div>

      {!data ? <PageSkeleton head={false} cards={4} /> : (
        <>
          <div className="sys-modules">
            <article className="sys-score">
              <span>整体健康度</span>
              <b>{data.score}</b>
              <small>服务可用率 {serviceHealth}% · 更新 {fmtTime(data.generated_at)}</small>
            </article>
            {data.modules.map((module, index) => <ModuleCard module={module} index={index} key={module.id} />)}
          </div>

          <div className="panel-title" style={{ marginTop: 24 }}>本地服务状态</div>
          <div className="sys-service-grid">
            {services.length === 0 ? <div className="empty">暂无本地服务配置。</div> :
              services.map((s) => <ServiceTile service={s} onOpen={setActiveService} key={s.name} />)}
          </div>

          <div className="panel-title" style={{ marginTop: 24 }}>本地 AI 开发工具</div>
          <div className="sys-tool-grid">
            {data.ai_tools.map((tool) => <ToolCard tool={tool} onOpen={setActiveTool} key={tool.id} />)}
          </div>

          <div className="intel-grid-2" style={{ marginTop: 24 }}>
            <section className="card">
              <div className="panel-title">资源占用排行</div>
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
            <section className="card">
              <div className="panel-title">高级详情</div>
              <details className="raw-details">
                <summary>查看原始命令输出</summary>
                <pre className="toolResult">{data.raw || "暂无原始输出"}</pre>
              </details>
            </section>
          </div>
        </>
      )}

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
            <p className="modal-note">{activeService.desc || "本地服务"}</p>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
