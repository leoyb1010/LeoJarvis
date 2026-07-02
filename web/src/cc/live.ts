// 指挥台实时数据层 —— 同源走相对 /api，只有 vite dev(5173) 回退绝对地址。
const BASE = (() => {
  if (typeof window === "undefined") return "/api";
  return window.location.port === "5173" ? "http://127.0.0.1:8787/api" : "/api";
})();

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
async function jpatch<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "PATCH",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
async function jdel<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { method: "DELETE" });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

// ---- CLI agent 编排（真实）----
export type CliAgent = { name: string; display: string; installed: boolean; version: string | null; auth: string; run_supported: string };
export type CliSession = { id: string; agent: string; name: string; prompt: string; status: string; started: number; pid: number; output: string };
export type ExternalAgent = { agent: string; display: string; kind: string; port: number; status: string; docs?: string };
export type CliCommand = { cmd: string; label: string; desc: string; kind: string };
export const getCliAgents = () => jget<{ agents: CliAgent[] }>("/agents/cli");
export const getCliCommands = (agent: string) => jget<{ ok?: boolean; agent: string; commands: CliCommand[]; models: string[] }>(`/agents/cli/${encodeURIComponent(agent)}/commands`);
export const runCliAgent = (name: string, prompt: string, cwd?: string, model?: string) => jpost<{ ok: boolean; id?: string; error?: string }>("/agents/cli/run", { name, prompt, cwd, model });
export const getCliSessions = () => jget<{ sessions: CliSession[]; external?: ExternalAgent[] }>("/agents/cli/sessions");
export const stopCliSession = (id: string) => jpost<{ ok: boolean }>(`/agents/cli/sessions/${id}/stop`);
export const clearFinishedSessions = () => jpost<{ ok: boolean; removed: number }>("/agents/cli/clear-finished");

// ---- 高德地图（真实）----
export type AmapConfig = { configured: boolean; js_key: string; home_city: string; center: string | null };
export type AmapWeather = { ok?: boolean; city?: string; weather?: string; temperature?: string; winddirection?: string; windpower?: string; humidity?: string; reporttime?: string; forecast?: { date: string; day: string; night: string; temp: string }[]; error?: string };
export const getAmapConfig = () => jget<AmapConfig>("/amap/config");
export const getAmapWeather = (city?: string) => jget<AmapWeather>(`/amap/weather${city ? `?city=${encodeURIComponent(city)}` : ""}`);

// ---- 设置（真实读写）----
export type Settings = Record<string, any>;
export const getSettings = () => jget<Settings>("/settings");
export const patchSettings = (settings: Settings) => jpatch<{ ok?: boolean } & Record<string, any>>("/settings", { settings });

// ---- 系统 / 服务 ----
// overview: { score, modules:[{ id, name, value, level, metrics:{ used_pct, load_pct, load_1, cores, ... } }], ... }
export type SysModule = { id: string; name: string; value: string; level: string; summary?: string; metrics?: Record<string, any> };
export type SystemOverview = { score?: number; modules?: SysModule[] } & Record<string, any>;
export const getSystemOverview = () => jget<SystemOverview>("/system/overview");

// services: [{ name, display, port, health:'online'|'offline', exposed, managed, ... }]
export type Service = { name: string; display?: string; port?: number; health?: string; exposed?: boolean; managed?: boolean } & Record<string, any>;
export const getServices = () => jget<Service[]>("/services/discover");

// ---- 情报 / 简报 ----
// briefing: { items:[{ title, source, priority, triage, why_important, ts, ... }], counts:{ total, ... } }
export type BriefItem = { title?: string; source?: string; priority?: string; triage?: string; why_important?: string; take?: string; ts?: number; event_id?: string } & Record<string, any>;
export type Briefing = { items?: BriefItem[]; counts?: Record<string, number> } & Record<string, any>;
export const getBriefing = () => jget<Briefing>("/briefing/today?compact=1");

