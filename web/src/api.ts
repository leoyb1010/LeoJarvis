// 后端 API：统一走 /api 前缀，避免和单页应用前端路由（如 /settings）冲突。
// 如果页面由后端 8787 托管，使用同源 /api；如果是 Vite/preview/其它端口，回退到 8787/api。
const BASE = (() => {
  if (typeof window === "undefined") return "http://127.0.0.1:8787/api";
  const explicit = localStorage.getItem("cortex-api-base");
  if (explicit) return explicit.replace(/\/$/, "");
  return window.location.port === "8787" ? "/api" : "http://127.0.0.1:8787/api";
})();

function apiUrl(path: string) {
  // BASE 可能是相对前缀（同源托管时为 "/api"），而 new URL 需要绝对 base。
  // 统一拼成绝对地址再构造，避免 "Invalid base URL"。
  const origin = (typeof window !== "undefined" && window.location?.origin) ? window.location.origin : "http://127.0.0.1:8787";
  const absBase = /^https?:\/\//i.test(BASE) ? BASE : `${origin}${BASE}`;
  return new URL(`${absBase.replace(/\/$/, "")}${path}`);
}

async function readJson<T>(res: Response, label: string): Promise<T> {
  const contentType = res.headers.get("content-type") || "";
  const text = await res.text();
  if (!res.ok) throw new Error(`${label}失败：${res.status} ${text.slice(0, 160)}`);
  if (!contentType.includes("application/json")) {
    const preview = text.trim().slice(0, 120).replace(/\s+/g, " ");
    throw new Error(`${label}失败：接口返回的不是 JSON，而是 ${contentType || "未知类型"}。请确认后端 8787 已重启并且前端 API 指向 127.0.0.1:8787。返回预览：${preview}`);
  }
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    throw new Error(`${label}失败：JSON 解析错误 ${String(err)}；返回预览：${text.slice(0, 120)}`);
  }
}

export type BriefingItem = {
  event_id: string;
  title: string;
  original_title?: string;
  url?: string;
  domain: "business" | "life" | string;
  domain_label?: string;
  source: string;
  source_raw?: string;
  kind: string;
  score: number;
  take: string;
  triage: "notify" | "digest" | "ignore";
  priority?: "高优先" | "中优先" | "观察" | string;
  reasons?: string[];
  why_important?: string;
  relation?: string;
  next_step?: string;
  detail?: string;
  source_detail?: string;
  source_detail_raw?: string;
  source_detail_translated?: boolean;
  source_detail_missing?: boolean;
  tags?: string[];
  ts?: number;
  repo_stars?: number | null;
  repo_speed?: number | null;
  channel?: string | null;
  category?: string | null;
  // 相似标题聚类：同一事件的其它来源报道折叠在主条目下。
  dup_count?: number;
  related_sources?: { event_id?: string; title?: string; source?: string; url?: string }[];
};

export type BriefingGroup = {
  name: string;
  count: number;
  top_score: number;
  items: BriefingItem[];
};

export type BriefingData = {
  generated_at: number;
  business: BriefingItem[];
  life: BriefingItem[];
  items?: BriefingItem[];
  mail?: BriefingItem[];
  x?: BriefingItem[];
  github?: BriefingItem[];
  focus?: BriefingItem[];
  groups?: BriefingGroup[];
  counts: { business: number; life: number; total?: number; mail?: number; x?: number; github?: number; duplicates_removed?: number };
  filters?: {
    sources: { name: string; count: number }[];
    priorities: { name: string; count: number }[];
    tags: { name: string; count: number }[];
  };
  summary?: { today_focus: string; why_it_matters: string; next_action: string };
};

export async function getBriefing(opts: { compact?: boolean; limit?: number; refresh?: boolean } = {}): Promise<BriefingData> {
  const url = apiUrl("/briefing/today");
  if (opts.compact !== false) url.searchParams.set("compact", "1");
  if (opts.limit) url.searchParams.set("limit", String(opts.limit));
  if (opts.refresh) url.searchParams.set("refresh", "1");
  return readJson(await fetch(url), "读取资讯简报");
}

export async function getBriefingItem(eventId: string): Promise<BriefingItem> {
  const payload = await readJson<{ ok: boolean; item: BriefingItem }>(
    await fetch(`${BASE}/briefing/items/${encodeURIComponent(eventId)}`),
    "读取资讯详情",
  );
  return payload.item;
}

