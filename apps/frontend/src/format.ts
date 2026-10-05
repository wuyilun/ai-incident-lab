export const fmt = (value: number | undefined | null, suffix = "") =>
  value == null
    ? "—"
    : `${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}`;

const metricNames: Record<string, string> = {
  db_pool_active: "池连接占用",
  db_pool_wait_ms: "获取连接等待",
  payment_latency_ms: "支付延迟",
  inventory_latency_ms: "库存延迟",
  notification_lag: "通知积压",
  redis_connections: "Redis 连接",
  redis_latency_ms: "Redis 延迟",
  api_latency_ms: "API 延迟",
  api_error_rate: "API 错误率",
  worker_open_clients: "Worker 连接",
  api_cpu_percent: "API CPU",
  cpu_percent: "CPU",
  memory_mb: "内存",
  connections: "连接",
  latency_ms: "延迟",
  error_rate: "错误率",
  queue_depth: "队列积压",
  database_latency_ms: "数据库延迟",
  database_slow_queries: "慢查询",
  worker_cpu_percent: "Worker CPU",
  depth: "积压",
  open_clients: "连接",
};
export const metricLabel = (key: string) =>
  metricNames[key] ?? key.replaceAll("_", " ");
export const metricUnit = (key: string) =>
  key.endsWith("_ms")
    ? "ms"
    : key.endsWith("_percent") || key.endsWith("_rate")
      ? "%"
      : key.endsWith("_mb")
        ? "MB"
        : "";
