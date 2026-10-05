import { useEffect, useId, useRef, useState } from "react";
import {
  ArrowRight,
  Database,
  GitBranch,
  Layers3,
  Radio,
  Server,
  Workflow,
  Maximize2,
  X,
  Crosshair,
} from "lucide-react";
import type { FaultMarker, World } from "./types";
import { fmt, metricLabel, metricUnit } from "./format";

type Service = World["services"][number];
const unhealthy = (service: Service) =>
  service.health
    ? service.health !== "healthy"
    : !["running", "healthy", "ready", "online"].includes(service.status);

const tierNames = ["入口", "接口", "业务服务", "中间件", "存储"];
const legacyTiers: Record<string, number> = {
  gateway: 0,
  api: 1,
  worker: 2,
  redis: 3,
  queue: 3,
  database: 4,
};
function layout(services: Service[]) {
  const tierOf = (service: Service) =>
    service.tier ?? legacyTiers[service.name] ?? 2;
  const maxTier = Math.max(0, ...services.map(tierOf));
  const layers = Array.from({ length: maxTier + 1 }, (_, tier) => ({
    tier,
    services: services.filter((service) => tierOf(service) === tier),
  })).filter((layer) => layer.services.length > 0);
  return {
    height: Math.max(150, layers.length * 136 + 14),
    layers,
    nodes: layers.flatMap((layer, row) =>
      layer.services.map((service, column) => ({
        service,
        row,
        x: 100 + ((column + 0.5) / layer.services.length) * 800,
        y: row * 136 + 86,
        width: Math.min(270, 704 / layer.services.length),
      })),
    ),
  };
}
type Node = ReturnType<typeof layout>["nodes"][number];
function routeEdge(from: Node, to: Node, index: number) {
  const startY = from.y + 43,
    endY = to.y - 46;
  if (to.row === from.row + 1) {
    const turnY = startY + 12 + (index % 3) * 4;
    return `M ${from.x} ${startY} V ${turnY} H ${to.x} V ${endY}`;
  }
  // Non-adjacent links use outer lanes reserved outside every node's bounds.
  const right = (from.x + to.x) / 2 >= 500;
  const lane = right ? 976 - (index % 4) * 16 : 24 + (index % 4) * 16;
  return `M ${from.x} ${startY} V ${startY + 12} H ${lane} V ${endY - 12} H ${to.x} V ${endY}`;
}
const faultText: Record<FaultMarker["phase"], string> = {
  preview: "待注入",
  injected: "故障注入点",
  recovered: "注入点已恢复",
};

function ServiceIcon({ kind }: { kind: string }) {
  if (["database", "cache", "redis"].includes(kind))
    return <Database size={18} />;
  if (["worker", "queue"].includes(kind)) return <Layers3 size={18} />;
  if (["gateway", "api"].includes(kind)) return <Workflow size={18} />;
  return <Server size={18} />;
}