export async function getEvents(hours = 24) {
  return readJson<any[]>(await fetch(`${BASE}/events?hours=${hours}`), "读取事件流");
}

export async function runIngest() {
  return readJson<any>(await fetch(`${BASE}/ingest/run`, { method: "POST" }), "采集资讯");
}

export type DeviceSummary = {
  device_id: string;
  device_name: string;
  host_name?: string;
  model?: string;
  role?: string;
  generated_at?: number;
  last_seen_ts?: number;
  age_seconds?: number;
  online?: boolean;
  health: number;
  status: string;
  metrics: {
    cpu_load?: number | null;
    cpu_load_pct?: number | null;
    cpu_cores?: number | null;
    ram_used_pct?: number | null;
    ram_used_gb?: number | null;
    ram_total_gb?: number | null;
    ssd_used_pct?: number | null;
    ssd_free_gb?: number | null;
    thermal_pressure?: number | null;
    battery_percent?: number | null;
    battery_plugged?: boolean | null;
    network_latency_ms?: number | null;
    uptime_hours?: number | null;
  };
  modules?: Record<string, { level?: string; value?: string; summary?: string }>;
  services: { online: number; total: number };
  risks: { title: string; advice: string; level: string }[];
  privacy?: string;
  // 同一台机器的远控通道（remote_cortex）合并进设备卡后的状态徽标。
  remote_control?: { id: string; name?: string; connected: boolean; error?: string };
};

export async function getDeviceSummary(): Promise<DeviceSummary> {
  return readJson(await fetch(`${BASE}/device/summary`), "读取本机设备摘要");
}

export async function getDevices(): Promise<DeviceSummary[]> {
  return readJson(await fetch(`${BASE}/devices`), "读取设备健康列表");
}

export async function sendSelfHeartbeat(): Promise<{ ok: boolean; device: DeviceSummary }> {
  return readJson(await fetch(`${BASE}/devices/self-heartbeat`, { method: "POST" }), "上报本机心跳");
}

export async function addSshDevice(input: { host: string; name?: string; user?: string; port?: number; enabled?: boolean; proxy_command?: string; ssh_options?: string[] }) {
  return readJson<any>(await fetch(`${BASE}/devices/ssh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }), "添加 SSH 设备");
}

export async function probeSshDevices() {
  return readJson<any>(await fetch(`${BASE}/devices/ssh/probe`, { method: "POST" }), "探测 SSH 设备");
}

export type RemoteLeoJarvisConnection = {
  id: string;
  name: string;
  host: string;
  user?: string;
  ssh_port: number;
  remote_port: number;
  local_port: number;
  enabled: boolean;
  connected?: boolean;
  last_error?: string;
  last_health_ts?: number;
  updated_at?: number;
  proxy_command?: string;
  ssh_options?: string[];
};

export async function listRemoteLeoJarvis(): Promise<RemoteLeoJarvisConnection[]> {
  return readJson(await fetch(`${BASE}/remote-cortex`), "读取远程 LeoJarvis");
}

export async function addRemoteLeoJarvis(input: Partial<RemoteLeoJarvisConnection> & { host: string }) {
  return readJson<{ ok: boolean; connection: RemoteLeoJarvisConnection }>(await fetch(`${BASE}/remote-cortex`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }), "添加远程 LeoJarvis");
}

export async function connectRemoteLeoJarvis(id: string) {
  return readJson<{ ok: boolean; connection?: RemoteLeoJarvisConnection; error?: string }>(await fetch(`${BASE}/remote-cortex/${id}/connect`, { method: "POST" }), "连接远程 LeoJarvis");
}

export async function disconnectRemoteLeoJarvis(id: string) {
  return readJson<{ ok: boolean }>(await fetch(`${BASE}/remote-cortex/${id}/disconnect`, { method: "POST" }), "断开远程 LeoJarvis");
}

export async function getRemoteCockpit(id: string): Promise<{ ok: boolean; connection?: RemoteLeoJarvisConnection; data?: CockpitOverview; error?: string }> {
  return readJson(await fetch(`${BASE}/remote-cortex/${id}/cockpit`), "读取远程驾驶舱");
}

export type RssSource = { name?: string; url?: string; category?: string; domain?: string; limit?: number; enabled?: boolean };

export type LeoJarvisSettings = {
  notifications: { enabled: boolean; apps: Record<string, boolean> };
  system: { show_status_bar: boolean; show_raw_details: boolean; refresh_seconds: number };
  email: { enabled: boolean; accounts: any[]; apple_mail_fallback?: boolean; apple_mail_limit?: number; apple_mail_unread_only?: boolean };
  gmail: { enabled: boolean; user: string; app_password: string; host?: string; port?: number; mailbox?: string };
  rss: { sources: RssSource[] };
  x_monitor: { enabled: boolean; rsshub_base: string; users: string[]; include_default_ai_tech?: boolean; limit?: number };
  mcp: { enabled: boolean; servers: Record<string, { enabled?: boolean; api_key?: string }> };
  remote_devices: any[];
  remote_cortex: RemoteLeoJarvisConnection[];
  overrides?: Record<string, Record<string, any>>;
};

export type Tuning = {
  judge: { ignore_below?: number; notify_above?: number };
  schedule: { ingest_minutes?: number; guard_minutes?: number; briefing_hour?: number; reflect_hour?: number; reflect_hours?: number };
  guard: { disk_used_pct?: number; load_per_core?: number };
  intelligence: { scan_minutes?: number };
  overrides: Record<string, Record<string, any>>;
};

export async function getSettings(): Promise<LeoJarvisSettings> {
  return readJson(await fetch(`${BASE}/settings`), "读取设置");
}

export async function patchSettings(settings: Partial<LeoJarvisSettings>): Promise<LeoJarvisSettings> {
  return readJson(await fetch(`${BASE}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings }),
  }), "保存设置");
}

