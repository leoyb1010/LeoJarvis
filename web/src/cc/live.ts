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

// ---- CLI agent 编排（真实）----
export type CliAgent = { name: string; display: string; installed: boolean; version: string | null; auth: string; run_supported: string };
export type CliSession = { id: string; agent: string; name: string; prompt: string; status: string; started: number; pid: number; output: string };
export const getCliAgents = () => jget<{ agents: CliAgent[] }>("/agents/cli");
export const runCliAgent = (name: string, prompt: string, cwd?: string) => jpost<{ ok: boolean; id?: string; error?: string }>("/agents/cli/run", { name, prompt, cwd });
export const getCliSessions = () => jget<{ sessions: CliSession[] }>("/agents/cli/sessions");
export const stopCliSession = (id: string) => jpost<{ ok: boolean }>(`/agents/cli/sessions/${id}/stop`);

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
export const getIntelligence = () => jget<any>("/intelligence/overview");
export const getBriefingItem = (id: string) => jget<any>(`/briefing/items/${encodeURIComponent(id)}`);

// ---- 中枢对话（真实）----
export type ChatMsg = { role: "user" | "assistant"; content: string };
export type ChatStep = { tool: string; args?: any; status: string; result?: string };
export type PendingAction = { id: string; tool?: string; args?: any; reason?: string } & Record<string, any>;
export type ChatReply = { reply?: string; steps?: ChatStep[]; pending_actions?: PendingAction[] } & Record<string, any>;
export const agentChat = (messages: ChatMsg[]) => jpost<ChatReply>("/agent/chat", { messages });
export const approveAction = (id: string, decision: "approve" | "reject") => jpost<ChatReply>("/agent/approve", { id, decision });

// ---- 记事 / 通知 ----
// notes: { ok, notes:[{ id, title, excerpt, created_ts, updated_ts, ... }], stats }
export type PersonalNote = { id?: string; title?: string; excerpt?: string; content?: string; created_ts?: number; updated_ts?: number } & Record<string, any>;
export const getNotes = () => jget<{ ok?: boolean; notes?: PersonalNote[]; stats?: any }>("/personal-notes");
// notifications: { apps:[{ id, name, count, has_new, icon(base64 dataurl), ... }] }
export type NotifApp = { id: string; name?: string; count?: number; has_new?: boolean; icon?: string } & Record<string, any>;
export const getNotifications = () => jget<{ apps?: NotifApp[] } & Record<string, any>>("/system/notifications");

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
