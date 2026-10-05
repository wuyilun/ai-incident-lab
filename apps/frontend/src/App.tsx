import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  ChevronRight,
  History,
  BarChart3,
  Radio,
  ShieldCheck,
  Workflow,
  Zap,
} from "lucide-react";
import AgentRegistry from "./AgentRegistry";
import Leaderboard from "./Leaderboard";
import IncidentWorkspace from "./IncidentWorkspace";
import Environment from "./Environment";
import MetricsTimeline from "./MetricsTimeline";
import { agentStatus, api, observations, terminal } from "./types";
import type {
  Agent,
  Benchmark,
  FaultMarker,
  Incident,
  LabEvent,
  Scenario,
  World,
} from "./types";

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("redis-connection-leak");
  const [previewScenario, setPreviewScenario] = useState(false);
  const [environment, setEnvironment] = useState<World | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [selected, setSelected] = useState("");
  const [events, setEvents] = useState<LabEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [agentId, setAgentId] = useState("builtin-reference");
  const [seed, setSeed] = useState(42);
  const [replay, setReplay] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [section, setSection] = useState<
    "workbench" | "agents" | "leaderboard"
  >("workbench");

  const refresh = useCallback(async () => {
    const [items, world, trials, registered, catalog] = await Promise.all([
      api<Incident[]>("/incidents"),
      api<World>("/environment"),
      api<Benchmark[]>("/benchmarks"),
      api<Agent[]>("/agents"),
      api<Scenario[]>("/scenarios"),
    ]);
    setIncidents(items);
    setEnvironment(world);
    setBenchmarks(trials);
    setAgents(registered);
    setScenarios(catalog);
    setSelected((current) => current || items[0]?.id || "");
  }, []);
  useEffect(() => {
    const load = () => void refresh().catch((e) => setError(String(e)));
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    setEvents([]);
    setReplay(false);
    setPlaying(false);
    setCursor(0);
    if (!selected) return;
    const stream = new EventSource(
      `/api/events/stream?incident_id=${selected}`,
    );
    let refreshTimer: ReturnType<typeof setTimeout>;
    stream.onopen = () => setConnected(true);
    stream.onerror = () => setConnected(false);
    stream.onmessage = (message) => {
      const event = JSON.parse(message.data) as LabEvent;
      setEvents((current) =>
        current.some((e) => e.sequence === event.sequence)
          ? current
          : [...current, event].sort((a, b) => a.sequence - b.sequence),
      );
      if (
        event.event_type.startsWith("incident.") ||
        event.event_type === "evaluator.result"
      ) {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(
          () => void refresh().catch((e) => setError(String(e))),
          150,
        );
      }
    };
    return () => {
      clearTimeout(refreshTimer);
      stream.close();
      setConnected(false);
    };
  }, [selected, refresh]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () => setCursor((current) => Math.min(current + 1, events.length - 1)),
      170,
    );
    return () => clearInterval(timer);
  }, [playing, events.length]);
  useEffect(() => {
    if (playing && cursor >= events.length - 1) setPlaying(false);
  }, [cursor, events.length, playing]);

  const incident = incidents.find((i) => i.id === selected);
  const active = incidents.some((i) => !terminal(i.status));
  const scenario = scenarios.find((item) => item.id === scenarioId);
  const incidentScenario = scenarios.find(
    (item) => item.id === incident?.scenario_id,
  );
  const selectedAgent = agents.find((a) => a.id === agentId);
  const ready =
    selectedAgent?.enabled &&
    ["ready", "online"].includes(selectedAgent.connection_status);
  const benchmarkBusy = benchmarks.some((b) => b.status === "running");
  const visible = useMemo(
    () => (replay ? events.slice(0, cursor + 1) : events),
    [events, replay, cursor],
  );
  const snapshots = observations(visible);
  const world =
    !replay && previewScenario
      ? environment
      : (snapshots.at(-1) ??
        (replay ? null : (incident?.after ?? incident?.latest ?? environment)));
  const baseline = snapshots[0];
  const injection = visible.find(
    (event) => event.event_type === "fault.injected",
  );
  const injectedTarget =
    typeof injection?.payload.target === "string"
      ? injection.payload.target
      : injection
        ? incidentScenario?.target
        : undefined;
  const fault: FaultMarker | undefined =
    !replay && (!incident || previewScenario) && scenario
      ? { target: scenario.target, label: scenario.name, phase: "preview" }
      : injectedTarget
        ? {
            target: injectedTarget,
            label: incidentScenario?.name ?? "已记录的故障注入",
            phase: visible.some(
              (event) => event.event_type === "incident.resolved",
            )
              ? "recovered"
              : "injected",
          }
        : undefined;
  async function perform(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  function seek(value: number) {
    setPreviewScenario(false);
    setReplay(true);
    setPlaying(false);
    setCursor(value);
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          href="#workbench"
          className="brand"
          onClick={() => setSection("workbench")}
        >
          <span className="brand-icon">
            <Workflow size={23} />
          </span>
          <span>
            incident<span className="brand-lab">lab</span>
            <small>AGENT OPERATIONS</small>
          </span>
        </a>
        <div className="workspace">
          <span className="dot green" />
          Local workspace<span className="version">v0.3</span>
        </div>
        <nav aria-label="主导航">
          <button
            className={`nav-item ${section === "workbench" ? "selected" : ""}`}
            onClick={() => setSection("workbench")}
          >
            <Activity size={18} />
            <span>故障实验台</span>
          </button>
          <button
            className={`nav-item ${section === "agents" ? "selected" : ""}`}
            onClick={() => setSection("agents")}
          >
            <Bot size={18} />
            <span>Agent 接入中心</span>
            <span className="nav-count">{agents.length}</span>
          </button>
          <button
            className={`nav-item ${section === "leaderboard" ? "selected" : ""}`}
            onClick={() => setSection("leaderboard")}
          >
            <BarChart3 size={18} />
            <span>Agent 排行榜</span>
          </button>
        </nav>
        <div className="sidebar-note">
          <Radio size={20} />
          <strong>观察每一次恢复</strong>
          <p>
            环境的变化与 Agent 的行动，
            <br />
            在同一条时间线上相遇。
          </p>
          <span>OBSERVE → ACT → VERIFY</span>
        </div>
        <div className="sidebar-footer">
          <ShieldCheck size={14} />
          MCP · 安全动作策略<small>模拟环境 / 持久化事件回放</small>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div>
            Workspace
            <ChevronRight size={13} />
            <strong>
              {section === "agents"
                ? "Agent registry"
                : section === "leaderboard"
                  ? "Agent leaderboard"
                  : "Incident workbench"}
            </strong>
          </div>
          <span className="connection">
            <span
              className={`dot ${connected || !selected ? "green" : "orange"}`}
            />
            {connected
              ? "事件流已连接"
              : selected
                ? "事件流重连中"
                : "等待实验"}
          </span>
        </header>
        <main id="workbench">
          {error && (
            <div role="alert" className="error-banner">
              {error}
              <button onClick={() => setError("")} aria-label="关闭错误">
                ×
              </button>
            </div>
          )}
          {section === "agents" ? (
            <AgentRegistry agents={agents} onRefresh={refresh} />
          ) : section === "leaderboard" ? (
            <Leaderboard scenarios={scenarios} />
          ) : (
            <>
              <div className="compact-heading">
                <div>
                  <span className="eyebrow">ENVIRONMENT ↔ AGENT</span>
                  <h1>故障实验台</h1>
                  <p>注入故障，观察告警如何驱动 Agent 完成诊断与恢复。</p>
                </div>
                <label className="history-select">
                  <History size={15} />
                  <select
                    aria-label="选择历史事件"
                    value={selected}
                    onChange={(e) => {
                      setSelected(e.target.value);
                      setPreviewScenario(false);
                    }}
                  >
                    <option value="" disabled>
                      暂无历史实验
                    </option>
                    {incidents.map((i) => (
                      <option value={i.id} key={i.id}>
                        {i.id.slice(0, 8)} · {i.status} · seed {i.seed}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <section className="experiment panel" aria-label="故障实验配置">
                <div className="experiment-copy">
                  <span className="experiment-icon">
                    <Zap size={19} />
                  </span>
                  <div>
                    <h3>{world?.name ?? "微服务模拟环境"}</h3>
                    <p>
                      {scenario?.description ??
                        "选择故障场景，观察服务依赖与告警变化"}
                    </p>
                  </div>
                </div>
                <div className="experiment-controls">
                  <label>
                    故障场景
                    <select
                      aria-label="故障场景"
                      value={scenarioId}
                      disabled={active}
                      onChange={(e) => {
                        setScenarioId(e.target.value);
                        setPreviewScenario(true);
                      }}
                    >
                      {scenarios.map((item) => (
                        <option value={item.id} key={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    响应 Agent
                    <select
                      aria-label="响应 Agent"
                      value={agentId}
                      onChange={(e) => setAgentId(e.target.value)}
                    >
                      {agents.map((a) => (
                        <option
                          value={a.id}
                          key={a.id}
                          disabled={
                            !a.enabled ||
                            ["unavailable", "offline", "disabled"].includes(
                              a.connection_status,
                            )
                          }
                        >
                          {a.name} · {agentStatus[a.connection_status]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    随机种子
                    <input
                      aria-label="随机种子"
                      type="number"
                      min={0}
                      max={4294967295}
                      value={seed}
                      onChange={(e) => setSeed(Number(e.target.value))}
                    />
                  </label>
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      active ||
                      benchmarkBusy ||
                      !ready ||
                      !scenario ||
                      !Number.isInteger(seed) ||
                      seed < 0 ||
                      seed > 4294967295
                    }
                    onClick={() =>
                      void perform(async () => {
                        const item = await api<Incident>("/incidents", {
                          method: "POST",
                          body: JSON.stringify({
                            scenario_id: scenarioId,
                            seed,
                            auto_agent: true,
                            agent_id: agentId,
                          }),
                        });
                        setSelected(item.id);
                        setPreviewScenario(false);
                      })
                    }
                  >
                    <Zap size={15} />
                    {active ? "实验进行中" : "注入故障"}
                  </button>
                </div>
              </section>
              {!ready && !active && (
                <p className="inline-notice">
                  请在 Agent 接入中心连接或启用响应 Agent，再注入故障。
                </p>
              )}
              <div className="workbench-grid">
                <div data-testid="workbench-environment">
                  <Environment
                    world={world}
                    fault={fault}
                    replay={replay}
                    before={baseline?.metrics}
                  />
                </div>
                <IncidentWorkspace
                  key={selected}
                  incident={incident}
                  busy={busy}
                  visible={visible}
                  replay={replay}
                  onStart={() =>
                    void perform(() =>
                      api(`/incidents/${selected}/agent`, {
                        method: "POST",
                        body: JSON.stringify({ agent_id: agentId }),
                      }),
                    )
                  }
                  onCancel={() =>
                    void perform(() =>
                      api(`/incidents/${selected}/agent`, { method: "DELETE" }),
                    )
                  }
                />
              </div>
              <MetricsTimeline
                key={selected}
                defaultMetric={incidentScenario?.metric ?? scenario?.metric}
                events={events}
                visible={visible}
                replay={replay}
                cursor={cursor}
                playing={playing}
                onSeek={seek}
                onToggle={() => {
                  setReplay(true);
                  if (cursor >= events.length - 1) setCursor(0);
                  setPlaying(!playing);
                }}
                onLive={() => {
                  setReplay(false);
                  setPlaying(false);
                }}
              />
            </>
          )}
          <footer>
            <span>INCIDENT LAB / SIMULATION</span>
            <span>
              <ShieldCheck size={12} />
              证据驱动诊断 · 安全策略执行 · 独立验证恢复
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