// intelligence/overview: { github:[{ repo_full_name, display_description/summary_zh/description, language, stars, stars_per_day, delta_24h, momentum_score, url, topics, ... }], sources:[{ id, type, name, url, domain, enabled, last_scan_ts }], targets:[{ id, label, kind, query, enabled }], stats:{ enabled_targets, enabled_sources, notify_events, github_repos } }
export type IntelRepo = { repo_full_name?: string; description?: string; display_description?: string; summary_zh?: string; why_zh?: string; relation_zh?: string; next_step_zh?: string; language?: string; stars?: number; forks?: number; stars_per_day?: number; delta_24h?: number; delta_7d?: number; momentum_score?: number; url?: string; topics?: string[]; display_topics?: string[]; pushed_at?: string; created_at?: string; observed_ts?: number } & Record<string, any>;
export type IntelSource = { id?: string; type?: string; name?: string; url?: string; domain?: string; enabled?: number; last_scan_ts?: number | null } & Record<string, any>;
export type IntelTarget = { id?: string; label?: string; kind?: string; query?: string; enabled?: number } & Record<string, any>;
export type Intelligence = { github?: IntelRepo[]; sources?: IntelSource[]; targets?: IntelTarget[]; stats?: Record<string, number> } & Record<string, any>;
export const getIntelligence = () => jget<Intelligence>("/intelligence/overview");

// briefing/items/{id}: { ok, item:{ title, source, source_detail(中文全文正文), source_detail_translated, why_important, take, next_step, reasons[], url, score, ts, priority, ... } }
export type BriefDetailItem = { title?: string; source?: string; source_detail?: string; source_detail_translated?: boolean; source_detail_missing?: boolean; pending_translation?: boolean; why_important?: string; take?: string; next_step?: string; reasons?: string[]; url?: string; score?: number; ts?: number; priority?: string; relation?: string } & Record<string, any>;
export const getBriefingItem = (id: string) => jget<{ ok?: boolean; item?: BriefDetailItem }>(`/briefing/items/${encodeURIComponent(id)}`);
// 秒开后异步补译:返回同步全译后的 item(中文正文)。
export const translateBriefingItem = (id: string) => jpost<{ ok?: boolean; item?: BriefDetailItem }>(`/briefing/items/${encodeURIComponent(id)}/translate`);

// ---- 中枢对话（真实）----
export type ChatMsg = { role: "user" | "assistant"; content: string };
export type ChatStep = { tool: string; args?: any; status: string; result?: string };
export type PendingAction = { id: string; tool?: string; args?: any; reason?: string } & Record<string, any>;
export type ChatReply = { reply?: string; steps?: ChatStep[]; pending_actions?: PendingAction[] } & Record<string, any>;
export const agentChat = (messages: ChatMsg[]) => jpost<ChatReply>("/agent/chat", { messages });
export const approveAction = (id: string, decision: "approve" | "reject") => jpost<ChatReply>("/agent/approve", { id, decision });

// 流式对话事件（与后端 run_agent_stream 对齐）
export type ChatStreamEvent =
  | { type: "thought"; text: string }
  | { type: "tool_start"; tool: string; args?: any }
  | { type: "tool_result"; tool: string; status: string; result?: string }
  | { type: "token"; text: string }
  | { type: "final"; reply: string; steps?: ChatStep[] }
  | { type: "pending"; reply: string; steps?: ChatStep[]; pending_actions?: PendingAction[] }
  | { type: "error"; message: string };

/**
 * 流式对话：POST /agent/chat/stream，逐事件回调，首字亚秒可见。
 * onEvent 收到每个 SSE 事件；返回一个可 await 的 Promise，结束时 resolve。
 * 浏览器不支持 EventSource 的 POST，所以用 fetch + ReadableStream 手解析 SSE。
 */
export async function agentChatStream(
  messages: ChatMsg[],
  onEvent: (e: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(BASE + "/agent/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`/agent/chat/stream ${r.status}`);
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE 以空行分隔事件；逐个取出
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const payload = line.slice(6);
      if (payload === "[DONE]") return;
      try {
        onEvent(JSON.parse(payload) as ChatStreamEvent);
      } catch {
        /* 跳过解析失败的帧 */
      }
    }
  }
}

