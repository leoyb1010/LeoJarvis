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
export const getSystemOverview = () => jget<any>("/system/overview");
export const getServices = () => jget<any[]>("/services/discover");

// ---- 情报 / 简报 ----
export const getBriefing = () => jget<any>("/briefing/today?compact=1");
export const getIntelligence = () => jget<any>("/intelligence/overview");
export const getBriefingItem = (id: string) => jget<any>(`/briefing/items/${encodeURIComponent(id)}`);

// ---- 中枢对话（真实）----
export type ChatMsg = { role: "user" | "assistant"; content: string };
export const agentChat = (messages: ChatMsg[]) => jpost<any>("/agent/chat", { messages });
export const approveAction = (id: string, decision: "approve" | "reject") => jpost<any>("/agent/approve", { id, decision });

// ---- 记事 / 通知 ----
export const getNotes = () => jget<any>("/personal-notes");
export const getNotifications = () => jget<any>("/system/notifications");

export function fmtAgo(ts?: number): string {
  if (!ts) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}分`;
  return `${Math.floor(s / 3600)}时`;
}
