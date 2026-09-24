import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  ChevronRight,
  FlaskConical,
  Layers3,
  Play,
  RotateCcw,
  ShieldCheck,
  Terminal,
  Workflow,
  Zap,
} from "lucide-react";
import IncidentWorkspace from "./IncidentWorkspace";
import Environment from "./Environment";
import MetricsTimeline from "./MetricsTimeline";
import { fmt } from "./format";
import { api, terminal } from "./types";
import type { Benchmark, Incident, LabEvent, World } from "./types";

function Metric({
  label,
  value,
  detail,
  accent = false,
}: {
  label: string;
  value: string;
  detail: string;
  accent?: boolean;
}) {
  return (
    <div className={`stat ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [environment, setEnvironment] = useState<World | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [selected, setSelected] = useState("");
  const [events, setEvents] = useState<LabEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("reference");
  const [auto, setAuto] = useState(true);
  const [seed, setSeed] = useState(42);
  const [replay, setReplay] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [section, setSection] = useState("overview");

  const refresh = useCallback(async () => {
    const [items, world, trials] = await Promise.all([
      api<Incident[]>("/incidents"),
      api<World>("/environment"),
      api<Benchmark[]>("/benchmarks"),
    ]);
    setIncidents(items);
    setEnvironment(world);
    setBenchmarks(trials);
    setSelected((current) => current || items[0]?.id || "");
  }, []);
  useEffect(() => {
    let alive = true;
    const load = () =>
      refresh().catch((e) => {
        if (alive) setError(String(e));
      });
    void load();
    const timer = setInterval(() => void load(), 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
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
          : [...current, event],
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
      150,
    );
    return () => clearInterval(timer);
  }, [playing, events.length]);
  useEffect(() => {
    if (playing && cursor >= events.length - 1) setPlaying(false);
  }, [cursor, events.length, playing]);

  const incident = incidents.find((i) => i.id === selected);
  const latest = incidents[0];
  const active = latest && !terminal(latest.status);
  const benchmarkBusy = benchmarks.some((b) => b.status === "running");
  const visible = useMemo(
    () => (replay ? events.slice(0, cursor + 1) : events),
    [events, replay, cursor],
  );
  const snapshots = visible.filter(
    (e) =>
      e.event_type === "environment.metric" ||
      e.event_type === "environment.state_changed",
  );
  const world =
    !replay &&
    incident?.id === latest?.id &&
    incident &&
    terminal(incident.status)
      ? (environment ?? incident.after)
      : ((snapshots.at(-1)?.payload as World | undefined) ??
        (replay ? null : (incident?.after ?? incident?.latest ?? environment)));
  const evaluations = incidents.flatMap((i) =>
    i.evaluation ? [i.evaluation] : [],
  );
  const successful = evaluations.filter((e) => e.incident_resolved);
  const mttr = successful.flatMap((e) =>
    e.time_to_recovery_seconds == null ? [] : [e.time_to_recovery_seconds],
  );
  const percent = (count: number) =>
    evaluations.length
      ? `${Math.round((count / evaluations.length) * 100)}%`
      : "—";
  const before = visible.find((e) => e.event_type === "alert.generated")
    ?.payload.metrics as World["metrics"] | undefined;

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
  function navigate(id: string) {
    setSection(id);
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <a href="#overview" className="brand">
          <span className="brand-icon">
            <Workflow size={23} />
          </span>
          <span>
            incident<span className="brand-lab">lab</span>
            <small>AGENT OPERATIONS</small>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-dot" /> Local workspace{" "}
          <span className="version">v0.1</span>
        </div>
        <div className="nav-label">实验控制台</div>
        <nav>
          {[
            ["overview", Activity, "总览"],
            ["environment", Layers3, "环境拓扑"],
            ["incident", Terminal, "事件与 Agent"],
            ["replay", RotateCcw, "历史回放"],
          ].map(([id, Icon, label]) => {
            const Component = Icon as typeof Activity;
            return (
              <button
                key={String(id)}
                className={section === id ? "nav-item selected" : "nav-item"}
                onClick={() => navigate(String(id))}
              >
                <Component size={18} />
                {String(label)}
                {id === "incident" && (
                  <span className="nav-count">{incidents.length}</span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-note">
          <FlaskConical size={20} />
          <strong>让故障成为证据。</strong>
          <p>
            可控注入，独立诊断，
            <br />
            让每一步恢复都可验证。
          </p>
          <span>SIMULATION ENVIRONMENT</span>
        </div>
        <div className="sidebar-footer">
          <span className="dot green" /> MCP · Streamable HTTP
          <small>API / Redis / Worker · 模拟服务</small>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div>
            Workspace <ChevronRight size={14} />{" "}
            <strong>Incident operations</strong>
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
        <main id="overview">
          <div className="page-heading">
            <div>
              <div className="eyebrow">OBSERVE. DIAGNOSE. RECOVER.</div>
              <h1>
                故障有迹，恢复有据<span>。</span>
              </h1>
              <p>
                从故障注入到自主修复，观察 Agent 如何完成一次真实的诊断闭环。
              </p>
            </div>
            <div className="lab-badge">
              <span className="dot green" /> LOCAL LAB{" "}
              <small>可重复 · 可审计 · 可回放</small>
            </div>
          </div>
          {error && (
            <div role="alert" className="error-banner">
              {error}
              <button onClick={() => setError("")} aria-label="关闭错误">
                ×
              </button>
            </div>
          )}
          <section className="stats">
            <Metric
              label="累计实验"
              value={String(incidents.length).padStart(2, "0")}
              detail={`${evaluations.length} 次已评估`}
            />
            <Metric
              label="恢复成功率"
              value={percent(successful.length)}
              detail="独立评估器验证"
              accent
            />
            <Metric
              label="根因诊断准确率"
              value={percent(
                evaluations.filter(
                  (e) => e.root_cause_correct && e.affected_service_correct,
                ).length,
              )}
              detail="根因与责任服务同时匹配"
            />
            <Metric
              label="平均恢复时间"
              value={
                mttr.length
                  ? fmt(mttr.reduce((a, b) => a + b, 0) / mttr.length, "s")
                  : "—"
              }
              detail="从 Agent 启动到确认恢复"
            />
            <Metric
              label="安全通过率"
              value={percent(
                evaluations.filter(
                  (e) => !e.unsafe_action_count && !e.forbidden_action_count,
                ).length,
              )}
              detail={
                evaluations.length
                  ? `平均 ${(evaluations.reduce((s, e) => s + e.action_count, 0) / evaluations.length).toFixed(1)} 次动作 / ${(evaluations.reduce((s, e) => s + e.tool_call_count, 0) / evaluations.length).toFixed(0)} 次工具调用`
                  : "所有变更经过策略审核"
              }
            />
          </section>
          <section className="experiment panel">
            <div className="experiment-icon">
              <Zap size={22} />
            </div>
            <div className="experiment-copy">
              <h3>启动一次故障实验</h3>
              <p>
                Worker 连接泄漏 <ArrowRight size={12} /> Redis 压力上升{" "}
                <ArrowRight size={12} /> API 退化
              </p>
            </div>
            <div className="experiment-controls">
              <label>
                Agent
                <select
                  aria-label="Agent 类型"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="reference">Reference · 无需密钥</option>
                  <option value="llm">LLM · 需配置密钥</option>
                </select>
              </label>
              <label>
                SEED
                <input
                  aria-label="随机种子"
                  type="number"
                  min="0"
                  max="4294967295"
                  value={seed}
                  onChange={(e) => setSeed(Number(e.target.value))}
                />
              </label>
              <label className="auto-label">
                <input
                  type="checkbox"
                  checked={auto}
                  onChange={(e) => setAuto(e.target.checked)}
                />
                告警后自动响应
              </label>
              <button
                className="primary"
                disabled={busy || !!active || benchmarkBusy}
                onClick={() =>
                  void perform(async () => {
                    const item = await api<Incident>("/incidents", {
                      method: "POST",
                      body: JSON.stringify({
                        scenario_id: "redis-connection-leak",
                        seed,
                        auto_agent: auto,
                        agent_mode: mode,
                      }),
                    });
                    setSelected(item.id);
                  })
                }
              >
                <Zap size={16} />
                {active ? "实验进行中" : "注入故障"}
              </button>
            </div>
          </section>
          <Environment world={world} replay={replay} before={before} />
          <IncidentWorkspace
            key={selected}
            incidents={incidents}
            selected={selected}
            onSelect={setSelected}
            busy={busy}
            visible={visible}
            replay={replay}
            onStart={() =>
              void perform(() =>
                api(`/incidents/${selected}/agent`, {
                  method: "POST",
                  body: JSON.stringify({ mode }),
                }),
              )
            }
            onCancel={() =>
              void perform(() =>
                api(`/incidents/${selected}/agent`, { method: "DELETE" }),
              )
            }
          />
          <MetricsTimeline
            events={events}
            visible={visible}
            replay={replay}
            cursor={cursor}
            playing={playing}
            onSeek={(value) => {
              setReplay(true);
              setPlaying(false);
              setCursor(value);
            }}
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
          <section className="benchmark">
            <div>
              <h3>
                <FlaskConical size={18} />
                可重复的能力验证
              </h3>
              <p>
                {benchmarks[0]?.aggregate
                  ? `最近基准：${benchmarks[0].results.length} 次试验 · 恢复率 ${Math.round(benchmarks[0].aggregate.resolution_rate * 100)}% · 平均 ${benchmarks[0].aggregate.average_tool_calls.toFixed(1)} 次工具调用`
                  : benchmarks[0]
                    ? `基准 ${benchmarks[0].status} · 已完成 ${benchmarks[0].results.length} 次试验`
                    : "使用选定 Agent 和种子运行 3 次，比较恢复率、诊断、安全性与效率。"}
              </p>
            </div>
            <button
              disabled={busy || !!active || benchmarkBusy}
              onClick={() =>
                void perform(() =>
                  api("/benchmarks", {
                    method: "POST",
                    body: JSON.stringify({
                      seeds: [seed],
                      trials: 3,
                      agent_mode: mode,
                    }),
                  }),
                )
              }
            >
              <Play size={14} />
              {benchmarkBusy ? "基准运行中" : "运行基准 · 3 trials"}
            </button>
          </section>
          <footer>
            INCIDENT AGENT LAB{" "}
            <span>
              Simulation creates the problem. Evidence earns the recovery.
            </span>
            <span>
              <ShieldCheck size={12} /> Ground truth isolated
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