// ---- 语音转写（本机 Whisper）----
export type SpeechTranscribeReq = { data_base64: string; mime_type: string; file_name: string; model?: string; language?: string; prompt?: string };
export const transcribeSpeech = (req: SpeechTranscribeReq) =>
  jpost<{ ok?: boolean; text?: string; error?: string }>("/speech/transcribe", req);

// ---- 实时推送（/ws/notify）----
export type NotifyEvent = { type?: string; source?: string; title?: string; take?: string } & Record<string, any>;

/**
 * 订阅后端 /ws/notify 推送（情报命中、系统告警等），带自动重连。
 * 返回一个 stop() 用于卸载时关闭。后端所有 push 都是 {type:"notify", ...}。
 */
export function connectNotify(onEvent: (e: NotifyEvent) => void): () => void {
  const wsBase = window.location.port === "5173"
    ? "ws://127.0.0.1:8787"
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  let ws: WebSocket | null = null;
  let ping: number | undefined;
  let retry: number | undefined;
  let closed = false;
  let backoff = 1000;

  const open = () => {
    if (closed) return;
    ws = new WebSocket(`${wsBase}/api/ws/notify`);
    ws.onopen = () => { backoff = 1000; };
    ws.onmessage = (ev) => { try { onEvent(JSON.parse(ev.data)); } catch { /* ignore */ } };
    ws.onclose = () => {
      if (ping) window.clearInterval(ping);
      if (closed) return;
      retry = window.setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 15000);   // 指数退避，封顶 15s
    };
    ws.onerror = () => { try { ws?.close(); } catch { /* ignore */ } };
    ping = window.setInterval(() => { if (ws?.readyState === WebSocket.OPEN) ws.send("ping"); }, 30000);
  };
  open();

  return () => {
    closed = true;
    if (ping) window.clearInterval(ping);
    if (retry) window.clearTimeout(retry);
    try { ws?.close(); } catch { /* ignore */ }
  };
}

// 全局单例：整个 App 只开一条 /ws/notify 连接，多个组件通过订阅复用。
const _notifySubs = new Set<(e: NotifyEvent) => void>();
let _notifyStop: (() => void) | null = null;

/** 订阅实时推送（自动管理单例连接）。返回取消订阅函数。 */
export function subscribeNotify(handler: (e: NotifyEvent) => void): () => void {
  _notifySubs.add(handler);
  if (!_notifyStop) {
    _notifyStop = connectNotify((e) => { for (const h of _notifySubs) { try { h(e); } catch { /* ignore */ } } });
  }
  return () => {
    _notifySubs.delete(handler);
    if (_notifySubs.size === 0 && _notifyStop) { _notifyStop(); _notifyStop = null; }
  };
}

// ---- 记事（完整 CRUD + 链接导入 + 附件/图片）----
export type PersonalNote = { id?: string; title?: string; excerpt?: string; content?: string; tags?: string[]; pinned?: boolean; favorite?: boolean; source?: string; source_url?: string; created_ts?: number; updated_ts?: number } & Record<string, any>;
export type NoteAttachment = { id?: string; file_name?: string; mime_type?: string; size?: number } & Record<string, any>;
export type NoteInput = { title?: string; content?: string; excerpt?: string; tags?: string[]; pinned?: boolean; favorite?: boolean; source?: string };
export const getNotes = (q = "") => jget<{ ok?: boolean; notes?: PersonalNote[]; stats?: any }>(`/personal-notes${q ? `?q=${encodeURIComponent(q)}` : ""}`);
export const getNote = (id: string) => jget<{ ok?: boolean; note?: PersonalNote; revisions?: any[]; attachments?: NoteAttachment[] }>(`/personal-notes/${encodeURIComponent(id)}`);
export const createNote = (note: NoteInput) => jpost<{ ok?: boolean; note?: PersonalNote }>("/personal-notes", note);
export const updateNote = (id: string, note: NoteInput) => jpatch<{ ok?: boolean; note?: PersonalNote }>(`/personal-notes/${encodeURIComponent(id)}`, note);
export const deleteNote = (id: string) => fetch(`${BASE}/personal-notes/${encodeURIComponent(id)}`, { method: "DELETE" }).then((r) => r.json());
export const importNoteUrl = (url: string, notebook = "") => jpost<{ ok?: boolean; note?: PersonalNote }>("/personal-notes/import-url", { url, notebook });
export const importNoteAttachment = (p: { file_name: string; mime_type?: string; data_base64?: string; text_content?: string; note_id?: string; notebook?: string }) => jpost<{ ok?: boolean; attachment?: NoteAttachment; note?: PersonalNote }>("/personal-notes/import-attachment", p);
export const attachmentUrl = (id: string) => `${BASE}/personal-notes/attachments/${encodeURIComponent(id)}`;

