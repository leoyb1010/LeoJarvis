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
export type IntelRepo = { repo_full_name?: string; description?: string; display_description?: string; summary_zh?: string; language?: string; stars?: number; forks?: number; stars_per_day?: number; delta_24h?: number; momentum_score?: number; url?: string; topics?: string[]; display_topics?: string[] } & Record<string, any>;
export type IntelSource = { id?: string; type?: string; name?: string; url?: string; domain?: string; enabled?: number; last_scan_ts?: number | null } & Record<string, any>;
export type IntelTarget = { id?: string; label?: string; kind?: string; query?: string; enabled?: number } & Record<string, any>;
export type Intelligence = { github?: IntelRepo[]; sources?: IntelSource[]; targets?: IntelTarget[]; stats?: Record<string, number> } & Record<string, any>;
export const getIntelligence = () => jget<Intelligence>("/intelligence/overview");

// briefing/items/{id}: { ok, item:{ title, source, source_detail(中文全文正文), source_detail_translated, why_important, take, next_step, reasons[], url, score, ts, priority, ... } }
export type BriefDetailItem = { title?: string; source?: string; source_detail?: string; source_detail_translated?: boolean; source_detail_missing?: boolean; why_important?: string; take?: string; next_step?: string; reasons?: string[]; url?: string; score?: number; ts?: number; priority?: string; relation?: string } & Record<string, any>;
export const getBriefingItem = (id: string) => jget<{ ok?: boolean; item?: BriefDetailItem }>(`/briefing/items/${encodeURIComponent(id)}`);

// ---- 中枢对话（真实）----
export type ChatMsg = { role: "user" | "assistant"; content: string };
export type ChatStep = { tool: string; args?: any; status: string; result?: string };
export type PendingAction = { id: string; tool?: string; args?: any; reason?: string } & Record<string, any>;
export type ChatReply = { reply?: string; steps?: ChatStep[]; pending_actions?: PendingAction[] } & Record<string, any>;
export const agentChat = (messages: ChatMsg[]) => jpost<ChatReply>("/agent/chat", { messages });
export const approveAction = (id: string, decision: "approve" | "reject") => jpost<ChatReply>("/agent/approve", { id, decision });

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
