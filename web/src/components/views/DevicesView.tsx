import { useEffect, useMemo, useState } from "react";
import { getDevices, sendSelfHeartbeat, type DeviceSummary } from "../../api";
import { PageSkeleton } from "../Skeleton";

function pct(value?: number | null) {
  return value == null ? "—" : `${Math.round(value)}%`;
}

function ageLabel(seconds?: number) {
  if (seconds == null) return "刚刚";
  if (seconds < 60) return `${seconds}s 前`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m 前`;
  return `${Math.round(seconds / 3600)}h 前`;
}

function tone(device: DeviceSummary) {
  if (!device.online) return "offline";
  if (device.status === "异常" || device.health < 65) return "bad";
  if (device.status === "注意" || device.health < 82) return "warn";
  return "good";
}

function metricRows(device: DeviceSummary) {
  return [
    ["CPU", pct(device.metrics.cpu_load_pct), device.metrics.cpu_load != null ? `${device.metrics.cpu_load} / ${device.metrics.cpu_cores || "?"} 核` : "负载"],
    ["RAM", pct(device.metrics.ram_used_pct), device.metrics.ram_total_gb ? `${device.metrics.ram_used_gb ?? "—"}G / ${device.metrics.ram_total_gb}G` : "内存"],
    ["SSD", pct(device.metrics.ssd_used_pct), device.metrics.ssd_free_gb != null ? `剩余 ${device.metrics.ssd_free_gb}G` : "磁盘"],
    ["温控", device.modules?.thermal?.value || "正常", device.modules?.thermal?.level || "健康"],
    ["电源", device.metrics.battery_percent != null ? `${device.metrics.battery_percent}%` : "—", device.metrics.battery_plugged ? "外接" : "电池"],
    ["服务", `${device.services.online}/${device.services.total}`, "在线"],
  ];
}

function DeviceCard({ device, hero = false }: { device: DeviceSummary; hero?: boolean }) {
  const t = tone(device);
  return (
    <article className={`device-card ${hero ? "hero" : ""} ${t}`}>
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
        {metricRows(device).map(([label, value, hint]) => (
          <div key={label}>
            <span>{label}</span>
            <b>{value}</b>
            <em>{hint}</em>
          </div>
        ))}
      </div>
      <div className="device-risks">
        {(device.risks || []).slice(0, hero ? 4 : 2).map((risk) => (
          <span className={risk.level === "异常" ? "bad" : risk.level === "注意" ? "warn" : "good"} key={`${risk.title}-${risk.advice}`}>
            <b>{risk.level}</b>{risk.title}
          </span>
        ))}
        {(device.risks || []).length === 0 ? <span className="good"><b>健康</b>暂无风险项</span> : null}
      </div>
      <div className="device-foot">
        <span>{device.online ? "在线" : "离线"}</span>
        <span>心跳 {ageLabel(device.age_seconds)}</span>
      </div>
    </article>
  );
}

export function DevicesView() {
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setError("");
    try {
      const rows = await getDevices();
      setDevices(rows);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function heartbeat() {
    setBusy(true);
    try {
      await sendSelfHeartbeat();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 15000);
    return () => window.clearInterval(t);
  }, []);

  const sorted = useMemo(() => [...devices].sort((a, b) => Number(b.online) - Number(a.online) || b.health - a.health), [devices]);
  const local = sorted[0];
  const rest = sorted.slice(1);

  if (loading && devices.length === 0) return <PageSkeleton cards={4} />;

  return (
    <div className="devices-view">
      <div className="page-head devices-head">
        <div>
          <div className="kicker">LeoJarvis Fleet</div>
          <h1>设备健康</h1>
          <p>每台 Mac 只上报健康摘要：CPU、RAM、SSD、温控、电源、网络、服务在线率和风险项。不上传原始命令输出、进程命令行或通知内容。</p>
        </div>
        <div className="head-actions">
          <button className="btn ghost" onClick={refresh}>刷新</button>
          <button className="btn primary" onClick={heartbeat} disabled={busy}>{busy ? "上报中" : "本机心跳"}</button>
        </div>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}

      {local ? <DeviceCard device={local} hero /> : <div className="empty">暂无设备心跳。点击“本机心跳”写入当前 Mac。</div>}

      <div className="device-section-title">
        <h2>所有设备</h2>
        <span>{sorted.filter((d) => d.online).length}/{sorted.length} 在线</span>
      </div>
      <div className="device-grid">
        {(rest.length ? rest : sorted.slice(local ? 1 : 0)).map((device) => <DeviceCard device={device} key={device.device_id} />)}
        {rest.length === 0 && sorted.length <= 1 ? <div className="empty">还没有其他 Mac 上报。把其它机器的 LeoJarvis 指向这个 Hub 后会显示在这里。</div> : null}
      </div>
    </div>
  );
}