// ── open-notebook 能力（笔记本 / 来源 / RAG 对话 / 工作室）──
export type NbSource = { id: string; title?: string; excerpt?: string; tags?: string[]; source?: string; source_url?: string; chars?: number; updated_ts?: number; pinned?: boolean };
export type NbCitation = { n: number; note_id: string; title: string; snippet: string };
export type StudioTpl = { id: string; label: string; tag: string };
export type NbWorkspace = { ok?: boolean; notebook?: string; sources: NbSource[]; notes: NbSource[]; source_count: number; note_count: number; studio_templates: StudioTpl[] };
export type NotebookMeta = { name: string; note_count?: number; source_count?: number; updated_ts?: number; tags?: { tag: string; count: number }[] };
export const getNotebooks = () => jget<{ ok?: boolean; notebooks?: NotebookMeta[]; templates?: any[] }>("/personal-notes/notebooks");
export const getNotebookWorkspace = (notebook = "") => jget<NbWorkspace>(`/notebook/workspace?notebook=${encodeURIComponent(notebook)}`);
export const addNotebookText = (notebook: string, title: string, text: string) => jpost<{ ok?: boolean; note?: PersonalNote }>("/notebook/source-text", { notebook, title, text });
export const notebookChat = (notebook: string, question: string, source_ids: string[] = [], history: { role: string; content: string }[] = []) =>
  jpost<{ ok?: boolean; answer: string; citations: NbCitation[]; used_chunks: number; grounded: boolean }>("/notebook/chat", { notebook, question, source_ids, history });
export const notebookStudio = (notebook: string, kind: string, source_ids: string[] = []) =>
  jpost<{ ok?: boolean; note?: PersonalNote; kind?: string }>("/notebook/studio", { notebook, kind, source_ids });

// ---- 设备 / 舰队（F2：本机登记心跳，列出所有设备只读状态）----
export type FleetDevice = {
  device_id: string; device_name?: string; host_name?: string; model?: string; role?: string;
  online?: boolean; is_current?: boolean; seen_ago_s?: number; last_seen_ts?: number;
  health?: number; status?: string;
  metrics?: { cpu_load_pct?: number; ram_used_pct?: number; ram_total_gb?: number; ssd_used_pct?: number; ssd_free_gb?: number; battery_percent?: number; battery_plugged?: boolean };
  services?: { online?: number; total?: number };
  risks?: { level?: string; title?: string; detail?: string }[];
} & Record<string, any>;
export const getDevices = () => jget<{ ok?: boolean; current?: string; devices?: FleetDevice[]; count?: number }>("/devices");
export const deleteDevice = (id: string) => fetch(`${BASE}/devices/${encodeURIComponent(id)}`, { method: "DELETE" }).then((r) => r.json());

// ---- 星座运势（离线确定性）----
export type Horoscope = { ok?: boolean; sign?: string; sign_en?: string; score?: number; level?: string; advice?: string; lucky_color?: string; lucky_number?: number; yi?: string[]; ji?: string[]; summary?: string } & Record<string, any>;
export const getHoroscope = (sign: string) => jget<Horoscope>(`/horoscope/${encodeURIComponent(sign)}`);

