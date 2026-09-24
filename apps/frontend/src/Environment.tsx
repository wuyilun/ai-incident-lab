import {
  ArrowDown,
  ArrowRight,
  Database,
  GitBranch,
  Layers3,
  Radio,
  Workflow,
} from "lucide-react";
import type { World } from "./types";
import { fmt } from "./format";
export default function Environment({
  world,
  replay,
  before,
}: {
  world: World | null | undefined;
  replay: boolean;
  before?: World["metrics"];
}) {
  const metrics = world?.metrics;
  return (
    <div className="middle-grid" id="environment">
      <section className="panel topology">
        <div className="panel-heading">
          <div>
            <span className="section-index">01</span>
            <h2>环境拓扑</h2>
          </div>
          <span className="tag">
            {replay ? "REPLAY" : "SIMULATED"} · T+{world?.tick ?? 0}
          </span>
        </div>
        <div className="topology-canvas">
          <div className="flow-source">
            <Service name="api" label="API Gateway" world={world} />
            <Service name="worker" label="Background Worker" world={world} />
          </div>
          <div className="flow-lines">
            <span>
              请求 / cache
              <ArrowDown size={21} />
            </span>
            <span>
              任务 / connections
              <ArrowDown size={21} />
            </span>
          </div>
          <div className="redis-node">
            <Service name="redis" label="Redis" world={world} />
          </div>
          <span className="traffic-label">
            <Radio size={12} /> 依赖状态随模拟时钟变化
          </span>
        </div>
        <div className="environment-foot">
          <span>
            <span className="dot green" /> Running
          </span>
          <span>
            <span className="dot orange" /> Resource pressure
          </span>
          <span>
            <GitBranch size={13} /> 2 dependencies
          </span>
        </div>
      </section>
      <section className="panel signals">
        <div className="panel-heading">
          <div>
            <span className="section-index">02</span>
            <h2>环境信号</h2>
          </div>
          <span
            className={`status ${metrics && metrics.api_error_rate >= 3 ? "warning" : ""}`}
          >
            {!metrics
              ? "WAITING"
              : metrics.api_error_rate >= 3
                ? "DEGRADED"
                : "HEALTHY"}
          </span>
        </div>
        <Signal
          label="Redis connections"
          value={fmt(metrics?.redis_connections)}
          unit="clients"
          before={before?.redis_connections}
          current={metrics?.redis_connections}
          threshold={200}
          max={1000}
        />
        <Signal
          label="API latency"
          value={fmt(metrics?.api_latency_ms)}
          unit="ms"
          before={before?.api_latency_ms}
          current={metrics?.api_latency_ms}
          threshold={300}
          max={5000}
        />
        <Signal
          label="API error rate"
          value={fmt(metrics?.api_error_rate)}
          unit="%"
          before={before?.api_error_rate}
          current={metrics?.api_error_rate}
          threshold={1}
          max={15}
        />
      </section>
    </div>
  );
}

function Service({
  name,
  label,
  world,
}: {
  name: string;
  label: string;
  world: World | null | undefined;
}) {
  const service = world?.services.find((s) => s.name === name);
  const pressured =
    world &&
    (name === "redis"
      ? world.metrics.redis_connections >= 200
      : name === "api"
        ? world.metrics.api_error_rate >= 3
        : world.metrics.worker_open_clients > 100);
  return (
    <div className={`service ${pressured ? "pressured" : ""}`}>
      <div className="service-icon">
        {name === "redis" ? (
          <Database size={22} />
        ) : name === "api" ? (
          <Workflow size={22} />
        ) : (
          <Layers3 size={22} />
        )}
      </div>
      <div>
        <strong>{label}</strong>
        <small>
          <span className={`dot ${pressured ? "orange" : "green"}`} />
          {service?.status ?? "unknown"}
          {service?.restarts ? ` · restarted ${service.restarts}×` : ""}
        </small>
      </div>
    </div>
  );
}
function Signal({
  label,
  value,
  unit,
  before,
  current,
  threshold,
  max,
}: {
  label: string;
  value: string;
  unit: string;
  before?: number;
  current?: number;
  threshold: number;
  max: number;
}) {
  const bad = (current ?? 0) >= threshold;
  return (
    <div className="signal">
      <div>
        <span>{label}</span>
        <small>
          健康阈值 &lt; {threshold}
          {unit === "%" ? "%" : ""}
        </small>
      </div>
      <div className="signal-value">
        <strong className={bad ? "bad" : ""}>
          {value}
          <small>{unit}</small>
        </strong>
        {before != null && (
          <span>
            {fmt(before)} <ArrowRight size={12} /> <b>{value}</b>
          </span>
        )}
      </div>
      <div className="meter">
        <i
          className={bad ? "bad" : ""}
          style={{ width: `${Math.min(100, ((current ?? 0) / max) * 100)}%` }}
        />
      </div>
    </div>
  );
}
