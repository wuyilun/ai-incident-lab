import { useState } from "react";
import type { ReactNode } from "react";
import {
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  GitBranch,
  Layers3,
  Play,
  ShieldCheck,
  Square,
  Terminal,
} from "lucide-react";
import { terminal } from "./types";
import type { Evaluation, Incident, LabEvent } from "./types";
const phases = [
  "detected",
  "investigating",
  "diagnosing",
  "planning",
  "acting",
  "verifying",
  "resolved",
];
const names: Record<string, string> = {
  degrading: "故障演化中",
  detected: "告警触发",
  investigating: "采集证据",
  diagnosing: "定位根因",
  planning: "选择 SOP",
  acting: "执行修复",
  verifying: "验证恢复",
  resolved: "已恢复",
  failed: "执行失败",
  cancelled: "已取消",
};

const asText = (value: unknown) =>
  typeof value === "string" ? value : JSON.stringify(value);

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
  return asText(
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
  incidents: Incident[];
  selected: string;
  onSelect: (id: string) => void;
  busy: boolean;
  onStart: () => void;
  onCancel: () => void;
  visible: LabEvent[];
  replay: boolean;
};
export default function IncidentWorkspace({
  incidents,
  selected,
  onSelect,
  busy,
  onStart,
  onCancel,
  visible,
  replay,
}: Props): ReactNode {
  const [expanded, setExpanded] = useState<number | null>(null);
  const incident = incidents.find((i) => i.id === selected);
  const last = (type: string) =>
    visible.findLast((e) => e.event_type === type)?.payload;
  const hypothesis = last("agent.hypothesis");
  const plan = last("agent.plan");
  const verification = last("agent.verification");
  const evaluation = last("evaluator.result") as Evaluation | undefined;
  const statusEvent = visible.findLast(
    (e) =>
      e.event_type.startsWith("incident.") || e.event_type === "agent.started",
  );
  const status = replay
    ? String(statusEvent?.payload.status ?? "degrading")
    : (incident?.status ?? "idle");
  const trace = visible.filter(
    (e) =>
      e.event_type !== "environment.metric" &&
      e.event_type !== "incident.updated",
  );

  return (
    <section className="panel incident-panel" id="incident">
      <div className="panel-heading">
        <div>
          <span className="section-index">03</span>
          <h2>Incident workspace</h2>
          <span
            className={`status ${["failed", "degrading"].includes(status) ? "warning" : ""}`}
            data-testid="incident-status"
          >
            {names[status] ?? "等待注入"}
          </span>
        </div>
        <div className="inline-controls">
          <select
            aria-label="选择历史事件"
            value={selected}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="" disabled>
              选择事件
            </option>
            {incidents.map((i) => (
              <option key={i.id} value={i.id}>
                {i.id.slice(0, 8)} · {names[i.status]} · seed {i.seed}
              </option>
            ))}
          </select>
          {incident?.status === "detected" && (
            <button disabled={busy} onClick={onStart}>
              <Play size={14} />
              启动 Agent
            </button>
          )}
          {incident && !terminal(incident.status) && (
            <button disabled={busy} onClick={onCancel}>
              <Square size={13} />
              停止
            </button>
          )}
        </div>
      </div>
      <div className="incident-summary">
        <span className="incident-id">
          {incident ? `INC / ${incident.id.slice(0, 8)}` : "NO ACTIVE INCIDENT"}
        </span>
        <strong>
          {incident
            ? replay && status === "degrading"
              ? "故障已注入，等待告警阈值"
              : (incident.alert?.name ?? "故障已注入，等待告警阈值")
            : "准备好观察下一次恢复"}
        </strong>
        <span className="tag">
          {incident?.agent_mode === "llm"
            ? "LLM AGENT"
            : incident?.agent_mode === "external"
              ? "EXTERNAL AGENT"
              : "REFERENCE AGENT"}
        </span>
      </div>
      <div className="lifecycle">
        {phases.map((phase, i) => (
          <div
            key={phase}
            className={`phase ${phases.indexOf(status) > i ? "done" : ""} ${status === phase ? "current" : ""}`}
          >
            <span>
              {phases.indexOf(status) > i ? (
                <Check size={13} />
              ) : (
                String(i + 1).padStart(2, "0")
              )}
            </span>
            {names[phase]}
            {i < phases.length - 1 && <ChevronRight size={14} />}
          </div>
        ))}
      </div>
      <div className="incident-grid">
        <div className="trace">
          <div className="subheading">
            <h3>
              <Terminal size={15} />
              Agent 执行轨迹
            </h3>
            <span>{trace.length} events · MCP</span>
          </div>
          <div className="trace-list" aria-label="Agent 执行轨迹">
            {trace.length ? (
              trace.map((event) => (
                <div
                  key={event.sequence}
                  className={`trace-item ${event.event_type.includes("hypothesis") || event.event_type === "action.completed" ? "highlight" : ""}`}
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
                <CircleDot size={26} />
                <strong>证据从这里开始</strong>
                <p>注入故障后，告警、工具调用、诊断和修复会按发生顺序记录。</p>
              </div>
            )}
          </div>
        </div>
        <div className="diagnosis">
          <div className="subheading">
            <h3>
              <GitBranch size={15} />
              诊断与决策
            </h3>
          </div>
          <label>ROOT CAUSE</label>
          <h3 className="root-cause">
            {hypothesis
              ? `${hypothesis.service} / ${hypothesis.root_cause}`
              : "等待诊断证据"}
          </h3>
          <label>EVIDENCE</label>
          {hypothesis ? (
            <ul className="evidence">
              {(hypothesis.evidence as string[]).map((e, i) => (
                <li key={i}>
                  <CheckCircle2 size={14} />
                  {e}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              Agent 将沿依赖关系调查指标、日志与资源归属。
            </p>
          )}
          <div className="sop-box">
            <span>
              <Layers3 size={15} /> SOP / REMEDIATION
            </span>
            <strong>{plan ? String(plan.sop) : "等待检索操作规程"}</strong>
            {plan && (
              <code>
                {String(plan.action)}({String(plan.target)})
              </code>
            )}
          </div>
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
                  : verification
                    ? "Agent 已验证，等待评估"
                    : "等待恢复验证"}
              </strong>
              <p>
                {evaluation
                  ? `根因 ${evaluation.root_cause_correct ? "正确" : "未匹配"} · ${evaluation.tool_call_count} 次工具调用 · ${evaluation.action_count} 次动作`
                  : "连续健康采样 + 环境实际状态检查"}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
