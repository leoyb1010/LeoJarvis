const BASE = "http://127.0.0.1:8787";

export type BriefingItem = {
  event_id: string;
  title: string;
  url?: string;
  domain: "business" | "life";
  source: string;
  kind: string;
  score: number;
  take: string;
  triage: "notify" | "digest";
};

export type BriefingData = {
  generated_at: number;
  business: BriefingItem[];
  life: BriefingItem[];
  counts: { business: number; life: number };
};

export async function getBriefing(): Promise<BriefingData> {
  const res = await fetch(`${BASE}/briefing/today`);
  if (!res.ok) throw new Error(`briefing failed: ${res.status}`);
  return res.json();
}

export async function getEvents(hours = 24) {
  const res = await fetch(`${BASE}/events?hours=${hours}`);
  if (!res.ok) throw new Error(`events failed: ${res.status}`);
  return res.json();
}

export async function runIngest() {
  const res = await fetch(`${BASE}/ingest/run`, { method: "POST" });
  if (!res.ok) throw new Error(`ingest failed: ${res.status}`);
  return res.json();
}

export async function sendFeedback(event_id: string, signal: "important" | "useless") {
  const res = await fetch(`${BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id, signal }),
  });
  if (!res.ok) throw new Error(`feedback failed: ${res.status}`);
  return res.json();
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
  const res = await fetch(`${BASE}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error(`agent chat failed: ${res.status}`);
  return res.json();
}

export async function approveAction(id: string, decision: "approve" | "reject") {
  const res = await fetch(`${BASE}/agent/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, decision }),
  });
  if (!res.ok) throw new Error(`approve failed: ${res.status}`);
  return res.json();
}

// ---------- 能力模块 ----------

export type ServiceRow = {
  name: string; port: number; online: boolean; pid: string | null; can_restart: boolean;
};
export async function getServices(): Promise<ServiceRow[]> {
  return (await fetch(`${BASE}/services`)).json();
}

export type SystemStatus = { raw: string };
export async function getSystemStatus(): Promise<SystemStatus> {
  return (await fetch(`${BASE}/system/status`)).json();
}

export type AgentRow = {
  id: string; name: string; command: string; pid: number; status: string; started: number;
};
export async function getAgents(): Promise<AgentRow[]> {
  return (await fetch(`${BASE}/agents`)).json();
}

export type JournalRow = { id: string; ts: number; title: string; content: string };
export async function getJournal(q = ""): Promise<JournalRow[]> {
  return (await fetch(`${BASE}/journal?q=${encodeURIComponent(q)}`)).json();
}
export async function addJournal(text: string) {
  return (await fetch(`${BASE}/journal`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  })).json();
}

export type MemoryRow = {
  id: string; type: string; subject: string | null; statement: string;
  confidence: number; salience: number; updated_ts: number;
};
export async function getMemories(): Promise<MemoryRow[]> {
  return (await fetch(`${BASE}/memories`)).json();
}
export async function runReflect(): Promise<{ created: number; used_llm?: boolean; events?: number; note?: string }> {
  return (await fetch(`${BASE}/memory/reflect`, { method: "POST" })).json();
}

export function connectNotify(onMsg: (m: any) => void) {
  const ws = new WebSocket("ws://127.0.0.1:8787/ws/notify");
  ws.onmessage = (event) => onMsg(JSON.parse(event.data));
  const timer = window.setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 30000);
  ws.addEventListener("close", () => window.clearInterval(timer));
  return ws;
}
