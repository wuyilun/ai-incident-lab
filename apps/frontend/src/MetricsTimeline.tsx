import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Play, Square } from "lucide-react";
import type { LabEvent, World } from "./types";
export default function MetricsTimeline({
  events,
  visible,
  replay,
  cursor,
  playing,
  onSeek,
  onToggle,
  onLive,
}: {
  events: LabEvent[];
  visible: LabEvent[];
  replay: boolean;
  cursor: number;
  playing: boolean;
  onSeek: (cursor: number) => void;
  onToggle: () => void;
  onLive: () => void;
}) {
  const chart = visible
    .filter((e) =>
      ["environment.metric", "environment.state_changed"].includes(
        e.event_type,
      ),
    )
    .map((e) => {
      const s = e.payload as World;
      return { tick: s.tick, ...s.metrics };
    });
  const actions = visible.filter((e) => e.event_type === "action.completed");
  return (
    <section className="panel metrics-panel" id="replay">
      <div className="panel-heading">
        <div>
          <span className="section-index">04</span>
          <h2>故障 → 恢复</h2>
          <span className="muted">指标时间线</span>
        </div>
        <div className="legend">
          <span className="legend-teal" />
          Redis 连接
          <span className="legend-orange" />
          API 延迟
          <span className="legend-red" />
          错误率（见下图）
        </div>
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height={215}>
          <ComposedChart
            data={chart}
            margin={{ top: 15, right: 25, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#159d8c" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#159d8c" stopOpacity={0} />
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
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 11 }}
              tickFormatter={(n) => `T+${n}`}
            />
            <YAxis yAxisId="connections" tick={{ fontSize: 10 }} width={45} />
            <YAxis
              yAxisId="latency"
              orientation="right"
              tick={{ fontSize: 10 }}
              unit="ms"
              width={60}
            />
            <Tooltip />
            <Area
              yAxisId="connections"
              type="monotone"
              dataKey="redis_connections"
              name="Redis connections"
              stroke="#159d8c"
              fill="url(#fill)"
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Line
              yAxisId="latency"
              type="monotone"
              dataKey="api_latency_ms"
              name="API latency (ms)"
              stroke="#d99d4f"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            {actions.map((e) => (
              <ReferenceLine
                key={e.sequence}
                yAxisId="connections"
                x={(e.payload.after as World).tick}
                stroke="#61716b"
                strokeDasharray="4 4"
                label={{
                  value: "RESTART",
                  position: "insideTopRight",
                  fontSize: 10,
                }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="error-chart">
        <span>API ERRORS %</span>
        <ResponsiveContainer width="100%" height={75}>
          <ComposedChart
            data={chart}
            margin={{ right: 85, left: 0, bottom: 0 }}
          >
            <XAxis dataKey="tick" hide />
            <YAxis width={45} tick={{ fontSize: 10 }} />
            <Tooltip />
            <Line
              dataKey="api_error_rate"
              name="API error rate (%)"
              stroke="#bf6e5d"
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="replay-controls">
        <button disabled={!events.length} onClick={onToggle}>
          {playing ? <Square size={13} /> : <Play size={13} />}{" "}
          {playing ? "暂停" : "回放"}
        </button>
        <input
          aria-label="回放进度"
          type="range"
          min="0"
          max={Math.max(0, events.length - 1)}
          value={replay ? cursor : Math.max(0, events.length - 1)}
          disabled={!events.length}
          onChange={(e) => onSeek(Number(e.target.value))}
        />
        <span>
          {replay ? cursor + 1 : events.length} / {events.length}
        </span>
        <button className={!replay ? "live active" : "live"} onClick={onLive}>
          <span className="dot green" />
          实时
        </button>
      </div>
    </section>
  );
}