export default function Environment({
  world,
  replay,
  before,
  fault,
}: {
  world: World | null | undefined;
  replay: boolean;
  before?: World["metrics"];
  fault?: FaultMarker;
}) {
  const [selectedNode, setSelectedNode] = useState("");
  const [expanded, setExpanded] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const markerId = useId().replaceAll(":", "");
  useEffect(() => {
    if (expanded) dialog.current?.showModal();
    else dialog.current?.close();
  }, [expanded]);
  const metrics = world?.metrics;
  const services = world?.services ?? [];
  const dependencies = world?.dependencies ?? [];
  const { height, layers, nodes } = layout(services);
  const selected = services.find((service) => service.name === selectedNode);
  const direct = dependencies.filter((edge) => edge.from === selected?.name);
  const focused = new Set([selected?.name, ...direct.map((edge) => edge.to)]);
  const faultBanner = fault && (
    <div className={`fault-banner ${fault.phase}`} data-testid="fault-location">
      <Crosshair size={14} />
      <strong>
        {faultText[fault.phase]} · {fault.target}
      </strong>
      <span>{fault.label}</span>
      <small>操作员视图</small>
    </div>
  );
  const graph = (
    <>
      {faultBanner}
      <div className="topology-viewport">
        <div
          className="topology-graph"
          style={{ height }}
          aria-label="服务依赖拓扑"
        >
          {layers.map(({ tier }, row) => (
            <div
              className="topology-tier"
              style={{ top: row * 136 + 7 }}
              key={tier}
            >
              <span>
                L{tier} / {tierNames[tier] ?? `服务层 ${tier}`}
              </span>
            </div>
          ))}
          <svg
            viewBox={`0 0 1000 ${height}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              {[
                ["normal", "#92ab90"],
                ["affected", "#c18c47"],
                ["focused", "#416d57"],
              ].map(([name, color]) => (
                <marker
                  key={name}
                  id={`${markerId}-${name}`}
                  markerWidth="7"
                  markerHeight="7"
                  refX="6"
                  refY="3.5"
                  orient="auto"
                >
                  <path d="M0,0 L7,3.5 L0,7" fill={color} />
                </marker>
              ))}
            </defs>
            {dependencies.map((edge, index) => {
              const from = nodes.find(
                (node) => node.service.name === edge.from,
              );
              const to = nodes.find((node) => node.service.name === edge.to);
              if (!from || !to) return null;
              const affected = edge.affected ?? unhealthy(to.service);
              const emphasized = selected?.name === edge.from;
              const tone = affected
                ? "affected"
                : emphasized
                  ? "focused"
                  : "normal";
              return (
                <path
                  key={`${edge.from}-${edge.to}`}
                  data-testid={`dependency-${edge.from}-${edge.to}`}
                  data-affected={affected}
                  data-focused={emphasized}
                  className={`dependency ${affected ? "pressured" : ""} ${emphasized ? "focused" : ""} ${selected && !emphasized ? "dimmed" : ""}`}
                  d={routeEdge(from, to, index)}
                  markerEnd={`url(#${markerId}-${tone})`}
                >
                  <title>
                    {edge.from} → {edge.to} ·{" "}
                    {edge.label ?? edge.kind ?? "服务依赖"}
                    {affected ? " · 依赖受影响" : ""}
                  </title>
                </path>
              );
            })}
          </svg>
          {nodes.map(({ service, x, y, width }) => {
            const marked = fault?.target === service.name ? fault : undefined;
            return (
              <button
                key={service.name}
                className={`topology-node ${unhealthy(service) ? "pressured" : ""} ${selected?.name === service.name ? "selected" : ""} ${selected && !focused.has(service.name) ? "dimmed" : ""} ${marked ? `fault-${marked.phase}` : ""}`}
                style={{ left: `${x / 10}%`, top: y, width: `${width / 10}%` }}
                onClick={() =>
                  setSelectedNode(
                    selected?.name === service.name ? "" : service.name,
                  )
                }
                aria-label={`${service.label ?? service.name} · ${service.health ?? service.status}${marked ? ` · ${faultText[marked.phase]}` : ""}`}
                aria-pressed={selected?.name === service.name}
                data-testid={`service-${service.name}`}
                title={service.label ?? service.name}
              >
                {marked && (
                  <span className={`node-fault-badge ${marked.phase}`}>
                    {faultText[marked.phase]}
                  </span>
                )}
                <span className="node-title">
                  <ServiceIcon kind={service.kind ?? service.name} />
                  <strong>{service.label ?? service.name}</strong>
                </span>
                <small>
                  <span
                    className={`dot ${unhealthy(service) ? "orange" : "green"}`}
                  />
                  {service.health ?? service.status}
                  {service.restarts > 0 ? ` · ↻${service.restarts}` : ""}
                </small>
                <span className="node-metrics">
                  {Object.entries(service.metrics ?? {})
                    .slice(0, 2)
                    .map(([key, value]) => (
                      <span key={key} title={metricLabel(key)}>
                        {metricLabel(key)}{" "}
                        <b>
                          {fmt(value)}
                          {metricUnit(key)}
                        </b>
                      </span>
                    ))}
                </span>
              </button>
            );
          })}
          {!nodes.length && (
            <div className="empty topology-empty">
              <Radio size={23} />
              <p>等待当前时刻的环境采样</p>
            </div>
          )}
        </div>
      </div>
      {selected ? (
        <div className="node-detail" aria-label="节点观测详情">
          <div>
            <strong>{selected.label ?? selected.name}</strong>
            <span>
              {selected.kind ?? "service"} · 重启 {selected.restarts} 次
            </span>
          </div>
          <div className="node-detail-metrics">
            {Object.entries(selected.metrics ?? {}).map(([key, value]) => (
              <span key={key}>
                {metricLabel(key)}
                <b>
                  {fmt(value)} {metricUnit(key)}
                </b>
              </span>
            ))}
            {!Object.keys(selected.metrics ?? {}).length && (
              <small>此历史采样没有节点局部指标</small>
            )}
          </div>
          <ul className="node-dependencies">
            {direct.map((edge) => (
              <li key={edge.to}>
                <ArrowRight size={12} />
                <strong>{edge.to}</strong>
                <span>{edge.label ?? edge.kind ?? "服务依赖"}</span>
                {edge.affected && <small>依赖受影响</small>}
              </li>
            ))}
          </ul>
          {!direct.length && <p>无直接下游依赖</p>}
          <button className="clear-focus" onClick={() => setSelectedNode("")}>
            显示全部依赖
          </button>
        </div>
      ) : (
        <p className="topology-hint">
          点击节点，突出其直接依赖并查看指标；横向浏览或展开查看完整拓扑。
        </p>
      )}
    </>
  );
  return (
    <div className="middle-grid" id="environment">
      <section className="panel topology">
        <div className="panel-heading">
          <div>
            <span className="section-index">01</span>
            <h2>环境拓扑</h2>
          </div>
          <div>
            <span className="tag">
              {replay ? "REPLAY" : "SIMULATED"} · T+{world?.tick ?? 0}
            </span>
            <button
              className="expand-topology"
              onClick={() => setExpanded(true)}
            >
              <Maximize2 size={13} />
              展开拓扑
            </button>
          </div>
        </div>
        <div className="topology-direction">
          <ArrowRight size={13} />
          箭头：调用者 → 依赖服务<span>健康与依赖颜色来自观测</span>
        </div>
        {!expanded && graph}
        <dialog
          ref={dialog}
          className="topology-dialog"
          onCancel={() => setExpanded(false)}
          onClose={() => setExpanded(false)}
          aria-label="展开环境拓扑"
        >
          <div className="panel-heading">
            <h2>环境拓扑 · 调用者 → 依赖服务</h2>
            <button
              aria-label="关闭展开拓扑"
              onClick={() => setExpanded(false)}
            >
              <X size={17} />
            </button>
          </div>
          {expanded && graph}
        </dialog>
        <div className="environment-foot topology-legend">
          <span>
            <i className="legend-dot fault" />
            注入点（操作员）
          </span>
          <span>
            <i className="legend-dot affected" />
            依赖受影响
          </span>
          <span>
            <i className="legend-dot healthy" />
            健康
          </span>
          <span>
            <i className="legend-dot recovered" />
            已恢复
          </span>
          <span>
            <GitBranch size={12} />
            {services.length} 节点 · {dependencies.length} 依赖
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
            className={`status ${services.some(unhealthy) || (metrics?.api_error_rate ?? 0) >= 3 ? "warning" : ""}`}
          >
            {!metrics
              ? "WAITING"
              : services.some(unhealthy) || metrics.api_error_rate >= 3
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
            {fmt(before)} <ArrowRight size={12} />
            <b>{value}</b>
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
