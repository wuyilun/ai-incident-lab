import { useEffect, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Download,
  FileCheck2,
  Play,
  ShieldCheck,
  Square,
  Terminal,
} from "lucide-react";
import { observations, terminal } from "./types";
import type { Evaluation, Incident, LabEvent, Metrics } from "./types";
import { fmt, metricLabel, metricUnit } from "./format";

const names: Record<string, string> = {
  degrading: "故障演化中",
  detected: "告警触发",
  dispatching: "等待 Agent 接收",
  investigating: "采集证据",
  diagnosing: "定位根因",
  planning: "选择 SOP",
  acting: "执行修复",
  verifying: "验证恢复",
  resolved: "已恢复",
  failed: "执行失败",
  cancelled: "已取消",
};
const eventPhases: Record<string, string> = {
  "fault.injected": "degrading",
  "alert.generated": "detected",
  "alert.dispatched": "dispatching",
  "agent.alert_received": "investigating",
  "agent.started": "investigating",
  "agent.hypothesis": "diagnosing",
  "agent.plan": "planning",
  "action.completed": "acting",
  "agent.verification": "verifying",
  "incident.resolved": "resolved",
  "incident.failed": "failed",
  "incident.cancelled": "cancelled",
};
const text = (value: unknown) =>
  typeof value === "string" ? value : (JSON.stringify(value) ?? "未产生");
function describe(event: LabEvent): string {
  const p = event.payload;
  if (event.event_type === "agent.tool_call")
    return `${p.tool}(${JSON.stringify(p.arguments)})`;
  if (event.event_type === "agent.tool_result")
    return `${p.tool} · ${p.error ? "ERROR" : "响应已记录"}`;
  if (event.event_type === "agent.hypothesis")
    return `${p.service} → ${p.root_cause}`;
  if (event.event_type === "action.completed")
    return `${p.tool}(${p.target}) · 执行完成`;
  if (event.event_type === "action.attempted")
    return `${p.decision} · ${p.tool}(${p.target})`;
  if (event.event_type === "agent.plan")
    return `${p.sop} → ${p.action}(${p.target})`;
  if (event.event_type === "agent.alert_received")
    return "Agent 已接收告警，开始诊断";
  if (event.event_type === "alert.dispatched") return "告警已投递到响应 Agent";
  return text(
    p.summary ??
      p.decision ??
      p.name ??
      p.status ??
      p.evidence ??
      p.skill ??
      event.event_type,
  );
}

