export type Metrics = {
  redis_connections: number;
  redis_latency_ms: number;
  api_latency_ms: number;
  api_error_rate: number;
  worker_open_clients: number;
};
export type World = {
  tick: number;
  metrics: Metrics;
  services: { name: string; status: string; restarts: number }[];
  dependencies: { from: string; to: string }[];
  healthy_ticks: number;
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
  alert: { name: string; status: string } | null;
  before: World;
  after?: World;
  latest?: World;
  evaluation: Evaluation | null;
  summary?: string;
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