export async function getSettingsDiagnostics() {
  return readJson<any>(await fetch(`${BASE}/settings/diagnostics`), "读取设置诊断");
}

export async function getTuning(): Promise<Tuning> {
  return readJson(await fetch(`${BASE}/settings/tuning`), "读取阈值/节奏");
}

export async function importOpml(opml: string, opts: { category?: string; domain?: string; limit?: number } = {}) {
  return readJson<{ ok: boolean; parsed: number; added: number; total: number }>(await fetch(`${BASE}/settings/rss/import-opml`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ opml, category: opts.category || "OPML导入", domain: opts.domain || "business", limit: opts.limit ?? 8 }),
  }), "导入 OPML");
}

export type McpServerStatus = {
  id: string;
  name: string;
  provider: string;
  tier: number;
  optional: boolean;
  enabled: boolean;
  status: "ok" | "warn" | "off" | string;
  message: string;
  key_configured: boolean;
  key_source?: string;
  auth_env: string[];
  capabilities: string[];
  description: string;
  install_hint: string;
  docs_url: string;
};

export type McpStatus = {
  ok: boolean;
  generated_at: number;
  summary: { ready: number; total: number; needs_key: number; disabled: number };
  servers: McpServerStatus[];
  policy?: Record<string, string>;
};

export async function getMcpStatus(): Promise<McpStatus> {
  return readJson(await fetch(`${BASE}/mcp/status`), "读取 MCP 状态");
}

export async function patchMcpSettings(settings: Record<string, any>): Promise<{ ok: boolean; mcp: any; status: McpStatus }> {
  return readJson(await fetch(`${BASE}/mcp/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings }),
  }), "保存 MCP 设置");
}

export async function searchMcpWeb(query: string, limit = 8) {
  return readJson<any>(await fetch(`${BASE}/mcp/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit, include_answer: false }),
  }), "MCP 搜索");
}

export async function removeSshDevice(id: string) {
  return readJson<{ ok: boolean }>(await fetch(`${BASE}/devices/ssh/${id}`, { method: "DELETE" }), "删除 SSH 设备");
}

// ---------- 全景驾驶舱 ----------

export type CockpitOverview = {
  generated_at: number;
  health: {
    score: number;
    system: { raw: string; disk_pct?: number | null; load?: number | null; load_5?: number | null; load_15?: number | null; cores?: number | null; load_pct?: number | null; memory_free_pct?: number | null; memory_used_pct?: number | null };
    services_online: number;
    services_total: number;
    attention_items?: { label: string; level: string; detail: string }[];
  };
  services: ServiceRow[];
  notifications?: LocalNotifications;
  weather?: Weather;
  runtime?: RuntimeStatus;
  briefing: { business: number; life: number; top: BriefingItem[] };
  intelligence: { events: number; github_repos: number; top_repos: CockpitGithubCard[] };
  notes: PersonalNoteStats;
  memory: { active: number; pending: number; later: number; rejected: number };
  signals: {
    triage: Record<string, number>;
    sources: { source: string; count: number }[];
  };
  timeline: {
    id: string;
    title: string;
    source?: string;
    kind?: string;
    ts?: number;
    url?: string;
    summary?: string;
    why?: string;
    next_step?: string;
  }[];
};

