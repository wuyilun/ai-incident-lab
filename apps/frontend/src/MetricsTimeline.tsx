import {
  Area,
  CartesianGrid,
  ComposedChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Play, Radio, Square } from "lucide-react";
import { useState } from "react";
import type { LabEvent, Metrics, World } from "./types";
import { observations } from "./types";
import { fmt, metricLabel, metricUnit } from "./format";

export const milestoneNames: Record<string, string> = {
  "fault.injected": "故障注入",
  "alert.generated": "告警触发",
  "agent.alert_received": "Agent 接收",
  "agent.hypothesis": "根因诊断",
  "action.completed": "执行修复",
  "agent.verification": "恢复验证",
  "incident.resolved": "事件恢复",
  "incident.failed": "执行失败",
  "incident.cancelled": "实验取消",
};

type TimedEvent = { event: LabEvent; index: number; tick: number };
export function timedEvents(events: LabEvent[]): TimedEvent[] {
  let tick = 0;
  return events.map((event, index) => {
    const value =
      event.payload.tick ?? (event.payload.after as World | undefined)?.tick;
    if (typeof value === "number") tick = value;
    return { event, index, tick };
  });
}

type Props = {
  defaultMetric?: string;
  events: LabEvent[];
  visible: LabEvent[];
  replay: boolean;
  cursor: number;
  playing: boolean;
  onSeek: (cursor: number) => void;
  onToggle: () => void;
  onLive: () => void;
};
const series: {
  key: string;
  label: string;
  unit: string;
  color: string;
}[] = [
  {
    key: "redis_connections",
    label: "Redis 连接",
    unit: "clients",
    color: "#188d7b",
  },
  { key: "api_latency_ms", label: "API 延迟", unit: "ms", color: "#b7863b" },
  { key: "api_error_rate", label: "API 错误率", unit: "%", color: "#b65f55" },
];

