"""Seeded, stateful causal simulation. Only observation() crosses the MCP boundary."""

import random
from collections import deque
from pathlib import Path
from typing import Any

from packages.contracts import Scenario

SCENARIO_DIR = Path(__file__).parent / "scenarios"


def load_scenarios() -> dict[str, Scenario]:
    items = [Scenario.model_validate_json(p.read_text()) for p in SCENARIO_DIR.glob("*.json")]
    return {s.id: s for s in items}


class World:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.tick = 0
        self.rng = random.Random(seed)
        self.connections = 100.0
        self.leak_intensity = 0.0
        self.status = {"api": "running", "redis": "running", "worker": "running"}
        self.restarts = dict.fromkeys(self.status, 0)
        self.config = {
            "worker": {"pool_limit": 100, "concurrency": 8},
            "redis": {"max_clients": 1000},
            "api": {"timeout_ms": 3000},
        }
        self.logs: deque[dict[str, Any]] = deque(maxlen=100)
        self.healthy_ticks = 0
        self._log("api", "info", "Request stream active; dependency redis connected")
        self._log("worker", "info", "Job queue consumer started; redis client pool initialized")

    def _log(self, service: str, level: str, message: str) -> None:
        self.logs.append(
            {"tick": self.tick, "service": service, "level": level, "message": message}
        )

    def inject(self, scenario: Scenario) -> None:
        self.leak_intensity = scenario.fault.intensity
        self.healthy_ticks = 0

    def advance(self) -> dict[str, Any]:
        self.tick += 1
        if self.leak_intensity and self.status["worker"] == "running":
            self.connections = min(
                990, self.connections + 100 * self.leak_intensity + self.rng.uniform(-5, 5)
            )
            self._log(
                "worker",
                "warning",
                f"redis client acquired without release; open_clients={int(self.connections - 60)}; pool_limit=100",
            )
        else:
            self.connections = max(100, 100 + (self.connections - 100) * 0.35)
        metrics = self.metrics()
        if metrics["api_error_rate"] >= 1:
            self._log("api", "error", "redis request timeout; upstream request failed")
            self._log(
                "redis",
                "warning",
                f"Client pressure elevated; clients_by_name: worker={int(self.connections - 60)}, api=60",
            )
        self.healthy_ticks = self.healthy_ticks + 1 if self.healthy() else 0
        return self.observation()

    def metrics(self) -> dict[str, float]:
        pressure = max(0, (self.connections - 200) / 750)
        unavailable = self.status["redis"] != "running" or self.status["api"] != "running"
        return {
            "redis_connections": round(self.connections, 1),
            "redis_latency_ms": round(2 + pressure**2 * 180, 1),
            "api_latency_ms": 5000 if unavailable else round(180 + pressure**2 * 4100, 1),
            "api_error_rate": 100 if unavailable else round(0.2 + pressure**2 * 14, 2),
            "worker_open_clients": round(max(0, self.connections - 60), 1),
        }

    def healthy(self) -> bool:
        m = self.metrics()
        return (
            all(v == "running" for v in self.status.values())
            and m["redis_connections"] < 200
            and m["api_error_rate"] < 1
            and m["api_latency_ms"] < 300
        )

    def observation(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "metrics": self.metrics(),
            "services": [
                {"name": name, "status": state, "restarts": self.restarts[name]}
                for name, state in self.status.items()
            ],
            "dependencies": [{"from": "api", "to": "redis"}, {"from": "worker", "to": "redis"}],
            "healthy_ticks": self.healthy_ticks,
        }

    def restart(self, service: str) -> None:
        if service not in self.status:
            raise ValueError("Unknown service")
        self.status[service] = "running"
        self.restarts[service] += 1
        if service == "worker":
            self.leak_intensity = 0
            self.connections = 100 + (self.connections - 100) * 0.5
        self.healthy_ticks = 0
        self._log(
            service, "info", "Service restarted; owned connections closed and client pool reset"
        )
