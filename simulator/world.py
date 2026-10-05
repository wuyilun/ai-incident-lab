"""Seeded, stateful causal simulation. Only observation() crosses the MCP boundary."""

import random
from collections import deque
from pathlib import Path
from typing import Any

from packages.contracts import Scenario
from simulator.environment import Environment, load_environment

SCENARIO_DIR = Path(__file__).parent / "scenarios"


def load_scenarios() -> dict[str, Scenario]:
    items = [Scenario.model_validate_json(p.read_text()) for p in SCENARIO_DIR.glob("*.json")]
    return {s.id: s for s in items}


class World:
    def __init__(self, seed: int = 42, environment: Environment | None = None):
        self.environment = environment or load_environment()
        self.fault_target: str | None = None
        self.fault_type: str | None = None
        self.intensity = 0.0
        self.db_pool_active = 12.0
        self.cpu = 25.0
        self.database_latency = 20.0
        self.queue_depth = 10.0
        self.seed = seed
        self.tick = 0
        self.rng = random.Random(seed)
        self.connections = 100.0
        self.leak_intensity = 0.0
        self.status = {service.name: "running" for service in self.environment.services}
        self.restarts = dict.fromkeys(self.status, 0)
        self.config = {service.name: service.config.copy() for service in self.environment.services}
        self.logs: deque[dict[str, Any]] = deque(maxlen=100)
        self.healthy_ticks = 0
        self._log("api", "info", "Request stream active; dependency redis connected")
        self._log("worker", "info", "Job queue consumer started; redis client pool initialized")

    def _log(self, service: str, level: str, message: str) -> None:
        self.logs.append(
            {"tick": self.tick, "service": service, "level": level, "message": message}
        )

    def inject(self, scenario: Scenario) -> None:
        if scenario.target not in self.status:
            raise ValueError("Scenario target is absent from the environment")
        self.fault_type, self.fault_target = scenario.fault.type, scenario.target
        self.intensity = scenario.fault.intensity
        self.leak_intensity = self.intensity if self.fault_type == "connection_leak" else 0
        if self.fault_type == "service_down":
            self.status[scenario.target] = "stopped"
            self._log(scenario.target, "error", "Service process exited unexpectedly")
        self.healthy_ticks = 0

    def advance(self) -> dict[str, Any]:
        self.tick += 1
        if self.leak_intensity and self.status.get(self.fault_target or "worker") == "running":
            self.connections = min(
                990, self.connections + 100 * self.leak_intensity + self.rng.uniform(-5, 5)
            )
            self._log(
                self.fault_target or "worker",
                "warning",
                f"redis client acquired without release; open_clients={int(self.connections - 60)}; pool_limit=100",
            )
        else:
            self.connections = max(100, 100 + (self.connections - 100) * 0.35)
        target = self.fault_target or "api"
        if self.fault_type == "cpu_saturation":
            self.cpu = min(99, self.cpu + 22 * self.intensity)
            self._log(target, "warning", "CPU saturation; busy loop detected")
        else:
            self.cpu = 25 + (self.cpu - 25) * 0.25
        if self.fault_type == "slow_queries":
            self.database_latency = min(2000, self.database_latency + 220 * self.intensity)
            self._log(target, "warning", "Query execution stalled; slow query backlog")
        else:
            self.database_latency = 20 + (self.database_latency - 20) * 0.25
        if self.fault_type == "queue_backlog" or self.status.get("queue") == "stopped":
            self.queue_depth = min(5000, self.queue_depth + 220 * self.intensity)
            if self.fault_type == "queue_backlog":
                self._log(target, "warning", "Consumer stalled; messages not acknowledged")
        else:
            self.queue_depth = 10 + (self.queue_depth - 10) * 0.25
        if self.fault_type == "connection_pool_exhaustion":
            self.db_pool_active = min(100, self.db_pool_active + 20 * self.intensity)
            self._log(
                target, "warning", "Connection acquisition timed out; pool wait queue growing"
            )
        else:
            self.db_pool_active = 12 + (self.db_pool_active - 12) * 0.25
        if self.database_latency > 200 or self.db_pool_active > 70:
            for dependent in ("api", "payment", "inventory", "worker"):
                if dependent in self.status:
                    self._log(dependent, "warning", "Dependency request timed out; retry scheduled")
        metrics = self.metrics()
        if metrics["api_error_rate"] >= 1 and self.leak_intensity:
            self._log("api", "error", "redis request timeout; upstream request failed")
            self._log(
                "redis",
                "warning",
                f"Client pressure elevated; clients_by_name: worker={int(self.connections - 60)}, api=60",
            )
        self.healthy_ticks = self.healthy_ticks + 1 if self.healthy() else 0
        return self.observation()

    def dependency_closure(self, service: str) -> set[str]:
        reachable = {service}
        for _ in self.status:
            reachable |= {e.to for e in self.environment.dependencies if e.from_ in reachable}
        return reachable

    def metrics(self) -> dict[str, float]:
        pressure = max(0, (self.connections - 200) / 750)
        unavailable = any(
            self.status.get(name) != "running" for name in self.dependency_closure("api")
        )
        cpu_pressure = max(0, (self.cpu - 70) / 25)
        db_pressure = max(0, (self.database_latency - 200) / 500)
        queue_pressure = max(0, (self.queue_depth - 200) / 500)
        pool_wait = max(0, self.db_pool_active - 65) * 25
        pool_pressure = max(0, (self.db_pool_active - 70) / 25)
        extra_latency = (
            cpu_pressure * 1000 + db_pressure * 700 + queue_pressure * 600 + pool_wait * 1.5
        )
        extra_errors = cpu_pressure * 5 + db_pressure * 3 + queue_pressure * 3 + pool_pressure * 4
        return {
            "redis_connections": round(self.connections, 1),
            "redis_latency_ms": round(2 + pressure**2 * 180, 1),
            "api_latency_ms": 5000
            if unavailable
            else round(180 + pressure**2 * 4100 + extra_latency, 1),
            "api_error_rate": 100
            if unavailable
            else round(min(100, 0.2 + pressure**2 * 14 + extra_errors), 2),
            "db_pool_active": round(self.db_pool_active, 1),
            "db_pool_wait_ms": round(pool_wait, 1),
            "payment_latency_ms": round(40 + self.database_latency + pool_wait, 1),
            "inventory_latency_ms": round(25 + self.database_latency + pool_wait, 1),
            "notification_lag": round(self.queue_depth, 1),
            "api_cpu_percent": round(self.cpu, 1),
            "database_latency_ms": round(self.database_latency, 1),
            "queue_depth": round(self.queue_depth, 1),
            "worker_open_clients": round(max(0, self.connections - 60), 1),
        }

    def healthy(self) -> bool:
        m = self.metrics()
        return (
            all(v == "running" for v in self.status.values())
            and m["redis_connections"] < 200
            and m["api_error_rate"] < 1
            and m["api_latency_ms"] < 300
            and self.db_pool_active < 70
            and self.cpu < 70
            and self.database_latency < 200
            and self.queue_depth < 200
        )

    def observation(self) -> dict[str, Any]:
        metrics = self.metrics()
        impaired = {name for name, state in self.status.items() if state != "running"}
        # Infer health from public measurements, never from the injected target.
        limits = {
            "redis_connections": 200,
            "redis_latency_ms": 10,
            "worker_open_clients": 100,
            "api_cpu_percent": 70,
            "api_latency_ms": 300,
            "api_error_rate": 1,
            "database_latency_ms": 200,
            "queue_depth": 200,
            "db_pool_active": 70,
            "db_pool_wait_ms": 100,
            "payment_latency_ms": 240,
            "inventory_latency_ms": 225,
            "notification_lag": 200,
        }
        impaired |= {
            service.name
            for service in self.environment.services
            if any(
                metrics.get(key, 0) >= limits[key] for key in service.metric_keys if key in limits
            )
        }
        edges = [e.model_dump(by_alias=True) for e in self.environment.dependencies]
        # Propagate observed dependency impairment, including graphs with cycles.
        for _ in self.status:
            impaired |= {e["from"] for e in edges if e["to"] in impaired}
        return {
            "environment_id": self.environment.id,
            "name": self.environment.name,
            "tick": self.tick,
            "metrics": metrics,
            "services": [
                {
                    "name": service.name,
                    "label": service.label,
                    "kind": service.kind,
                    "tier": service.tier,
                    "status": self.status[service.name],
                    "restarts": self.restarts[service.name],
                    "health": "unavailable"
                    if self.status[service.name] != "running"
                    else "degraded"
                    if service.name in impaired
                    else "healthy",
                    "metrics": {key: metrics[key] for key in service.metric_keys if key in metrics},
                }
                for service in self.environment.services
            ],
            "dependencies": [{**edge, "affected": edge["to"] in impaired} for edge in edges],
            "healthy_ticks": self.healthy_ticks,
        }

    def restart(self, service: str) -> None:
        if service not in self.status:
            raise ValueError("Unknown service")
        self.status[service] = "running"
        self.restarts[service] += 1
        if service == self.fault_target:
            self.fault_type = None
            self.leak_intensity = 0
            self.connections = 100 + (self.connections - 100) * 0.5
        self.healthy_ticks = 0
        self._log(
            service, "info", "Service restarted; process state reset and owned resources released"
        )