// notifications: { apps:[{ id, name, count, has_new, icon(base64 dataurl), ... }] }
export type NotifApp = { id: string; name?: string; count?: number; has_new?: boolean; icon?: string } & Record<string, any>;
export const getNotifications = () => jget<{ apps?: NotifApp[] } & Record<string, any>>("/system/notifications");
export const openApp = (name: string) => jpost<{ ok: boolean; message?: string; error?: string }>("/apps/open", { name });

// 顶部 header vitals：健康分 + CPU% + 在线/总服务数（一次组合）
export type Vitals = { health: number | null; cpu: number | null; online: number; total: number };
export async function getVitals(): Promise<Vitals> {
  const [ov, svc] = await Promise.allSettled([getSystemOverview(), getServices()]);
  let health: number | null = null;
  let cpu: number | null = null;
  if (ov.status === "fulfilled") {
    const o = ov.value;
    if (typeof o?.score === "number") health = Math.round(o.score);
    const cpuMod = o?.modules?.find((m) => m.id === "cpu");
    const lp = cpuMod?.metrics?.load_pct;
    if (typeof lp === "number") cpu = Math.round(lp);
  }
  let online = 0, total = 0;
  if (svc.status === "fulfilled" && Array.isArray(svc.value)) {
    total = svc.value.length;
    online = svc.value.filter((s) => s.health === "online").length;
  }
  return { health, cpu, online, total };
}

