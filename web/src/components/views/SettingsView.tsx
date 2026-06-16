import { useEffect, useState } from "react";
import {
  getSettings,
  getSettingsDiagnostics,
  getMcpStatus,
  getTuning,
  importOpml,
  patchMcpSettings,
  patchSettings,
  type LeoJarvisSettings,
  type McpStatus,
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
  mcp: {
    enabled: true,
    servers: {
      tavily: { enabled: true, api_key: "" },
      github_mcp: { enabled: true, api_key: "" },
      amap_maps: { enabled: false, api_key: "" },
    },
  },
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
    mcp: { ...DEFAULT_SETTINGS.mcp, ...(input?.mcp || {}), servers: { ...DEFAULT_SETTINGS.mcp.servers, ...(input?.mcp?.servers || {}) } },
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
  const [mcpStatus, setMcpStatus] = useState<McpStatus | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [emailDraft, setEmailDraft] = useState({ name: "", host: "", user: "", password: "", port: 993 });
  const [gmailDraft, setGmailDraft] = useState({ user: "", app_password: "" });
  const [rssDraft, setRssDraft] = useState<{ name: string; url: string; category: string }>({ name: "", url: "", category: "自定义" });
  const [opmlText, setOpmlText] = useState("");
  const [xUsers, setXUsers] = useState("");
  const [mcpDraftKeys, setMcpDraftKeys] = useState<Record<string, string>>({});

  async function load() {
    setError("");
    try {
      const res = normalizeSettings(await getSettings());
      setSettings(res);
      setXUsers((res.x_monitor?.users || []).join("\n"));
      setGmailDraft({ user: res.gmail?.user || "", app_password: "" });
      getSettingsDiagnostics().then(setDiag).catch((err) => setDiag({ error: String(err) }));
      getTuning().then(setTuning).catch(() => {});
      getMcpStatus().then(setMcpStatus).catch(() => {});
    } catch (err) {
      setError(String(err));
      setSettings((prev) => prev || DEFAULT_SETTINGS);
    }
  }

  useEffect(() => { load(); }, []);

  async function save(next: Partial<LeoJarvisSettings>) {
    setSaving(true);
    setError("");
    try {
      const res = normalizeSettings(await patchSettings(next));
      setSettings(res);
      getSettingsDiagnostics().then(setDiag).catch((err) => setDiag({ error: String(err) }));
      getMcpStatus().then(setMcpStatus).catch(() => {});
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
  const tv = (s: keyof Tuning, k: string, d: number) => Number((tuning?.[s] as any)?.[k] ?? d);

  function setRss(sources: RssSource[]) { save({ rss: { sources } }); }

  async function saveMcpServer(id: string, patch: Record<string, any>) {
    setSaving(true);
    setError("");
    try {
      const res = await patchMcpSettings({ servers: { [id]: patch } });
      setMcpStatus(res.status);
      const next = normalizeSettings(await getSettings());
      setSettings(next);
      setNotice("MCP 设置已保存。需要 key 的能力会在补齐后自动变为可用。");
      window.setTimeout(() => setNotice(""), 4000);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="settings-view">
      <div className="page-head settings-head">
        <div>
          <div className="kicker">Preferences</div>
          <h1>设置</h1>
          <p>邮件账户、Gmail、应用通知、RSS / OPML、X 监控、阈值与节奏，全部可在这里自定义。保存后后端立即按新配置读取（定时任务节奏需重启生效）。</p>
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

        {/* MCP Gateway */}
        <section className="card settings-card settings-wide">
          <div className="panel-title">MCP Gateway（搜索 / 抓取 / 工具）</div>
          <p className="settings-note">
            Tavily、GitHub MCP 和高德地图统一从 Jarvis 后端调用。iPhone / Mac App 不直接嵌入第三方 key；补 key 后三端共用同一套能力。
          </p>
          <div className="reach-summary">
            <div><b>{mcpStatus?.summary.ready ?? 0}</b><span>可用</span></div>
            <div><b>{mcpStatus?.summary.needs_key ?? 0}</b><span>待补 key</span></div>
            <div><b>{mcpStatus?.summary.disabled ?? 0}</b><span>已关闭</span></div>
            <div><b>{mcpStatus?.summary.total ?? 0}</b><span>总能力</span></div>
          </div>
          <div className="settings-list mcp-list">
            {(mcpStatus?.servers || []).map((server) => {
              const localEnabled = settings.mcp?.servers?.[server.id]?.enabled ?? server.enabled;
              const draftKey = mcpDraftKeys[server.id] || "";
              return (
                <div className="settings-row mcp-row" key={server.id}>
                  <label className="toggle-pill compact">
                    <input
                      type="checkbox"
                      checked={localEnabled !== false}
                      onChange={(e) => saveMcpServer(server.id, { enabled: e.target.checked })}
                    />
                  </label>
                  <div className="settings-row-main">
                    <b>{server.name}</b>
                    <span>{server.provider} · {server.capabilities.join(" / ")}</span>
                    <small>{server.description}</small>
                    <small>{server.message}</small>
                  </div>
                  <div className="mcp-keybox">
                    <em className={`status-pill ${server.status}`}>{server.status === "ok" ? "可用" : server.status === "warn" ? "待配置" : "关闭"}</em>
                    <input
                      type="password"
                      placeholder={server.key_configured ? `已配置：${server.key_source || "local"}` : server.auth_env.join(" / ")}
                      value={draftKey}
                      onChange={(e) => setMcpDraftKeys({ ...mcpDraftKeys, [server.id]: e.target.value })}
                    />
                    <button
                      className="btn sm"
                      disabled={!draftKey.trim() || saving}
                      onClick={() => {
                        saveMcpServer(server.id, { api_key: draftKey.trim(), enabled: true });
                        setMcpDraftKeys({ ...mcpDraftKeys, [server.id]: "" });
                      }}
                    >
                      保存 key
                    </button>
                  </div>
                </div>
              );
            })}
            {!mcpStatus ? <div className="empty">MCP 状态读取中。</div> : null}
          </div>
          <div className="diag-box">
            Key 优先级：环境变量优先，其次本机设置。当前保留 <code>TAVILY_API_KEY</code>、<code>GITHUB_TOKEN</code>、<code>AMAP_MAPS_API_KEY</code>。
          </div>
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
