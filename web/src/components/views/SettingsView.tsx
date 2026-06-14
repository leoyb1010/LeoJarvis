import { useEffect, useState } from "react";
import {
  addRemoteLeoJarvis,
  connectRemoteLeoJarvis,
  disconnectRemoteLeoJarvis,
  getSettings,
  getSettingsDiagnostics,
  getTuning,
  importOpml,
  listRemoteLeoJarvis,
  patchSettings,
  probeSshDevices,
  removeSshDevice,
  type LeoJarvisSettings,
  type RemoteLeoJarvisConnection,
  type RssSource,
  type Tuning,
} from "../../api";
import { PageSkeleton } from "../Skeleton";

const APP_LABELS: Record<string, string> = {
  wechat: "微信",
  popo: "POPO",
  telegram: "Telegram",
  mailmaster: "网易邮箱大师",
  mail: "本机邮件",
  gmail: "Gmail",
};

const DEFAULT_SETTINGS: LeoJarvisSettings = {
  notifications: { enabled: true, apps: { wechat: true, popo: true, telegram: true, mailmaster: true, mail: true, gmail: true } },
  system: { show_status_bar: true, show_raw_details: false, refresh_seconds: 15 },
  email: { enabled: false, accounts: [], apple_mail_fallback: true, apple_mail_limit: 20, apple_mail_unread_only: false },
  gmail: { enabled: false, user: "", app_password: "", host: "imap.gmail.com", port: 993, mailbox: "INBOX" },
  rss: { sources: [] },
  x_monitor: {
    enabled: true,
    rsshub_base: "https://rsshub.app",
    include_default_ai_tech: true,
    limit: 6,
    users: [
      "OpenAI",
      "AnthropicAI",
      "GoogleDeepMind",
      "xai",
      "deepseek_ai",
      "nvidia",
      "huggingface",
      "cursor_ai",
      "vercel",
      "togethercompute",
      "sama",
      "karpathy",
    ],
  },
  remote_devices: [],
  remote_cortex: [],
  overrides: {},
};

function normalizeSettings(input: Partial<LeoJarvisSettings> | null | undefined): LeoJarvisSettings {
  return {
    ...DEFAULT_SETTINGS,
    ...(input || {}),
    notifications: { ...DEFAULT_SETTINGS.notifications, ...(input?.notifications || {}), apps: { ...DEFAULT_SETTINGS.notifications.apps, ...(input?.notifications?.apps || {}) } },
    system: { ...DEFAULT_SETTINGS.system, ...(input?.system || {}) },
    email: { ...DEFAULT_SETTINGS.email, ...(input?.email || {}), accounts: input?.email?.accounts || [] },
    gmail: { ...DEFAULT_SETTINGS.gmail, ...(input?.gmail || {}) },
    rss: { ...DEFAULT_SETTINGS.rss, ...(input?.rss || {}), sources: input?.rss?.sources || [] },
    x_monitor: { ...DEFAULT_SETTINGS.x_monitor, ...(input?.x_monitor || {}), users: input?.x_monitor?.users || DEFAULT_SETTINGS.x_monitor.users },
    remote_devices: input?.remote_devices || [],
    remote_cortex: input?.remote_cortex || [],
    overrides: input?.overrides || {},
  };
}

function splitLines(value: string) {
  return value.split(/[\n,，]+/).map((x) => x.trim()).filter(Boolean);
}