export function fmtAgo(ts?: number): string {
  if (!ts) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}分`;
  return `${Math.floor(s / 3600)}时`;
}

// ---- WorkDock 合并 M2：信息转任务收件箱 ----
export type InboxTask = {
  id: string; title: string; action?: string; object?: string; owner?: string; due?: string;
  priority?: string; confidence?: number; inbox_state?: string; risk_level?: string;
  origin?: string; event_id?: string; context_preview?: string; suggestion?: string;
  tags?: string[]; suggest_only?: boolean; created_ts?: number;
} & Record<string, any>;
export type InboxList = { ok?: boolean; tasks: InboxTask[]; counts?: Record<string, number> };
export const getInbox = (states = "unconfirmed,confirmed") =>
  jget<InboxList>(`/inbox/list?states=${encodeURIComponent(states)}`);
export const rebuildInbox = (hours = 48) =>
  jpost<{ ok: boolean; scanned: number; created: number; used_llm?: boolean; note?: string }>(`/inbox/rebuild?hours=${hours}`);
export const setInboxState = (id: string, state: "unconfirmed" | "confirmed" | "done" | "ignored") =>
  jpost<{ ok: boolean }>(`/inbox/${encodeURIComponent(id)}/state`, { state });

// ---- WorkDock 合并 M3：下班收尾 / 日报周报 ----
export type WrapItem = { title?: string; detail?: string; source?: Record<string, any> };
export type WrapUp = {
  ok?: boolean; period: string; label: string;
  completed: WrapItem[]; unfinished: WrapItem[];
  counts?: { completed: number; unfinished: number };
  summary?: { headline?: string; highlights?: string[]; by_area?: Record<string, string>; report?: string; unfinished_focus?: string; next?: string };
};
export const getWrapup = (period: "today" | "week" = "today") =>
  jget<WrapUp>(`/wrapup/${period}`);

// ---- WorkDock 合并 M4：受控执行台 ----
export type AgentRunPending = { id: string; status: string; tool?: string; args?: any; thought?: string; gate?: { verdict: string; label: string }; reason?: string };
export type AgentRunPast = { id: string; status: string; tool?: string; title?: string; detail?: string; ts?: number };
export type AgentRunsOverview = {
  ok?: boolean; pending: AgentRunPending[]; recent: AgentRunPast[];
  counts?: { awaiting: number; executed: number; blocked: number; total_recent: number };
};
export const getAgentRuns = (hours = 48) => jget<AgentRunsOverview>(`/agent-runs?hours=${hours}`);

// ---- P1 Email 腔理 ----
export type EmailTriage = { event_id: string; summary?: string; tags?: string[]; actionable?: boolean; action?: string; reply_draft?: string } & Record<string, any>;
export const getEmailTriage = (eventId: string) => jget<{ ok: boolean; triage: EmailTriage | null }>(`/email/triage/${encodeURIComponent(eventId)}`);
export const runEmailTriage = (hours = 720) => jpost<{ ok: boolean; scanned: number; triaged: number; actionable: number; note?: string }>(`/email/triage?hours=${hours}`);

// ---- P3 定时/事件触发 agent 任务 ----
export type ScheduledTask = { id: string; name: string; prompt: string; trigger: string; interval_minutes?: number; cron_hour?: number; cron_minute?: number; trigger_event?: string; trigger_count?: number; status: string; last_run?: number; last_result?: string } & Record<string, any>;
export const getScheduledTasks = () => jget<{ ok: boolean; tasks: ScheduledTask[] }>("/tasks/scheduled");
export const createScheduledTask = (t: Partial<ScheduledTask>) => jpost<{ ok: boolean; id?: string }>("/tasks/scheduled", t);
export const setScheduledTaskStatus = (id: string, status: "active" | "paused" | "deleted") => jpost<{ ok: boolean }>(`/tasks/scheduled/${encodeURIComponent(id)}/status`, { status });
export const runScheduledTask = (id: string) => jpost<{ ok: boolean }>(`/tasks/scheduled/${encodeURIComponent(id)}/run`);

// ---- 问题1 日程 ----
export type ScheduleItem = { id: string; title: string; note?: string; start_ts: number; remind_ts?: number | null; repeat: string; status: string; overdue?: boolean; source?: string } & Record<string, any>;
export const getSchedule = (status = "", upcomingHours = 0) => jget<{ ok: boolean; items: ScheduleItem[]; stats: { pending: number; today: number } }>(`/schedule?status=${status}&upcoming_hours=${upcomingHours}`);
export const createSchedule = (s: { title: string; start_ts: number; remind_ts?: number | null; note?: string; repeat?: string }) => jpost<{ ok: boolean; id?: string }>("/schedule", s);
export const updateSchedule = (id: string, patch: Partial<ScheduleItem>) => jpatch<{ ok: boolean }>(`/schedule/${encodeURIComponent(id)}`, patch);
export const scheduleDone = (id: string, done = true) => jpost<{ ok: boolean }>(`/schedule/${encodeURIComponent(id)}/done?done=${done}`);
export const deleteSchedule = (id: string) => jdel<{ ok: boolean }>(`/schedule/${encodeURIComponent(id)}`);

// ---- P2 Calendar ----
export type CalEvent = { event_id: string; title: string; start?: number; location?: string; organizer?: string };
export const getUpcomingEvents = (hours = 168) => jget<{ ok: boolean; events: CalEvent[] }>(`/calendar/upcoming?hours=${hours}`);
export const importIcs = (ics: string) => jpost<{ ok: boolean; parsed: number; added: number }>("/calendar/import-ics", { ics });
export const syncCalendar = () => jpost<{ ok: boolean; reason?: string; added?: number }>("/calendar/sync");
export type CalDavStatus = { configured: boolean; lib_present: boolean; url_host?: string; has_url?: boolean };
export const getCalDavStatus = () => jget<CalDavStatus>("/calendar/caldav-status");

// ---- P4 深入调研 ----
export type DeepResearch = { ok: boolean; goal: string; report: string; sources: { n: number; title: string; url: string }[]; findings: any[]; note?: string };
export const deepResearch = (goal: string, maxSources = 5) => jpost<DeepResearch>("/research/deep", { goal, max_sources: maxSources });
export const researchReport = (goal: string, maxSources = 5) => jpost<{ ok: boolean; goal: string; html: string }>("/research/report", { goal, max_sources: maxSources });

// ---- A 主动助理 ----
export type AssistantCheckin = { enabled: boolean; hour: number; minute: number };
export type AssistantConfig = { enabled: boolean; name: string; persona: string; checkins: Record<string, AssistantCheckin> } & Record<string, any>;
export const getAssistantConfig = () => jget<{ ok: boolean; config: AssistantConfig }>("/assistant/config");
export const patchAssistantConfig = (c: Partial<AssistantConfig>) => jpatch<{ ok: boolean; config: AssistantConfig }>("/assistant/config", c);
export const runCheckin = (slot: string) => jpost<{ ok: boolean; reply?: string; title?: string }>(`/assistant/checkins/${encodeURIComponent(slot)}/run`);

// ---- B 技能库 ----
export type Skill = { id: string; name: string; category: string; when_to_use: string; body: string; keywords: string[]; source: string; use_count: number; status: string } & Record<string, any>;
export const getSkills = (q = "", category = "") => jget<{ ok: boolean; skills: Skill[] }>(`/skills?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`);
export const createSkill = (s: Partial<Skill>) => jpost<{ ok: boolean; id?: string }>("/skills", s);
export const setSkillStatus = (id: string, status: "active" | "archived" | "deleted") => jpost<{ ok: boolean }>(`/skills/${encodeURIComponent(id)}/status`, { status });
// 导入:贴 SKILL.md 文本,或给 GitHub repo(owner/name)+ 路径。
export const importSkill = (body: { markdown?: string; repo?: string; path?: string; ref?: string }) => jpost<{ ok: boolean; id?: string; error?: string; source_url?: string }>("/skills/import", body);

// ---- 问题8 MCP 中枢 ----
export type McpServer = { id: string; name: string; provider?: string; enabled?: boolean; status?: string; message?: string; key_configured?: boolean; capabilities?: string[]; path?: string } & Record<string, any>;
export type McpStatus = { ok: boolean; summary?: { ready: number; total: number; needs_key: number; disabled: number }; servers: McpServer[] };
export const getMcpStatus = () => jget<McpStatus>("/mcp/status");
export const patchMcpSettings = (settings: Record<string, any>) => jpatch<{ ok: boolean; status: McpStatus }>("/mcp/settings", { settings });

// ---- D 版本化文档 ----
export type DocMeta = { id: string; title: string; kind: string; tags: string[]; updated_ts?: number };
export type DocFull = DocMeta & { content: string };
export type DocVersion = { id: string; reason: string; created_ts: number };
export const getDocuments = () => jget<{ ok: boolean; documents: DocMeta[] }>("/documents");
export const getDocument = (id: string) => jget<{ ok: boolean; document: DocFull | null; versions: DocVersion[] }>(`/documents/${encodeURIComponent(id)}`);
export const createDocument = (title: string, content = "") => jpost<{ ok: boolean; document: DocFull }>("/documents", { title, content });
export const editDocument = (id: string, find: string, replace: string) => jpost<{ ok: boolean; replaced?: number; error?: string }>(`/documents/${encodeURIComponent(id)}/edit`, { find, replace });

// ---- V4 可信执行层：审计账本 + 一键回滚 + 行动预演沙箱 ----
export type AuditLog = {
  id: string; ts: number; tool: string; args: string; output_summary: string;
  risk: string; status: string; approved_by: string; reversible: boolean;
  undo_ref: string | null; duration_ms: number;
};
export type AuditPage = { ok: boolean; total: number; limit: number; offset: number; items: AuditLog[] };
export const getAuditLogs = (q: { tool?: string; status?: string; risk?: string; limit?: number; offset?: number } = {}) => {
  const p = new URLSearchParams();
  if (q.tool) p.set("tool", q.tool);
  if (q.status) p.set("status", q.status);
  if (q.risk) p.set("risk", q.risk);
  p.set("limit", String(q.limit ?? 50));
  p.set("offset", String(q.offset ?? 0));
  return jget<AuditPage>(`/audit/logs?${p.toString()}`);
};
export const undoAudit = (id: string) => jpost<{ ok: boolean; undone?: boolean; kind?: string; result?: string; reverse_command?: string; error?: string }>(`/audit/${encodeURIComponent(id)}/undo`);

export type ShellPreview = {
  ok: boolean; command: string; risk: string; blocked: boolean; block_reason?: string;
  dry_run_ran: boolean; dry_run_output?: string; expected_impact: string;
  reversible_command: string | null; reversible_hint: string;
};
export const previewShell = (command: string) => jpost<ShellPreview>("/agent/preview", { command });