type Props = {
  incident?: Incident;
  busy: boolean;
  onStart: () => void;
  onCancel: () => void;
  visible: LabEvent[];
  replay: boolean;
};
export default function IncidentWorkspace({
  incident,
  busy,
  onStart,
  onCancel,
  visible,
  replay,
}: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [tab, setTab] = useState<"trace" | "report">("trace");
  const traceEnd = useRef<HTMLDivElement>(null);
  const last = (type: string) =>
    visible.findLast((e) => e.event_type === type)?.payload;
  const hypothesis = last("agent.hypothesis");
  const plan = last("agent.plan");
  const verification = last("agent.verification");
  const evaluation = last("evaluator.result") as Evaluation | undefined;
  const alert = last("alert.generated");
  const received = last("agent.alert_received") ?? last("agent.started");
  const observedStatus = visible
    .map((e) => {
      if (
        e.event_type.startsWith("incident.") ||
        e.event_type.startsWith("agent.")
      ) {
        const phase = e.payload.phase ?? e.payload.status;
        if (typeof phase === "string" && phase in names) return phase;
      }
      return eventPhases[e.event_type];
    })
    .findLast(Boolean);
  const status = replay
    ? (observedStatus ?? "degrading")
    : (incident?.status ?? "idle");
  const trace = visible.filter(
    (e) =>
      ![
        "environment.metric",
        "environment.state_changed",
        "incident.updated",
      ].includes(e.event_type),
  );
  const actions = visible.filter((e) => e.event_type === "action.completed");
  const attempts = visible.filter((e) => e.event_type === "action.attempted");
  const snapshots = observations(visible);
  const before = snapshots[0];
  const after = snapshots.at(-1);
  const metricKeys = Object.keys(after?.metrics ?? {});
  const peak = (key: keyof Metrics) => {
    const values = snapshots
      .map((snapshot) => snapshot.metrics[key])
      .filter((value) => Number.isFinite(value));
    return values.length ? Math.max(...values) : undefined;
  };
  const identity =
    incident?.agent_name ?? `${incident?.agent_mode ?? "Reference"} Agent`;
  const evidence = Array.isArray(hypothesis?.evidence)
    ? hypothesis.evidence
    : [];
  const summary = visible.findLast((e) =>
    ["incident.resolved", "incident.failed", "incident.cancelled"].includes(
      e.event_type,
    ),
  )?.payload.summary;
  useEffect(() => {
    const list = traceEnd.current?.parentElement;
    if (!replay && tab === "trace" && list) list.scrollTop = list.scrollHeight;
  }, [visible.length, replay, tab]);
  function download() {
    const report = {
      incident_id: incident?.id,
      agent: {
        id: incident?.agent_id,
        name: identity,
        kind: incident?.agent_mode,
      },
      through_sequence: visible.at(-1)?.sequence,
      status,
      diagnosis: hypothesis ?? null,
      plan: plan ?? null,
      actions: actions.map((e) => e.payload),
      safety_decisions: attempts.map((e) => e.payload),
      verification: verification ?? null,
      evaluation: evaluation ?? null,
      summary: summary ?? null,
      metrics: {
        baseline: before?.metrics ?? null,
        peak: Object.fromEntries(metricKeys.map((key) => [key, peak(key)])),
        current: after?.metrics ?? null,
      },
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `incident-${incident?.id ?? "report"}-${visible.at(-1)?.sequence ?? 0}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section
      className="panel incident-panel"
      id="incident"
      data-testid="workbench-agent"
    >
      <div className="panel-heading">
        <h2>
          <Bot size={18} />
          Agent 执行现场
        </h2>
        <span
          className={`status ${["failed", "degrading", "dispatching"].includes(status) ? "warning" : ""}`}
          data-testid="incident-status"
        >
          {names[status] ?? "等待注入"}
        </span>
      </div>
      <div className="agent-identity">
        <span className="agent-avatar">
          <Bot size={21} />
        </span>
        <div>
          <strong>{incident ? identity : "等待响应 Agent"}</strong>
          <small>
            {incident
              ? `INC / ${incident.id.slice(0, 8)} · ${incident.agent_mode.toUpperCase()}`
              : "注册、连接，然后开始一次实验"}
          </small>
        </div>
        <div className="inline-controls">
          {!replay && incident?.status === "detected" && (
            <button disabled={busy} onClick={onStart}>
              <Play size={13} />
              启动 Agent
            </button>
          )}
          {!replay && incident && !terminal(incident.status) && (
            <button disabled={busy} onClick={onCancel}>
              <Square size={12} />
              停止
            </button>
          )}
        </div>
      </div>
      <div className={`alert-receipt ${received ? "received" : ""}`}>
        <CircleDot size={14} />
        <div>
          <strong>
            {received
              ? "Agent 已接收告警"
              : last("alert.dispatched")
                ? "告警已投递，等待 Agent 确认"
                : alert
                  ? "告警已触发"
                  : "等待故障触发告警"}
          </strong>
          <p>
            {alert
              ? text(alert.name)
              : "环境超过告警阈值后，将自动通知所选 Agent。"}
          </p>
        </div>
      </div>
      <div className="workspace-tabs" role="tablist" aria-label="Agent 视图">
        <button
          role="tab"
          aria-selected={tab === "trace"}
          aria-controls="agent-trace-panel"
          id="trace-tab"
          onClick={() => setTab("trace")}
        >
          <Terminal size={14} />
          执行过程<span>{trace.length}</span>
        </button>
        <button
          role="tab"
          aria-selected={tab === "report"}
          aria-controls="agent-report-panel"
          id="report-tab"
          onClick={() => setTab("report")}
        >
          <FileCheck2 size={14} />
          诊断报告{evaluation && <span>已评估</span>}
        </button>
      </div>
      {tab === "trace" ? (
        <div
          id="agent-trace-panel"
          role="tabpanel"
          aria-labelledby="trace-tab"
          className="trace-list"
          aria-label="Agent 执行轨迹"
        >
          {trace.length ? (
            trace.map((event) => (
              <div
                className={`trace-item ${["agent.hypothesis", "action.completed", "incident.resolved"].includes(event.event_type) ? "highlight" : ""}`}
                key={event.sequence}
              >
                <button
                  onClick={() =>
                    setExpanded(
                      expanded === event.sequence ? null : event.sequence,
                    )
                  }
                  aria-expanded={expanded === event.sequence}
                >
                  <time>
                    {new Date(event.timestamp).toLocaleTimeString("zh-CN", {
                      hour12: false,
                    })}
                  </time>
                  <span className="trace-dot" />
                  <div>
                    <small>{event.event_type}</small>
                    <p>{describe(event)}</p>
                  </div>
                  <ChevronRight size={13} />
                </button>
                {expanded === event.sequence && (
                  <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                )}
              </div>
            ))
          ) : (
            <div className="empty">
              <CircleDot size={28} />
              <strong>从一条告警开始</strong>
              <p>接收告警、MCP 调查、诊断与修复将依次出现在这里。</p>
            </div>
          )}
          <div ref={traceEnd} />
        </div>
      ) : (
        <div
          id="agent-report-panel"
          role="tabpanel"
          aria-labelledby="report-tab"
          className="diagnosis"
          data-testid="diagnosis-report"
        >
          <div className="report-heading">
            <span>{replay ? "当前回放时刻的报告" : "当前实验诊断报告"}</span>
            <button disabled={!incident || !visible.length} onClick={download}>
              <Download size={13} />
              下载报告
            </button>
          </div>
          <label>根因诊断</label>
          <h3 className="root-cause">
            {hypothesis
              ? `${hypothesis.service} / ${hypothesis.root_cause}`
              : "未产生诊断"}
          </h3>
          <label>诊断证据</label>
          {evidence.length ? (
            <ul className="evidence">
              {evidence.map((e, i) => (
                <li key={i}>
                  <CheckCircle2 size={14} />
                  {text(e)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">未产生证据</p>
          )}
          <div className="sop-box">
            <label>修复 SOP</label>
            <strong>{plan ? text(plan.sop) : "未产生修复计划"}</strong>
            {plan && (
              <code>
                {text(plan.action)}({text(plan.target)})
              </code>
            )}
          </div>
          <label>实际执行动作</label>
          {actions.length ? (
            <ul className="evidence">
              {actions.map((e) => (
                <li key={e.sequence}>
                  <CheckCircle2 size={14} />
                  {describe(e)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">未执行修复动作</p>
          )}
          {attempts.some((e) => e.payload.decision !== "ALLOW") && (
            <p className="denied">
              安全策略已拦截{" "}
              {attempts.filter((e) => e.payload.decision !== "ALLOW").length}{" "}
              次动作尝试，详情见执行过程。
            </p>
          )}
          <label>Agent 恢复验证</label>
          {verification ? (
            <pre className="artifact">
              {JSON.stringify(verification, null, 2)}
            </pre>
          ) : (
            <p className="muted">未产生验证结果</p>
          )}
          <div
            className={`verification ${evaluation?.incident_resolved ? "passed" : ""}`}
          >
            <ShieldCheck size={22} />
            <div>
              <strong>
                {evaluation
                  ? evaluation.incident_resolved
                    ? "独立评估：恢复通过"
                    : "独立评估：未通过"
                  : "独立评估：未产生"}
              </strong>
              {evaluation && (
                <p>
                  根因 {evaluation.root_cause_correct ? "正确" : "未匹配"} ·{" "}
                  {evaluation.tool_call_count} 次工具调用 ·{" "}
                  {evaluation.action_count} 次动作
                </p>
              )}
            </div>
          </div>
          {evaluation && (
            <dl className="evaluation-grid">
              <div>
                <dt>环境恢复</dt>
                <dd>{evaluation.environment_recovered ? "通过" : "未通过"}</dd>
              </div>
              <div>
                <dt>持续恢复验证</dt>
                <dd>{evaluation.recovery_verified ? "通过" : "未通过"}</dd>
              </div>
              <div>
                <dt>责任服务</dt>
                <dd>
                  {evaluation.affected_service_correct ? "正确" : "未匹配"}
                </dd>
              </div>
              <div>
                <dt>恢复耗时</dt>
                <dd>
                  {fmt(evaluation.time_to_recovery_seconds ?? undefined, "s")}
                </dd>
              </div>
              <div>
                <dt>策略拒绝</dt>
                <dd>{evaluation.denied_action_count} 次</dd>
              </div>
              <div>
                <dt>不安全 / 禁止动作</dt>
                <dd>
                  {evaluation.unsafe_action_count} /{" "}
                  {evaluation.forbidden_action_count}
                </dd>
              </div>
            </dl>
          )}
          <label>指标变化 · 基线 → 故障峰值 → 当前时刻</label>
          <div className="report-metrics">
            {metricKeys.map((key) => (
              <span key={key}>
                {metricLabel(key)}
                <strong>
                  {fmt(before?.metrics[key])} → {fmt(peak(key))} →{" "}
                  {fmt(after?.metrics[key])} {metricUnit(key)}
                </strong>
              </span>
            ))}
            {!metricKeys.length && (
              <p className="muted">当前时刻未产生指标采样</p>
            )}
          </div>
          <label>最终结论</label>
          <p className="report-summary">
            {summary ? text(summary) : "未产生最终结论"}
          </p>
        </div>
      )}
    </section>
  );
}
