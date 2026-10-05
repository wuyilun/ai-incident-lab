"""Versioned wire contracts, independent of implementations."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(Contract):
    version: int = 1
    sequence: int = 0
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    event_type: str
    source: str
    incident_id: str | None = None
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class Fault(Contract):
    type: Literal[
        "connection_leak",
        "cpu_saturation",
        "slow_queries",
        "queue_backlog",
        "service_down",
        "connection_pool_exhaustion",
    ]
    intensity: float = Field(gt=0, le=1)


class Success(Contract):
    redis_connections_lt: int = Field(gt=100)
    api_error_rate_lt: float = Field(gt=0.2)
    api_latency_ms_lt: float = Field(gt=180)
    healthy_ticks: int = Field(default=3, ge=2, le=20)


class GroundTruth(Contract):
    root_cause: str
    affected_service: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")


class Scenario(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    description: str = ""
    metric: str = "redis_connections"
    severity: Literal["low", "medium", "high", "critical"]
    target: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    fault: Fault
    ground_truth: GroundTruth
    allowed_actions: list[str]
    forbidden_actions: list[str]
    success: Success

    @model_validator(mode="after")
    def disjoint_actions(self) -> "Scenario":
        if set(self.allowed_actions) & set(self.forbidden_actions):
            raise ValueError("allowed and forbidden actions overlap")
        return self


class InjectRequest(Contract):
    scenario_id: str = "redis-connection-leak"
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    auto_agent: bool = True
    agent_mode: Literal["reference", "llm"] = "reference"
    agent_id: str | None = None


class StartRequest(Contract):
    mode: Literal["reference", "llm", "external"] = "reference"
    agent_id: str | None = None


class AgentCreate(Contract):
    name: str = Field(min_length=1, max_length=80, pattern=r"\S")
    kind: Literal["reference", "llm", "external"]
    description: str = Field(default="", max_length=500)


class AgentUpdate(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"\S")
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class Hypothesis(Contract):
    root_cause: str = Field(min_length=1, max_length=100)
    service: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    evidence: list[str] = Field(min_length=2, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)


class Verification(Contract):
    healthy_ticks: int = Field(ge=0, strict=True)
    metrics: dict[str, float] = Field(default_factory=dict)
    evidence: str = ""


class BenchmarkRequest(Contract):
    scenario_id: str = "redis-connection-leak"
    seeds: list[int] = Field(default_factory=lambda: [42], min_length=1, max_length=10)
    trials: int = Field(default=3, ge=1, le=10)
    agent_mode: Literal["reference", "llm"] = "reference"