export type Weather = {
  ok: boolean;
  city: string;
  temperature?: number;
  feels_like?: number;
  humidity?: number;
  wind?: number;
  code?: number;
  text: string;
  high?: number;
  low?: number;
  generated_at: number;
};

export async function getWeather(lat?: number, lon?: number): Promise<Weather> {
  const url = apiUrl("/system/weather");
  if (lat != null) url.searchParams.set("lat", String(lat));
  if (lon != null) url.searchParams.set("lon", String(lon));
  return readJson(await fetch(url), "读取天气");
}

export type DeviceOpsTarget = {
  target_id: string;
  target_name: string;
  host: string;
  kind: "local" | "ssh" | string;
  online?: boolean;
  mole_installed: boolean;
  mo_path: string;
  version: string;
  brew_installed: boolean;
  install_hint: string;
  capabilities: Record<string, boolean>;
  error?: string;
};

export type DeviceOpsStatus = {
  ok: boolean;
  generated_at: number;
  summary: { targets: number; ready: number; missing: number; safe_default: boolean };
  targets: DeviceOpsTarget[];
  cache?: { stale: boolean; refreshing: boolean; last_updated: number; ttl_seconds: number };
};

export type DeviceOpsPreview = {
  ok: boolean;
  target_id: string;
  action: string;
  safe_mode: boolean;
  destructive?: boolean;
  command?: string;
  duration_ms?: number;
  exit_code?: number;
  data?: any;
  summary?: { line_count: number; estimated_gb?: number | null; highlights: string[]; raw: string };
  error?: string;
  install_hint?: string;
};

export async function getDeviceOpsStatus(refresh = false): Promise<DeviceOpsStatus> {
  return readJson(await fetch(`${BASE}/device-ops/status${refresh ? "?refresh=1" : ""}`), "读取设备管家状态");
}

export async function previewDeviceOps(action: string, target_id = "local", path = ""): Promise<DeviceOpsPreview> {
  return readJson(await fetch(`${BASE}/device-ops/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, target_id, path }),
  }), "执行设备管家安全预览");
}

export type ReachChannel = {
  id: string;
  name: string;
  tier: number;
  optional: boolean;
  setup_level?: string;
  status: "ok" | "warn" | "off" | "error" | string;
  message: string;
  path: string;
  backends: string[];
  description: string;
  install_hint?: string;
  read_examples?: string[];
  search_examples?: string[];
};

export type ReachStatus = {
  ok: boolean;
  generated_at: number;
  summary: { ready: number; total: number; partial?: number; core_ready: number; core_total: number };
  channels: ReachChannel[];
  source_matrix?: Array<{ group: string; channels: string[]; use: string }>;
};

export type ReachGithubRepo = {
  ok: boolean;
  repo: string;
  error?: string;
  summary?: {
    name: string;
    description: string;
    stars: number;
    forks: number;
    language: string;
    topics: string[];
    license: string;
    latest_release: string;
    latest_release_name: string;
    pushed_at: string;
    updated_at: string;
    url: string;
  };
};

export async function getReachStatus(): Promise<ReachStatus> {
  return readJson(await fetch(`${BASE}/reach/status`), "读取 Reach 渠道状态");
}

export async function readReachUrl(url: string, limit = 12000) {
  return readJson<any>(await fetch(`${BASE}/reach/read-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, limit }),
  }), "读取网页全文");
}

