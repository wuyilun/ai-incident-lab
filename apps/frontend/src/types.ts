export type Metrics = {
  [key: string]: number;
  redis_connections: number;
  redis_latency_ms: number;
  api_latency_ms: number;
  api_error_rate: number;
  worker_open_clients: number;
};
export type World = {
  environment_id?: string;
  name?: string;
  tick: number;
  metrics: Metrics;
  services: {
    name: string;
    label?: string;
    kind?: string;
    tier?: number;
    status: string;
    health?: "healthy" | "degraded" | "unavailable";
    restarts: number;
    metrics?: Record<string, number>;
  }[];
  dependencies: {
    from: string;
    to: string;
    kind?: string;
    label?: string;
    affected?: boolean;
  }[];
  healthy_ticks: number;
};
export type FaultMarker = {
  target: string;
  label: string;
  phase: "preview" | "injected" | "recovered";
};
export type Evaluation = {
  incident_resolved: boolean;
  environment_recovered: boolean;
  root_cause_correct: boolean;
  affected_service_correct: boolean;
  recovery_verified: boolean;
  denied_action_count: number;
  unsafe_action_count: number;
  forbidden_action_count: number;
  action_count: number;
  tool_call_count: number;
  time_to_recovery_seconds: number | null;
};
export type Incident = {
  id: string;
  run_id: string;
  scenario_id: string;
  seed: number;
  status: string;
  agent_mode: string;
  agent_id?: string;
  agent_name?: string;
  alert: { name: string; status: string } | null;
  before: World;
  after?: World;
  latest?: World;
  evaluation: Evaluation | null;
  summary?: string;
};
export type Agent = {
  id: string;
  name: string;
  kind: "reference" | "llm" | "external";
  description: string;
  enabled: boolean;
  connection_status:
    "ready" | "online" | "offline" | "disabled" | "busy" | "unavailable";
  last_seen: string | null;
  created_at: string;
};
export type Credentials = {
  agent_id: string;
  token: string;
  poll_path: string;
  mcp_path?: string;
};
export type Scenario = {
  id: string;
  name: string;
  target: string;
  fault_type: string;
  description: string;
  metric?: string;
};
export type LeaderboardEntry = {
  agent_id: string;
  agent_name: string;
  agent_kind: Agent["kind"];
  rank: number | null;
  sample_count: number;
  resolution_rate: number | null;
  diagnosis_accuracy: number | null;
  safety_rate: number | null;
  scenario_count: number;
  average_mttr_seconds: number | null;
  average_tool_calls: number | null;
  score: number | null;
};
export type LeaderboardData = {
  scenario_id: string | null;
  total_scenarios: number;
  entries: LeaderboardEntry[];
  ranking_method: string;
};
export const agentStatus: Record<Agent["connection_status"], string> = {
  ready: "就绪",
  online: "在线",
  offline: "离线",
  disabled: "已停用",
  busy: "执行中",
  unavailable: "不可用",
};
export const agentKind: Record<Agent["kind"], string> = {
  reference: "Reference",
  llm: "LLM",
  external: "外部 Agent",
};
export type LabEvent = {
  sequence: number;
  event_id: string;
  timestamp: string;
  event_type: string;
  source: string;
  incident_id: string | null;
  run_id: string | null;
  payload: Record<string, unknown>;
};
export function observations(events: LabEvent[]): World[] {
  return events.flatMap((event) => {
    if (
      ["environment.metric", "environment.state_changed"].includes(
        event.event_type,
      )
    )
      return [event.payload as World];
    if (event.event_type === "action.completed" && event.payload.after)
      return [event.payload.after as World];
    return [];
  });
}
export type Benchmark = {
  id: string;
  status: string;
  results: unknown[];
  aggregate?: {
    resolution_rate: number;
    diagnosis_accuracy: number;
    safety_rate: number;
    average_tool_calls: number;
    average_actions: number;
    average_mttr_seconds: number | null;
  };
};
export const terminal = (status: string) =>
  ["resolved", "failed", "cancelled"].includes(status);
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail),
    );
  return body as T;
}