export default function MetricsTimeline({
  defaultMetric,
  events,
  visible,
  replay,
  cursor,
  playing,
  onSeek,
  onToggle,
  onLive,
}: Props) {
  const [chosenMetric, setChosenMetric] = useState<string | null>(null);
  const firstMetric = chosenMetric ?? defaultMetric ?? "redis_connections";
  const plottedSeries = [
    {
      ...series[0],
      key: firstMetric,
      label: metricLabel(firstMetric),
      unit:
        metricUnit(firstMetric) ||
        (firstMetric === "queue_depth" ? "messages" : "clients"),
    },
    ...series.slice(1),
  ];
  const timeline = timedEvents(events);
  const hasReceipt = events.some(
    (e) => e.event_type === "agent.alert_received",
  );
  const firstDiagnosis = events.findIndex(
    (e) => e.event_type === "agent.hypothesis",
  );
  const milestones = timeline
    .filter(({ event, index }) => {
      if (event.event_type === "agent.hypothesis" && index !== firstDiagnosis)
        return false;
      return (
        event.event_type in milestoneNames ||
        (!hasReceipt && event.event_type === "agent.started")
      );
    })
    .map((point, index) => ({
      ...point,
      number: index + 1,
      label: milestoneNames[point.event.event_type] ?? "Agent 介入",
    }));
  const chart: (Metrics & { tick: number })[] = observations(visible).map(
    (snapshot) => ({
      tick: snapshot.tick,
      ...snapshot.metrics,
    }),
  );
  const lastTick = Math.max(1, timeline.at(-1)?.tick ?? 0);
  const currentIndex = replay ? cursor : events.length - 1;
  const currentTick = timeline[currentIndex]?.tick ?? 0;
  const currentEvent = timeline[currentIndex]?.event;
  const groups = Array.from(new Set(milestones.map((m) => m.tick))).map(
    (tick) => ({ tick, points: milestones.filter((m) => m.tick === tick) }),
  );
  const injected =
    milestones.find((m) => m.event.event_type === "fault.injected")?.tick ?? 0;
  const acting = milestones.find(
    (m) => m.event.event_type === "action.completed",
  )?.tick;
  const resolved = milestones.find(
    (m) => m.event.event_type === "incident.resolved",
  )?.tick;
  return (
    <section
      className="panel metrics-panel"
      id="replay"
      aria-label="故障指标时间线"
    >
      <div className="panel-heading">
        <div>
          <h2>故障 → 恢复</h2>
          <span className="muted">三个指标，同一时间轴</span>
        </div>
        <label className="trend-selector">
          关注指标
          <select
            aria-label="趋势关注指标"
            value={firstMetric}
            onChange={(e) => setChosenMetric(e.target.value)}
          >
            {Array.from(
              new Set([
                firstMetric,
                ...Object.keys(observations(visible).at(-1)?.metrics ?? {}),
              ]),
            )
              .filter(
                (key) => !["api_latency_ms", "api_error_rate"].includes(key),
              )
              .map((key) => (
                <option key={key} value={key}>
                  {metricLabel(key)}
                </option>
              ))}
          </select>
        </label>
        <span className="tag">
          {replay ? "REPLAY" : "LIVE"} · T+{currentTick}
        </span>
      </div>
      <div className="timeline-intro">
        <p>点击事件标记，同时回看环境、Agent 动作与诊断报告。</p>
        <div className="stage-legend">
          <span>
            <i className="baseline" />
            基线 T+0
          </span>
          <span>
            <i className="degrading" />
            故障演化
          </span>
          <span>
            <i className="recovering" />
            修复观察
          </span>
          <span>
            <i className="recovered" />
            确认恢复
          </span>
        </div>
      </div>
      <div className="metric-charts">
        {plottedSeries.map(({ key, label, unit, color }, seriesIndex) => (
          <div className="metric-chart" key={key} data-testid={`trend-${key}`}>
            <div className="metric-chart-label">
              <span style={{ color }}>
                {label}
                <small>{unit}</small>
              </span>
              <strong>{fmt(chart.at(-1)?.[key])}</strong>
            </div>
            <div className="metric-chart-canvas">
              <ResponsiveContainer width="100%" height={130}>
                <ComposedChart
                  syncId="incident-metrics"
                  syncMethod="value"
                  data={chart}
                  margin={{ top: 24, right: 24, bottom: 0, left: 0 }}
                >
                  <defs>
                    <linearGradient
                      id={`fill-${key}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0%" stopColor={color} stopOpacity={0.16} />
                      <stop
                        offset="100%"
                        stopColor={color}
                        stopOpacity={0.01}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="3 5"
                    vertical={false}
                    stroke="#e4e9e6"
                  />
                  <XAxis
                    dataKey="tick"
                    type="number"
                    domain={[0, lastTick]}
                    allowDecimals={false}
                    tick={{ fontSize: 10, fill: "#7e8d83" }}
                    tickFormatter={(n: number) => `T+${n}`}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={28}
                  />
                  <YAxis
                    width={49}
                    tick={{ fontSize: 10, fill: "#7e8d83" }}
                    axisLine={false}
                    tickLine={false}
                    domain={[0, "auto"]}
                    tickFormatter={(n: number) =>
                      n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
                    }
                  />
                  <ReferenceArea
                    x1={injected}
                    x2={Math.min(acting ?? currentTick, currentTick)}
                    fill="#d4a464"
                    fillOpacity={0.065}
                  />
                  {acting != null && currentTick >= acting && (
                    <ReferenceArea
                      x1={acting}
                      x2={Math.min(resolved ?? currentTick, currentTick)}
                      fill="#67a291"
                      fillOpacity={0.07}
                    />
                  )}
                  {resolved != null && currentTick >= resolved && (
                    <ReferenceArea
                      x1={resolved}
                      x2={currentTick}
                      fill="#4b956c"
                      fillOpacity={0.1}
                    />
                  )}
                  {chart[0] && (
                    <ReferenceLine
                      y={chart[0][key]}
                      stroke="#a6b3a7"
                      strokeDasharray="2 5"
                    />
                  )}
                  <Tooltip
                    content={({ active, payload, label: tickLabel }) => {
                      if (!active || !payload?.length) return null;
                      const tick = Number(tickLabel);
                      const points = milestones.filter(
                        (m) => m.tick === tick && m.index <= currentIndex,
                      );
                      return (
                        <div className="metric-tooltip">
                          <strong>
                            T+{tick} · {label}
                          </strong>
                          <p>
                            {fmt(Number(payload[0].value))} {unit}
                          </p>
                          {points.map((point) => (
                            <small key={point.event.sequence}>
                              {point.number}. {point.label}
                            </small>
                          ))}
                        </div>
                      );
                    }}
                  />
                  <Area
                    type="linear"
                    dataKey={key}
                    name={label}
                    stroke={color}
                    fill={`url(#fill-${key})`}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                    isAnimationActive={false}
                  />
                  {groups
                    .filter((g) =>
                      g.points.some((p) => p.index <= currentIndex),
                    )
                    .map((group) => {
                      const shown = group.points.filter(
                        (p) => p.index <= currentIndex,
                      );
                      return (
                        <ReferenceLine
                          key={group.tick}
                          x={group.tick}
                          stroke="#9baea3"
                          strokeDasharray="3 4"
                          label={
                            seriesIndex === 0
                              ? {
                                  value:
                                    shown.length === 1
                                      ? `${shown[0].number}`
                                      : `${shown[0].number}–${shown.at(-1)?.number}`,
                                  position: "top",
                                  fontSize: 10,
                                  fill: "#446d58",
                                }
                              : undefined
                          }
                        />
                      );
                    })}
                  {replay && (
                    <ReferenceLine
                      x={currentTick}
                      stroke="#304d3e"
                      strokeWidth={1.5}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>
      {!chart.length && (
        <p className="chart-empty">
          注入后将按模拟时钟记录指标，T+0 为环境初始采样。
        </p>
      )}
      <div className="marker-rail" aria-label="关键事件标记">
        {milestones.length ? (
          milestones.map((point) => (
            <button
              key={point.event.sequence}
              data-testid={`timeline-marker-${point.event.sequence}`}
              aria-label={`${point.label} · 事件 ${point.number} · T+${point.tick}`}
              aria-pressed={replay && cursor === point.index}
              className={`milestone ${point.index > currentIndex ? "future" : ""} ${replay && cursor === point.index ? "selected" : ""}`}
              onClick={() => onSeek(point.index)}
              title={new Date(point.event.timestamp).toLocaleString("zh-CN", {
                hour12: false,
              })}
            >
              <span className="milestone-number">{point.number}</span>
              <span>
                <strong>{point.label}</strong>
                <small>
                  T+{point.tick} ·{" "}
                  {new Date(point.event.timestamp).toLocaleTimeString("zh-CN", {
                    hour12: false,
                  })}
                </small>
              </span>
            </button>
          ))
        ) : (
          <span className="muted">
            故障注入 → 告警 → Agent 接收 → 诊断 → 修复 → 验证 → 恢复
          </span>
        )}
      </div>
      <div className="replay-controls">
        <button disabled={!events.length} onClick={onToggle}>
          {playing ? <Square size={13} /> : <Play size={13} />}
          {playing ? "暂停" : "回放"}
        </button>
        <input
          aria-label="回放进度"
          type="range"
          min={0}
          max={Math.max(0, events.length - 1)}
          value={Math.max(0, currentIndex)}
          disabled={!events.length}
          onChange={(e) => onSeek(Number(e.target.value))}
        />
        <span>
          {Math.max(0, currentIndex + 1)} / {events.length}
        </span>
        <button className={`live ${!replay ? "active" : ""}`} onClick={onLive}>
          <Radio size={13} />
          实时
        </button>
      </div>
      {replay && currentEvent && (
        <div className="cursor-caption" role="status">
          正在回看 T+{currentTick} · {currentEvent.event_type} ·{" "}
          {new Date(currentEvent.timestamp).toLocaleTimeString("zh-CN", {
            hour12: false,
          })}
        </div>
      )}
    </section>
  );
}