export async function inspectReachGithubRepo(repo: string): Promise<ReachGithubRepo> {
  return readJson(await fetch(`${BASE}/reach/github/repo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo }),
  }), "读取 GitHub 仓库详情");
}

export type RuntimeStatus = {
  services_online: number;
  services_total: number;
  tools_ready: number;
  tools_total: number;
  tools_running: number;
  agents_running: number;
  agents_total: number;
  ai_tools: AiToolStatus[];
  agents: AgentRow[];
};

export type CockpitGithubCard = {
  name: string;
  title: string;
  url?: string;
  score: number;
  summary: string;
  source_detail?: string;
  source_detail_raw?: string;
  source_detail_translated?: boolean;
  why: string;
  relation: string;
  next_step: string;
  priority: string;
  tags: string[];
  stars?: number | null;
  speed?: number | null;
  star_history?: { ts: number; stars: number }[];
  language?: string | null;
};

export async function getCockpitOverview(): Promise<CockpitOverview> {
  return readJson(await fetch(`${BASE}/cockpit/overview`), "读取全景驾驶舱");
}

export type LocalNotificationApp = {
  id: string;
  name: string;
  category?: string;
  icon?: string | null;
  installed?: boolean;
  has_new: boolean;
  count: number;
  running: boolean;
  running_detail?: string[];
  configured: boolean;
  status: string;
  detail?: string;
  mechanism?: string;
  setup?: string;
  recent?: { title?: string; source?: string; ts?: number }[];
  checked_at: number;
};

export type LocalNotifications = {
  generated_at: number;
  database_state: string;
  privacy: string;
  apps: LocalNotificationApp[];
};

export async function getLocalNotifications(): Promise<LocalNotifications> {
  return readJson(await fetch(`${BASE}/system/notifications`), "读取本机通知状态");
}

// ---------- Personal Intelligence Hub ----------

export type IntelligenceTarget = {
  id: string;
  label: string;
  kind: string;
  query: string;
  enabled: number;
  updated_ts: number;
};

export type IntelligenceSource = {
  id: string;
  type: "rss" | "web";
  name: string;
  url: string;
  domain: "business" | "life" | string;
  enabled: number;
  last_scan_ts?: number | null;
  meta?: Record<string, any>;
};

export type IntelligenceEvent = {
  event_id: string;
  ts: number;
  source: string;
  domain: string;
  kind: string;
  title: string;
  url?: string;
  score?: number;
  take?: string;
  triage?: "notify" | "digest" | "ignore";
  reasons?: string[];
  meta?: Record<string, any>;
};

export type GithubRadarRepo = {
  repo_full_name: string;
  stars: number;
  forks?: number;
  description?: string;
  display_description?: string;
  summary_zh?: string;
  why_zh?: string;
  relation_zh?: string;
  next_step_zh?: string;
  display_topics?: string[];
  momentum_score?: number;
  url?: string;
  language?: string;
  topics?: string[];
  observed_ts: number;
  delta_24h?: number | null;
  delta_7d?: number | null;
  stars_per_day?: number | null;
  cold_stars_per_day?: number | null;
};

export type IntelligenceOverview = {
  generated_at: number;
  targets: IntelligenceTarget[];
  sources: IntelligenceSource[];
  events: IntelligenceEvent[];
  github: GithubRadarRepo[];
  stats: {
    enabled_targets: number;
    enabled_sources: number;
    notify_events: number;
    github_repos: number;
  };
};

export async function getIntelligenceOverview(): Promise<IntelligenceOverview> {
  return readJson(await fetch(`${BASE}/intelligence/overview`), "读取情报中心");
}

export async function runIntelligenceScan(options = {
  include_rss: true,
  include_web: true,
  include_github: true,
}) {
  return readJson<any>(await fetch(`${BASE}/intelligence/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  }), "运行情报扫描");
}

export async function addIntelligenceTarget(query: string) {
  return readJson<any>(await fetch(`${BASE}/intelligence/targets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, label: query, kind: "topic", enabled: true }),
  }), "添加关注项");
}

export async function setIntelligenceTargetEnabled(id: string, enabled: boolean) {
  return readJson<any>(await fetch(`${BASE}/intelligence/targets/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  }), "更新关注项");
}

export async function addIntelligenceSource(input: {
  type: "rss" | "web";
  name: string;
  url: string;
  domain?: string;
}) {
  return readJson<any>(await fetch(`${BASE}/intelligence/sources`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, domain: input.domain || "business", enabled: true }),
  }), "添加情报来源");
}

export async function setIntelligenceSourceEnabled(id: string, enabled: boolean) {
  return readJson<any>(await fetch(`${BASE}/intelligence/sources/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  }), "更新情报来源");
}

export async function sendFeedback(event_id: string, signal: "important" | "useless") {
  return readJson<any>(await fetch(`${BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id, signal }),
  }), "提交反馈");
}

// ---------- Agent 中枢 ----------

