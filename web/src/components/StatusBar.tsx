import { useEffect, useState } from "react";
import { getCockpitOverview, type CockpitOverview } from "../api";

// 常驻在所有页面最上方的系统状态横条：小字、实时、低打扰。
function tone(ok: boolean, warn: boolean) {
  return ok ? "good" : warn ? "warn" : "bad";
}

export function StatusBar() {
  const [data, setData] = useState<CockpitOverview | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getCockpitOverview()
        .then((d) => { if (alive) { setData(d); setErr(false); } })
        .catch(() => { if (alive) setErr(true); });
    load();
    const t = window.setInterval(load, 15000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);

  if (err && !data) {
    return (
      <div className="status-bar">
        <span className="sb-dot bad" />
        <span className="sb-item">后端未连接</span>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="status-bar">
        <span className="sb-dot" />
        <span className="sb-item sb-muted">连接中…</span>
      </div>
    );
  }

  const { health } = data;
  const disk = health.system.disk_pct;
  const load = health.system.load;
  const online = health.services_online;
  const total = health.services_total;
  const weather = data.weather;
  const updated = new Date(data.generated_at * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="status-bar">
      <span className={`sb-dot ${tone(health.score >= 80, health.score >= 60)}`} />
      <span className="sb-item"><b>健康 {health.score}</b></span>
      <span className="sb-sep" />
      <span className="sb-item">磁盘 <em className={tone((disk ?? 0) < 75, (disk ?? 0) < 90)}>{disk ?? "—"}%</em></span>
      <span className="sb-item">负载 <em className={tone((load ?? 0) < 4, (load ?? 0) < 8)}>{load?.toFixed(2) ?? "—"}</em></span>
      <span className="sb-item">服务 <em className={tone(online >= total, online > 0)}>{online}/{total}</em></span>
      {weather && weather.ok ? (
        <>
          <span className="sb-sep" />
          <span className="sb-item sb-weather" title={`体感 ${weather.feels_like}° · 风 ${weather.wind}km/h · ${weather.high}°/${weather.low}°`}>
            <b>{weather.city}</b> {weather.text} <em>{weather.temperature}°</em>
          </span>
          <span className="sb-item sb-muted">湿度 {weather.humidity}%</span>
        </>
      ) : null}
      <span className="sb-grow" />
      <span className="sb-item sb-muted">情报 {data.intelligence.events}</span>
      <span className="sb-item sb-muted">简报 {data.briefing.business + data.briefing.life}</span>
      <span className="sb-item sb-muted">待确认记忆 {data.memory.pending + data.memory.later}</span>
      <span className="sb-sep" />
      <span className="sb-item sb-muted">更新 {updated}</span>
    </div>
  );
}
