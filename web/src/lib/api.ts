export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TraceStep = { step: string; cypher: string; params: Record<string, unknown> };

export type Fact = {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  kind: "identity" | "preference" | "goal" | "state";
  status: string;
  valid_from: number;
  valid_to: number | null;
  confidence: number;
  asserted_by: string;
  hits: number;
  strength?: number;
  sources?: string[];
  match?: string;
  replaced?: string | null;
};

export type GraphNode = { id: string; label: string; type: "entity" | "fact"; fact?: Fact; x?: number; y?: number };
export type GraphLink = { source: string | GraphNode; target: string | GraphNode; type: string; status?: string };
export type Snapshot = { nodes: GraphNode[]; links: GraphLink[]; time_range: [number | null, number | null]; session: number };

export type Contradiction = { fact_id: string; new: Fact; old: Fact };

export type StaleDecision = {
  decision_id: string;
  decision: string;
  reason: string | null;
  decided_at: number;
  stale_since: number | null;
  was_based_on: string[];
  now_believed: string[];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}

const u = (user: string) => `/api/${encodeURIComponent(user)}`;

export const api = {
  config: () => req<{ chat_enabled: boolean; model: string | null }>("/api/config"),
  connect: () => req<{ connected: boolean; url?: string; user?: string }>("/api/connect"),
  users: () => req<{ users: string[] }>("/api/users"),
  seed: (s: "personal" | "team") => req<{ user: string }>(`/api/seed/${s}`, { method: "POST" }),
  session: (user: string) => req<{ session: number; trace: TraceStep[] }>(`${u(user)}/session`, { method: "POST" }),
  graph: (user: string, asOf?: number) =>
    req<Snapshot>(`${u(user)}/graph${asOf ? `?as_of=${asOf}` : ""}`),
  stats: (user: string) => req<{ facts: Record<string, number>; session: number }>(`${u(user)}/stats`),
  remember: (user: string, body: Record<string, unknown>) =>
    req<Record<string, unknown> & { status: string; trace: TraceStep[] }>(`${u(user)}/remember`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  recall: (user: string, q: string, asOf?: number) =>
    req<{ facts: Fact[]; decayed_hidden: number; trace: TraceStep[] }>(
      `${u(user)}/recall?q=${encodeURIComponent(q)}${asOf ? `&as_of=${asOf}` : ""}`,
    ),
  resolve: (user: string, fact_id: string, keep: "new" | "old" | "both") =>
    req<{ status: string; trace: TraceStep[] }>(`${u(user)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ fact_id, keep }),
    }),
  why: (user: string, topic: string) =>
    req<{ timelines: { key: string; versions: Fact[]; changed: boolean }[]; trace: TraceStep[] }>(
      `${u(user)}/why?topic=${encodeURIComponent(topic)}`,
    ),
  contradictions: (user: string) => req<{ pending: Contradiction[] }>(`${u(user)}/contradictions`),
  staleDecisions: (user: string) => req<{ stale: StaleDecision[]; trace: TraceStep[] }>(`${u(user)}/decisions/stale`),
  allDecisions: (user: string) =>
    req<{ decisions: { id: string; text: string; reason: string; status: string; based_on: string[] }[] }>(`${u(user)}/decisions`),
  resolveDecision: (user: string, decision_id: string, action: "reaffirm" | "revise" | "drop") =>
    req<{ status: string; trace: TraceStep[] }>(`${u(user)}/decisions/resolve`, {
      method: "POST",
      body: JSON.stringify({ decision_id, action }),
    }),
  profile: (user: string) => req<{ entities: { name: string; score: number }[]; trace: TraceStep[] }>(`${u(user)}/profile`),
  sweep: (user: string) => req<{ archived: number; trace: TraceStep[] }>(`${u(user)}/sweep`, { method: "POST" }),
  forget: (user: string, id: string) => req<{ trace: TraceStep[] }>(`${u(user)}/forget/${id}`, { method: "POST" }),
  chat: (user: string, messages: { role: string; content: string }[]) =>
    req<{ reply: string; steps: { tool: string; args: Record<string, unknown>; result: Record<string, unknown> & { trace?: TraceStep[] } }[] }>(
      `${u(user)}/chat`,
      { method: "POST", body: JSON.stringify({ messages }) },
    ),
};

export const fmt = (ms?: number | null) =>
  ms ? new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "now";