export type ChatMsg = { role: "user" | "assistant"; content: string };

export type AgentStep = {
  tool: string;
  args: Record<string, any>;
  status: "done" | "pending" | "denied";
  result?: string;
  id?: string;
};

export type PendingAction = {
  id: string;
  tool: string;
  args: Record<string, any>;
  reason: string;
};

export type AgentReply = {
  reply: string;
  steps: AgentStep[];
  pending_actions: PendingAction[];
};

export async function agentChat(messages: ChatMsg[]): Promise<AgentReply> {
  return readJson(await fetch(`${BASE}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  }), "中枢对话");
}

export async function approveAction(id: string, decision: "approve" | "reject") {
  return readJson<any>(await fetch(`${BASE}/agent/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, decision }),
  }), "审批动作");
}

// ---------- 能力模块 ----------

export type ServiceRow = {
  name: string; port: number; online: boolean; pid: string | null; can_restart: boolean;
  desc?: string;
  source?: "配置" | "自动发现" | string;
  process?: string;
  command?: string;
  cwd?: string;
  address?: string;
};
export async function getServices(): Promise<ServiceRow[]> {
  return readJson(await fetch(`${BASE}/services`), "读取本地服务");
}

export type SystemStatus = { raw: string };
export async function getSystemStatus(): Promise<SystemStatus> {
  return readJson(await fetch(`${BASE}/system/status`), "读取系统状态");
}

export type SystemLevel = "健康" | "注意" | "异常" | string;
export type SystemModule = {
  id: string;
  name: string;
  level: SystemLevel;
  value: string;
  summary: string;
  advice: string;
  metrics: Record<string, number | boolean | null>;
};
export type SystemProcess = {
  pid: string;
  cpu: number;
  memory: number;
  command: string;
};
export type AiToolStatus = {
  id: string;
  name: string;
  installed: boolean;
  path?: string | null;
  current_version: string;
  latest_version: string;
  update_state: string;
  running: boolean;
  running_detail: string[];
  launch: string;
  package_manager?: string;
  upgrade_command?: string;
  can_upgrade?: boolean;
  checked_at: number;
  advice: string;
};
export type SystemOverview = {
  generated_at: number;
  score: number;
  modules: SystemModule[];
  processes: SystemProcess[];
  ai_tools: AiToolStatus[];
  raw: string;
  risks: { title: string; advice: string; level: SystemLevel }[];
};
export async function getSystemOverview(): Promise<SystemOverview> {
  return readJson(await fetch(`${BASE}/system/overview`), "读取系统概览");
}
export async function getAiTools(): Promise<AiToolStatus[]> {
  return readJson(await fetch(`${BASE}/system/ai-tools`), "读取 AI 工具状态");
}
export async function upgradeAiTool(id: string): Promise<{ ok: boolean; tool?: string; command?: string; output?: string; error?: string }> {
  return readJson(await fetch(`${BASE}/system/ai-tools/${id}/upgrade`, { method: "POST" }), "升级 AI 工具");
}

export type TerminalSession = {
  id: string;
  tool_id: string;
  tool_name: string;
  command: string;
  cwd: string;
  created_at: number;
  running: boolean;
  exit_code?: number | null;
};

export type TerminalResponse = {
  ok: boolean;
  error?: string;
  session?: TerminalSession;
  output?: string;
};

function remoteTerminalData<T>(payload: T | { ok: boolean; data?: T; error?: string }): T {
  if (payload && typeof payload === "object" && "data" in payload && (payload as any).data) return (payload as any).data as T;
  return payload as T;
}

export async function getTerminalSessions(remoteId = "local"): Promise<TerminalSession[]> {
  const path = remoteId === "local" ? `${BASE}/terminal/sessions` : `${BASE}/remote-cortex/${remoteId}/terminal/sessions`;
  try {
    const payload = await readJson<TerminalSession[] | { ok: boolean; data?: TerminalSession[] }>(await fetch(path), "读取 CLI 会话");
    const rows = Array.isArray(payload) ? payload : (payload as any)?.data;
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

export async function createTerminalSession(tool_id: string, cwd = "", remoteId = "local"): Promise<TerminalResponse> {
  const path = remoteId === "local" ? `${BASE}/terminal/sessions` : `${BASE}/remote-cortex/${remoteId}/terminal/sessions`;
  const payload = await readJson<TerminalResponse | { ok: boolean; data?: TerminalResponse; error?: string }>(await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_id, cwd }),
  }), "启动 CLI 控制台");
  return remoteTerminalData<TerminalResponse>(payload);
}