export function SettingsView() {
  const [settings, setSettings] = useState<LeoJarvisSettings | null>(null);
  const [diag, setDiag] = useState<any>(null);
  const [tuning, setTuning] = useState<Tuning | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [emailDraft, setEmailDraft] = useState({ name: "", host: "", user: "", password: "", port: 993 });
  const [gmailDraft, setGmailDraft] = useState({ user: "", app_password: "" });
  const [rssDraft, setRssDraft] = useState<{ name: string; url: string; category: string }>({ name: "", url: "", category: "自定义" });
  const [opmlText, setOpmlText] = useState("");
  const [xUsers, setXUsers] = useState("");
  const [sshDraft, setSshDraft] = useState({ name: "", host: "", user: "", port: 22, proxy_command: "" });
  const [remoteDraft, setRemoteDraft] = useState({ name: "", host: "", user: "", ssh_port: 22, remote_port: 8787, proxy_command: "" });
  const [remoteLeoJarvis, setRemoteLeoJarvis] = useState<RemoteLeoJarvisConnection[]>([]);
  const [remoteBusy, setRemoteBusy] = useState("");

  async function load() {
    setError("");
    try {
      const res = normalizeSettings(await getSettings());
      setSettings(res);
      setXUsers((res.x_monitor?.users || []).join("\n"));
      setGmailDraft({ user: res.gmail?.user || "", app_password: "" });
      getSettingsDiagnostics().then(setDiag).catch((err) => setDiag({ error: String(err) }));
      getTuning().then(setTuning).catch(() => {});
      listRemoteLeoJarvis().then(setRemoteLeoJarvis).catch(() => {});
    } catch (err) {
      setError(String(err));
      setSettings((prev) => prev || DEFAULT_SETTINGS);
    }
  }

  useEffect(() => { load(); }, []);

  // 远程连接状态会被后台维护任务自动修复，设置页轮询保持显示同步。
  useEffect(() => {
    const t = window.setInterval(() => {
      listRemoteLeoJarvis().then(setRemoteLeoJarvis).catch(() => {});
    }, 10000);
    return () => window.clearInterval(t);
  }, []);

  async function save(next: Partial<LeoJarvisSettings>) {
    setSaving(true);
    setError("");
    try {
      const res = normalizeSettings(await patchSettings(next));
      setSettings(res);
      getSettingsDiagnostics().then(setDiag).catch((err) => setDiag({ error: String(err) }));
      listRemoteLeoJarvis().then(setRemoteLeoJarvis).catch(() => {});
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  async function saveOverride(section: string, patch: Record<string, any>) {
    const overrides = { ...(settings?.overrides || {}) };
    overrides[section] = { ...(overrides[section] || {}), ...patch };
    await save({ overrides });
    getTuning().then(setTuning).catch(() => {});
    setNotice("已保存。改动定时任务节奏需重启后端生效。");
    window.setTimeout(() => setNotice(""), 4000);
  }

  if (!settings) return <PageSkeleton cards={5} />;

  const emailAccounts = settings.email?.accounts || [];
  const rssSources = settings.rss?.sources || [];
  const remotes = settings.remote_devices || [];
  const tv = (s: keyof Tuning, k: string, d: number) => Number((tuning?.[s] as any)?.[k] ?? d);

  function setRss(sources: RssSource[]) { save({ rss: { sources } }); }

  async function addRemoteProduct() {
    if (!remoteDraft.host.trim()) return;
    setRemoteBusy("add");
    try {
      const res = await addRemoteLeoJarvis(remoteDraft);
      const connected = await connectRemoteLeoJarvis(res.connection.id);
      setRemoteDraft({ name: "", host: "", user: "", ssh_port: 22, remote_port: 8787, proxy_command: "" });
      setRemoteLeoJarvis(await listRemoteLeoJarvis());
      if (!connected.ok) setError(connected.error || "SSH tunnel 连接失败，请确认目标机 SSH 授权和 LeoJarvis 已运行。");
    } catch (err) {
      setError(String(err));
    } finally {
      setRemoteBusy("");
    }
  }

  async function toggleRemote(row: RemoteLeoJarvisConnection) {
    setRemoteBusy(row.id);
    setError("");
    try {
      if (row.connected) await disconnectRemoteLeoJarvis(row.id);
      else {
        const res = await connectRemoteLeoJarvis(row.id);
        if (!res.ok) setError(res.error || "连接失败");
      }
      setRemoteLeoJarvis(await listRemoteLeoJarvis());
    } finally {
      setRemoteBusy("");
    }
  }

  return (
    <div className="settings-view">
      <div className="page-head settings-head">
        <div>
          <div className="kicker">Preferences</div>
          <h1>设置</h1>
          <p>邮件账户、Gmail、应用通知、RSS / OPML、X 监控、阈值与节奏、SSH 设备与远程 LeoJarvis，全部可在这里自定义。保存后后端立即按新配置读取（定时任务节奏需重启生效）。</p>
        </div>
        <button className="btn ghost" onClick={load}>重新诊断</button>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}
      {notice ? <div className="diag-box" style={{ marginBottom: 16 }}>{notice}</div> : null}

      <div className="settings-grid">
        {/* 本机邮件 / IMAP */}
        <section className="card settings-card">
          <div className="panel-title">本机邮件（Apple Mail / IMAP）</div>
          <p className="settings-note">本机邮件未读数直接读取 Apple Mail 本地未读（read=0，已排除垃圾箱/已发送），与「邮件」App 角标一致。Gmail 单独配置在下一张卡。</p>
          <label className="switch-row">
            <span>启用主动 IMAP 拉取</span>
            <input type="checkbox" checked={!!settings.email.enabled} onChange={(e) => save({ email: { ...settings.email, enabled: e.target.checked } })} />
          </label>
          <label className="switch-row">
            <span>读取 Apple Mail 本地邮箱</span>
            <input type="checkbox" checked={settings.email.apple_mail_fallback !== false} onChange={(e) => save({ email: { ...settings.email, apple_mail_fallback: e.target.checked } })} />
          </label>
          <label className="switch-row">
            <span>仅统计未读</span>
            <input type="checkbox" checked={!!settings.email.apple_mail_unread_only} onChange={(e) => save({ email: { ...settings.email, apple_mail_unread_only: e.target.checked } })} />
          </label>
          <div className="settings-list">
            {emailAccounts.map((a, i) => <div className="settings-row" key={`${a.user}-${i}`}><b>{a.name || a.user}</b><span>{a.user} · {a.host}:{a.port || 993}</span><button className="btn sm ghost" onClick={() => save({ email: { ...settings.email, accounts: emailAccounts.filter((_, j) => j !== i) } })}>删除</button></div>)}
            {emailAccounts.length === 0 ? <div className="empty">还没有保存到 LeoJarvis 的 IMAP 邮箱账户。</div> : null}
          </div>
          <div className="settings-form email-form">
            <input placeholder="名称" value={emailDraft.name} onChange={(e) => setEmailDraft({ ...emailDraft, name: e.target.value })} />
            <input placeholder="IMAP Host" value={emailDraft.host} onChange={(e) => setEmailDraft({ ...emailDraft, host: e.target.value })} />
            <input placeholder="邮箱账号" value={emailDraft.user} onChange={(e) => setEmailDraft({ ...emailDraft, user: e.target.value })} />
            <input placeholder="授权码 / App Password" type="password" value={emailDraft.password} onChange={(e) => setEmailDraft({ ...emailDraft, password: e.target.value })} />
            <button className="btn sm primary" disabled={!emailDraft.host || !emailDraft.user || !emailDraft.password || saving} onClick={() => {
              save({ email: { enabled: true, accounts: [...emailAccounts, { ...emailDraft, enabled: true, limit: 20 }] } });
              setEmailDraft({ name: "", host: "", user: "", password: "", port: 993 });
            }}>添加邮箱</button>
          </div>
          <div className="diag-box">当前采集器识别到账户：{diag?.email_accounts?.length || 0} · Apple Mail 样本：{diag?.apple_mail?.recent_count_sample ?? "未诊断"}</div>
        </section>

        {/* Gmail 独立账户 */}
        <section className="card settings-card">
          <div className="panel-title">Gmail（独立未读）</div>
          <p className="settings-note">Gmail 与本机邮件分开统计：通过 IMAP 只做 UNSEEN 未读计数（仅数字，不下载正文）。需在 Gmail 开启两步验证后生成「应用专用密码」。</p>
          <label className="switch-row">
            <span>启用 Gmail 未读</span>
            <input type="checkbox" checked={!!settings.gmail.enabled} onChange={(e) => save({ gmail: { ...settings.gmail, enabled: e.target.checked } })} />
          </label>
          <div className="settings-form email-form">
            <input placeholder="Gmail 地址" value={gmailDraft.user} onChange={(e) => setGmailDraft({ ...gmailDraft, user: e.target.value })} />
            <input placeholder="应用专用密码 App Password" type="password" value={gmailDraft.app_password} onChange={(e) => setGmailDraft({ ...gmailDraft, app_password: e.target.value })} />
            <button className="btn sm primary" disabled={!gmailDraft.user || !gmailDraft.app_password || saving} onClick={() => {
              save({ gmail: { ...settings.gmail, enabled: true, user: gmailDraft.user.trim(), app_password: gmailDraft.app_password.replace(/\s+/g, "") } });
              setGmailDraft({ user: gmailDraft.user, app_password: "" });
            }}>保存 Gmail</button>
          </div>
          <div className="diag-box">服务器：{settings.gmail.host || "imap.gmail.com"}:{settings.gmail.port || 993} · 状态：{settings.gmail.enabled ? (settings.gmail.user ? `已配置（${settings.gmail.user}）` : "已启用，待填账号") : "未启用"}</div>
        </section>

        {/* 应用通知 */}
        <section className="card settings-card">
          <div className="panel-title">应用通知读取</div>
          <label className="switch-row"><span>启用通知计数</span><input type="checkbox" checked={settings.notifications.enabled} onChange={(e) => save({ notifications: { ...settings.notifications, enabled: e.target.checked } })} /></label>
          <div className="toggle-grid">
            {Object.entries(APP_LABELS).map(([id, label]) => (
              <label key={id} className="toggle-pill"><input type="checkbox" checked={settings.notifications.apps?.[id] !== false} onChange={(e) => save({ notifications: { ...settings.notifications, apps: { ...settings.notifications.apps, [id]: e.target.checked } } })} />{label}</label>
            ))}
          </div>
          <div className="diag-box">通知数据库：{diag?.notifications?.database_state || "未诊断"}</div>
        </section>

        {/* RSS 源管理 + OPML 导入 */}
        <section className="card settings-card settings-wide">
          <div className="panel-title">RSS 资讯源（{rssSources.length} 个自定义 + 精选基线）</div>
          <p className="settings-note">精选基线源在 <code>config/sources.toml</code>。这里新增的源会与基线合并、按 URL 去重。可一键导入 OPML（如 Karpathy 92 博客、BestBlogs 375 公众号）。</p>
          <div className="settings-list rss-list">
            {rssSources.map((s, i) => (
              <div className="settings-row" key={`${s.url}-${i}`}>
                <label className="toggle-pill compact"><input type="checkbox" checked={s.enabled !== false} onChange={(e) => { const next = [...rssSources]; next[i] = { ...s, enabled: e.target.checked }; setRss(next); }} /></label>
                <b>{s.name || s.url}</b>
                <span>{s.category || "—"} · {s.url}</span>
                <button className="btn sm ghost" onClick={() => setRss(rssSources.filter((_, j) => j !== i))}>删除</button>
              </div>
            ))}
            {rssSources.length === 0 ? <div className="empty">还没有自定义 RSS 源（基线源仍在工作）。</div> : null}
          </div>
          <div className="settings-form rss-add">
            <input placeholder="名称" value={rssDraft.name} onChange={(e) => setRssDraft({ ...rssDraft, name: e.target.value })} />
            <input placeholder="RSS / Atom URL" value={rssDraft.url} onChange={(e) => setRssDraft({ ...rssDraft, url: e.target.value })} />
            <input placeholder="分类" value={rssDraft.category} onChange={(e) => setRssDraft({ ...rssDraft, category: e.target.value })} />
            <button className="btn sm primary" disabled={!rssDraft.url.trim()} onClick={() => {
              setRss([...rssSources, { name: rssDraft.name || rssDraft.url, url: rssDraft.url.trim(), category: rssDraft.category || "自定义", domain: "business", limit: 10, enabled: true }]);
              setRssDraft({ name: "", url: "", category: "自定义" });
            }}>添加源</button>
          </div>
          <div className="settings-subtitle">OPML 导入</div>
          <textarea className="settings-textarea" value={opmlText} onChange={(e) => setOpmlText(e.target.value)} placeholder="粘贴 OPML 内容（<opml>…</opml>），保存后批量导入并去重。" />
          <button className="btn sm" disabled={!opmlText.trim() || saving} onClick={async () => {
            setError(""); setSaving(true);
            try {
              const r = await importOpml(opmlText);
              setOpmlText("");
              setNotice(`OPML 解析 ${r.parsed} 条，新增 ${r.added} 条，当前共 ${r.total} 个自定义源。`);
              window.setTimeout(() => setNotice(""), 5000);
              await load();
            } catch (err) { setError(String(err)); } finally { setSaving(false); }
          }}>导入 OPML</button>
        </section>

        {/* X 监控 */}
        <section className="card settings-card">
          <div className="panel-title">X / Twitter 监控</div>
          <p className="settings-note">每行一个：可填 <code>@handle</code>（走下方 RSSHub），或直接粘贴 rss.app 生成的 feed URL（更稳）。</p>
          <label className="switch-row"><span>启用 X 监控</span><input type="checkbox" checked={!!settings.x_monitor.enabled} onChange={(e) => save({ x_monitor: { ...settings.x_monitor, enabled: e.target.checked } })} /></label>
          <div className="settings-form two">
            <input placeholder="RSSHub 实例（自建更稳）" value={settings.x_monitor.rsshub_base} onChange={(e) => setSettings({ ...settings, x_monitor: { ...settings.x_monitor, rsshub_base: e.target.value } })} onBlur={(e) => save({ x_monitor: { ...settings.x_monitor, rsshub_base: e.target.value } })} />
          </div>
          <textarea className="settings-textarea" value={xUsers} onChange={(e) => setXUsers(e.target.value)} placeholder={"OpenAI\nAnthropicAI\nGoogleDeepMind\nxai\ndeepseek_ai\nnvidia\nhuggingface\ncursor_ai\nvercel\nhttps://rss.app/feeds/xxxx.xml"} />
          <button className="btn sm primary" onClick={() => save({ x_monitor: { ...settings.x_monitor, users: splitLines(xUsers), enabled: true } })}>保存 X 监控名单</button>
        </section>

        {/* 阈值 / 节奏 */}
        <section className="card settings-card settings-wide">
          <div className="panel-title">智能阈值与运行节奏</div>
          <p className="settings-note">覆盖 <code>config/settings.toml</code> 的默认值；留空即沿用默认。判断阈值即时生效，定时任务节奏改动需重启后端。</p>
          <div className="tuning-grid">
            <label><span>判断·忽略阈值</span><input type="number" step="0.05" min="0" max="1" defaultValue={tv("judge", "ignore_below", 0.35)} onBlur={(e) => saveOverride("judge", { ignore_below: Number(e.target.value) })} /></label>
            <label><span>判断·推送阈值</span><input type="number" step="0.05" min="0" max="1" defaultValue={tv("judge", "notify_above", 0.75)} onBlur={(e) => saveOverride("judge", { notify_above: Number(e.target.value) })} /></label>
            <label><span>采集间隔(分钟)</span><input type="number" min="1" defaultValue={tv("schedule", "ingest_minutes", 30)} onBlur={(e) => saveOverride("schedule", { ingest_minutes: Number(e.target.value) })} /></label>
            <label><span>情报扫描(分钟)</span><input type="number" min="1" defaultValue={tv("intelligence", "scan_minutes", 60)} onBlur={(e) => saveOverride("intelligence", { scan_minutes: Number(e.target.value) })} /></label>
            <label><span>守护巡检(分钟)</span><input type="number" min="1" defaultValue={tv("schedule", "guard_minutes", 5)} onBlur={(e) => saveOverride("schedule", { guard_minutes: Number(e.target.value) })} /></label>
            <label><span>简报时刻(时)</span><input type="number" min="0" max="23" defaultValue={tv("schedule", "briefing_hour", 8)} onBlur={(e) => saveOverride("schedule", { briefing_hour: Number(e.target.value) })} /></label>
            <label><span>磁盘告警(%)</span><input type="number" min="50" max="99" defaultValue={tv("guard", "disk_used_pct", 90)} onBlur={(e) => saveOverride("guard", { disk_used_pct: Number(e.target.value) })} /></label>
            <label><span>每核负载告警</span><input type="number" step="0.1" min="0.5" defaultValue={tv("guard", "load_per_core", 2.5)} onBlur={(e) => saveOverride("guard", { load_per_core: Number(e.target.value) })} /></label>
          </div>
        </section>

        {/* 远程 LeoJarvis */}
        <section className="card settings-card remote-product-card">
          <div className="panel-title">远程 LeoJarvis 实例（SSH 隧道）</div>
          <p className="settings-note">目标机器也部署 LeoJarvis 后，这里通过 SSH tunnel 连到远程 127.0.0.1:8787，主页驾驶舱可直接切换到那台机器的完整驾驶舱。需目标机已授权本机 SSH key。</p>
          <div className="settings-list">
            {remoteLeoJarvis.map((r) => {
              const verifiedAgo = r.last_health_ts ? Math.max(0, Math.round((Date.now() / 1000 - r.last_health_ts) / 60)) : null;
              return (
                <div className="settings-row remote-row" key={r.id}>
                  <span className={`conn-dot ${r.connected ? "good" : "bad"}`} />
                  <b>{r.name || r.host}</b>
                  <span>
                    {r.user ? `${r.user}@` : ""}{r.host}
                    {r.connected
                      ? ` · 已连接 127.0.0.1:${r.local_port}${verifiedAgo != null ? `（${verifiedAgo < 1 ? "刚刚" : `${verifiedAgo} 分钟前`}验证）` : ""}`
                      : ` · ${r.last_error || "未连接，等待后台重连"}`}
                  </span>
                  <button className="btn sm" disabled={remoteBusy === r.id} onClick={() => toggleRemote(r)}>{remoteBusy === r.id ? "处理中" : r.connected ? "断开" : "连接"}</button>
                </div>
              );
            })}
            {remoteLeoJarvis.length === 0 ? <div className="empty">暂无远程 LeoJarvis。先在目标机器部署并运行 LeoJarvis，再添加 SSH 连接。</div> : null}
          </div>
          <div className="settings-form remote-cortex-form">
            <input placeholder="设备名称" value={remoteDraft.name} onChange={(e) => setRemoteDraft({ ...remoteDraft, name: e.target.value })} />
            <input placeholder="host / IP" value={remoteDraft.host} onChange={(e) => setRemoteDraft({ ...remoteDraft, host: e.target.value })} />
            <input placeholder="ssh user" value={remoteDraft.user} onChange={(e) => setRemoteDraft({ ...remoteDraft, user: e.target.value })} />
            <input type="number" placeholder="远端端口" value={remoteDraft.remote_port} onChange={(e) => setRemoteDraft({ ...remoteDraft, remote_port: Number(e.target.value) || 8787 })} />
            <input placeholder="ProxyCommand（Cloudflare：cloudflared access ssh --hostname %h）" value={remoteDraft.proxy_command} onChange={(e) => setRemoteDraft({ ...remoteDraft, proxy_command: e.target.value })} />
            <button className="btn sm primary" disabled={!remoteDraft.host || !!remoteBusy} onClick={addRemoteProduct}>{remoteBusy === "add" ? "连接中" : "添加并连接"}</button>
          </div>
        </section>

        {/* SSH 设备健康 */}
        <section className="card settings-card">
          <div className="panel-title">SSH 设备健康监控</div>
          <p className="settings-note">仅需把本机 SSH key 授权进目标机 <code>~/.ssh/authorized_keys</code>，目标机有 python3 即可。LeoJarvis 通过 SSH 只读执行健康脚本（CPU/内存/磁盘/端口/进程），不读文件内容。</p>
          <div className="settings-list">
            {remotes.map((r, i) => <div className="settings-row" key={`${r.host}-${i}`}><b>{r.name || r.host}</b><span>{r.user ? `${r.user}@` : ""}{r.host}:{r.port || 22}{r.proxy_command ? " · ProxyCommand" : ""}</span><button className="btn sm ghost" onClick={async () => { if (r.id) await removeSshDevice(r.id); save({ remote_devices: remotes.filter((_, j) => j !== i) }); }}>删除</button></div>)}
            {remotes.length === 0 ? <div className="empty">暂无远程设备。</div> : null}
          </div>
          <div className="settings-form ssh-form">
            <input placeholder="名称" value={sshDraft.name} onChange={(e) => setSshDraft({ ...sshDraft, name: e.target.value })} />
            <input placeholder="host / IP" value={sshDraft.host} onChange={(e) => setSshDraft({ ...sshDraft, host: e.target.value })} />
            <input placeholder="user" value={sshDraft.user} onChange={(e) => setSshDraft({ ...sshDraft, user: e.target.value })} />
            <input type="number" placeholder="端口" value={sshDraft.port} onChange={(e) => setSshDraft({ ...sshDraft, port: Number(e.target.value) || 22 })} />
            <input placeholder="ProxyCommand（可选，如 Cloudflare：cloudflared access ssh --hostname %h）" value={sshDraft.proxy_command} onChange={(e) => setSshDraft({ ...sshDraft, proxy_command: e.target.value })} />
            <button className="btn sm primary" disabled={!sshDraft.host} onClick={() => {
              save({ remote_devices: [...remotes, { ...sshDraft, enabled: true }] });
              setSshDraft({ name: "", host: "", user: "", port: 22, proxy_command: "" });
            }}>添加 SSH 设备</button>
          </div>
          <button className="btn sm" disabled={remotes.length === 0} onClick={async () => { setError(""); try { const r = await probeSshDevices(); setNotice(`已探测 ${r.count} 台设备，详见「设备健康」页。`); window.setTimeout(() => setNotice(""), 4000); } catch (err) { setError(String(err)); } }}>立即探测全部设备</button>
        </section>

        {/* 系统显示 */}
        <section className="card settings-card">
          <div className="panel-title">界面与刷新</div>
          <label className="switch-row"><span>显示顶部状态条</span><input type="checkbox" checked={settings.system.show_status_bar} onChange={(e) => save({ system: { ...settings.system, show_status_bar: e.target.checked } })} /></label>
          <label className="switch-row"><span>默认展开原始详情</span><input type="checkbox" checked={settings.system.show_raw_details} onChange={(e) => save({ system: { ...settings.system, show_raw_details: e.target.checked } })} /></label>
          <label className="switch-row"><span>驾驶舱刷新间隔（秒）</span><input type="number" min="3" max="120" style={{ width: 90 }} defaultValue={settings.system.refresh_seconds} onBlur={(e) => save({ system: { ...settings.system, refresh_seconds: Number(e.target.value) || 15 } })} /></label>
        </section>
      </div>
    </div>
  );
}
