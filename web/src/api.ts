// 同源部署（后端 8787 直接吐 dist）时走相对地址；vite dev(5173) 时回退到后端 8787。
const BASE = (typeof window !== "undefined" && window.location.port !== "5173")
  ? ""
  : "http://127.0.0.1:8787";

function apiUrl(path: string) {
  if (BASE) return new URL(path, BASE);
  return new URL(path, window.location.origin);
}

async function readJson<T>(res: Response, label: string): Promise<T> {
  if (!res.ok) throw new Error(`${label}失败：${res.status}`);
  return res.json();
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
  tags?: string[];
  ts?: number;
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
  focus?: BriefingItem[];
  groups?: BriefingGroup[];
  counts: { business: number; life: number; total?: number; duplicates_removed?: number };
  filters?: {
    sources: { name: string; count: number }[];
    priorities: { name: string; count: number }[];
    tags: { name: string; count: number }[];
  };
  summary?: { today_focus: string; why_it_matters: string; next_action: string };
};

export async function getBriefing(): Promise<BriefingData> {
  return readJson(await fetch(`${BASE}/briefing/today`), "读取资讯简报");
}

export async function getEvents(hours = 24) {
  return readJson<any[]>(await fetch(`${BASE}/events?hours=${hours}`), "读取事件流");
}

export async function runIngest() {
  return readJson<any>(await fetch(`${BASE}/ingest/run`, { method: "POST" }), "采集资讯");
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
  content: string;
  excerpt: string;
  tags: string[];
  source?: string;
  source_url?: string | null;
  source_title?: string | null;
  import_meta?: Record<string, any>;
  favorite: boolean;
  pinned: boolean;
  archived: boolean;
  created_ts: number;
  updated_ts: number;
};

export type PersonalNoteStats = {
  total: number;
  favorite: number;
  pinned: number;
  archived: number;
  tags: { tag: string; count: number }[];
  recent: PersonalNote[];
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
  source?: string;
  source_url?: string;
  source_title?: string;
  import_meta?: Record<string, any>;
  favorite?: boolean;
  pinned?: boolean;
  archived?: boolean;
};

export async function getPersonalNotes(q = "", tag = "", status = "active"): Promise<PersonalNotesResponse> {
  const url = apiUrl("/personal-notes");
  if (q) url.searchParams.set("q", q);
  if (tag) url.searchParams.set("tag", tag);
  if (status) url.searchParams.set("status", status);
  return readJson(await fetch(url), "读取个人记事");
}

export async function savePersonalNote(input: NoteInput, id?: string): Promise<{ ok: boolean; note: PersonalNote }> {
  return readJson(await fetch(`${BASE}/personal-notes${id ? `/${id}` : ""}`, {
    method: id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }), "保存个人记事");
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