export async function readTerminalSession(sessionId: string, remoteId = "local"): Promise<TerminalResponse> {
  const path = remoteId === "local"
    ? `${BASE}/terminal/sessions/${sessionId}/read`
    : `${BASE}/remote-cortex/${remoteId}/terminal/sessions/${sessionId}/read`;
  const payload = await readJson<TerminalResponse | { ok: boolean; data?: TerminalResponse; error?: string }>(await fetch(path), "读取 CLI 控制台");
  return remoteTerminalData<TerminalResponse>(payload);
}

export async function writeTerminalSession(sessionId: string, text: string, remoteId = "local"): Promise<TerminalResponse> {
  const path = remoteId === "local"
    ? `${BASE}/terminal/sessions/${sessionId}/write`
    : `${BASE}/remote-cortex/${remoteId}/terminal/sessions/${sessionId}/write`;
  const payload = await readJson<TerminalResponse | { ok: boolean; data?: TerminalResponse; error?: string }>(await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }), "写入 CLI 控制台");
  return remoteTerminalData<TerminalResponse>(payload);
}

export async function closeTerminalSession(sessionId: string, remoteId = "local"): Promise<{ ok: boolean; error?: string }> {
  const path = remoteId === "local"
    ? `${BASE}/terminal/sessions/${sessionId}`
    : `${BASE}/remote-cortex/${remoteId}/terminal/sessions/${sessionId}`;
  const payload = await readJson<{ ok: boolean; error?: string } | { ok: boolean; data?: { ok: boolean; error?: string }; error?: string }>(await fetch(path, { method: "DELETE" }), "关闭 CLI 控制台");
  return remoteTerminalData<{ ok: boolean; error?: string }>(payload);
}

export type DevTool = { id: string; name: string; category: string; installed: boolean; path: string | null; version: string; launch: string; checked_at: number };
export type DevToolchain = {
  generated_at: number;
  summary: { installed: number; total: number };
  categories: Record<string, DevTool[]>;
  tools: DevTool[];
};
export async function getDevTools(): Promise<DevToolchain> {
  return readJson(await fetch(`${BASE}/system/dev-tools`), "读取本机开发工具链");
}

export type AgentRow = {
  id: string; name: string; command: string; pid: number; status: string; started: number;
};
export async function getAgents(): Promise<AgentRow[]> {
  return readJson(await fetch(`${BASE}/agents`), "读取子智能体");
}

// ---------- 个人记事 ----------

export type PersonalNote = {
  id: string;
  title: string;
  content?: string;
  excerpt: string;
  safe_excerpt?: string;
  tags: string[];
  source?: string;
  source_url?: string | null;
  source_title?: string | null;
  project_name?: string | null;
  import_meta?: Record<string, any>;
  favorite: boolean;
  pinned: boolean;
  archived: boolean;
  sensitive?: boolean;
  created_ts: number;
  updated_ts: number;
};

export type PersonalNoteStats = {
  total: number;
  favorite: number;
  pinned: number;
  archived: number;
  tags: { tag: string; count: number }[];
  projects?: { name: string; count: number }[];
  recent: PersonalNote[];
};

export type PersonalNotebook = {
  name: string;
  description: string;
  note_count: number;
  source_count: number;
  favorite: number;
  pinned: number;
  updated_ts: number;
  tags: { tag: string; count: number }[];
  recent: PersonalNote[];
};

export type NoteTransformTemplate = {
  id: string;
  label: string;
  tag: string;
};

export type PersonalNotesResponse = {
  ok: boolean;
  notes: PersonalNote[];
  stats: PersonalNoteStats;
};

export type NoteInput = {
  title?: string;
  content?: string;
  excerpt?: string;
  tags?: string[];
  project_name?: string;
  source?: string;
  source_url?: string;
  source_title?: string;
  import_meta?: Record<string, any>;
  favorite?: boolean;
  pinned?: boolean;
  archived?: boolean;
};

export async function getPersonalNotes(q = "", tag = "", status = "active", project = ""): Promise<PersonalNotesResponse> {
  const url = apiUrl("/personal-notes");
  url.searchParams.set("compact", "1");
  if (q) url.searchParams.set("q", q);
  if (tag) url.searchParams.set("tag", tag);
  if (status) url.searchParams.set("status", status);
  if (project) url.searchParams.set("project", project);
  return readJson(await fetch(url), "读取个人记事");
}

export async function savePersonalNote(input: NoteInput, id?: string): Promise<{ ok: boolean; note: PersonalNote }> {
  return readJson(await fetch(`${BASE}/personal-notes${id ? `/${id}` : ""}`, {
    method: id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }), "保存个人记事");
}

export async function getPersonalNoteNotebooks(): Promise<{ ok: boolean; notebooks: PersonalNotebook[]; templates: NoteTransformTemplate[] }> {
  return readJson(await fetch(`${BASE}/personal-notes/notebooks`), "读取 Notebook 项目");
}

export async function transformPersonalNote(id: string, template: string): Promise<{ ok: boolean; note: PersonalNote; template: string }> {
  return readJson(await fetch(`${BASE}/personal-notes/${id}/transform`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template }),
  }), "整理个人记事");
}

export async function deletePersonalNote(id: string): Promise<{ ok: boolean }> {
  return readJson(await fetch(`${BASE}/personal-notes/${id}`, { method: "DELETE" }), "删除个人记事");
}

export type NoteAttachment = {
  id: string;
  note_id: string;
  file_name: string;
  mime_type?: string;
  size: number;
  path: string;
  url?: string;
  is_image?: boolean;
  summary: string;
  created_ts: number;
};
export type PersonalNoteDetail = {
  ok: boolean;
  note: PersonalNote | null;
  revisions: any[];
  attachments: NoteAttachment[];
};
export async function getPersonalNote(id: string): Promise<PersonalNoteDetail> {
  return readJson(await fetch(`${BASE}/personal-notes/${id}`), "读取个人记事详情");
}
export async function importPersonalNoteUrl(url: string): Promise<{ ok: boolean; note: PersonalNote }> {
  return readJson(await fetch(`${BASE}/personal-notes/import-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  }), "导入链接");
}
export async function importPersonalNoteAttachment(input: {
  file_name: string;
  mime_type?: string;
  data_base64?: string;
  text_content?: string;
  note_id?: string;
}): Promise<{ ok: boolean; note: PersonalNote; attachment: NoteAttachment }> {
  return readJson(await fetch(`${BASE}/personal-notes/import-attachment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }), "导入附件");
}

export type JournalRow = { id: string; ts: number; title: string; content: string };
export async function getJournal(q = ""): Promise<JournalRow[]> {
  return readJson(await fetch(`${BASE}/journal?q=${encodeURIComponent(q)}`), "读取旧记事");
}
export async function addJournal(text: string) {
  return readJson<any>(await fetch(`${BASE}/journal`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }), "写入旧记事");
}

// ---------- 长期记忆 ----------

export type MemoryRow = {
  id: string;
  type: string;
  subject: string | null;
  statement: string;
  confidence: number;
  salience: number;
  created_ts?: number;
  updated_ts: number;
  status?: "active" | "pending" | "later" | "rejected";
  source_events?: string;
};
export async function getMemories(): Promise<MemoryRow[]> {
  return readJson(await fetch(`${BASE}/memories`), "读取长期记忆");
}
export async function getPendingMemories(): Promise<MemoryRow[]> {
  return readJson(await fetch(`${BASE}/memories/pending`), "读取待确认记忆");
}
export async function decideMemory(id: string, decision: "accept" | "reject" | "later"): Promise<{ ok: boolean; status: string }> {
  return readJson(await fetch(`${BASE}/memories/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  }), "处理记忆候选");
}
export async function runReflect(): Promise<{ created: number; used_llm?: boolean; events?: number; note?: string }> {
  return readJson(await fetch(`${BASE}/memory/reflect`, { method: "POST" }), "生成待确认记忆");
}

export function connectNotify(onMsg: (m: any) => void) {
  // 同源部署用当前 host；dev(5173) 回退到后端 8787。
  const wsBase = (typeof window !== "undefined" && window.location.port !== "5173")
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
    : "ws://127.0.0.1:8787";
  const ws = new WebSocket(`${wsBase}/ws/notify`);
  ws.onmessage = (event) => onMsg(JSON.parse(event.data));
  const timer = window.setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 30000);
  ws.addEventListener("close", () => window.clearInterval(timer));
  return ws;
}
