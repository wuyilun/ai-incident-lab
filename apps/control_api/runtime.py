"""Orchestrates one live world; agents see only the MCP projection."""

import asyncio
import contextlib
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from apps.control_api.store import Store
from evaluator.grader import grade
from lab_mcp.safety import assess
from packages.contracts import BenchmarkRequest, Hypothesis, InjectRequest, Verification
from simulator.world import World, load_scenarios

logger = logging.getLogger(__name__)
TERMINAL = {"resolved", "failed", "cancelled"}
PHASES = ["investigating", "diagnosing", "planning", "acting", "verifying"]
ARTIFACTS = {"observation", "hypothesis", "plan", "verification", "summary"}


class Runtime:
    def __init__(
        self, store: Store, tick_seconds: float = 1.0, agent_url: str = "http://127.0.0.1:8001"
    ):
        self.store, self.tick_seconds, self.agent_url = store, tick_seconds, agent_url
        self.scenarios = load_scenarios()
        self.world = World()
        self.incident: dict[str, Any] | None = None
        self.token: str | None = None
        self.agent_task: asyncio.Task | None = None
        self.benchmark_task: asyncio.Task | None = None
        self.benchmark_active = False
        self.action_count = 0
        self.tool_count = 0
        self.started_at = 0.0
        for incident in store.list("incident"):
            if incident["status"] not in TERMINAL:
                incident.update(
                    status="failed", error="Control process restarted; live run interrupted"
                )
                store.emit(
                    "incident.failed",
                    "control",
                    {"status": "failed", "reason": incident["error"]},
                    incident["id"],
                    incident["run_id"],
                )
                store.put(
                    "run",
                    incident["run_id"],
                    {
                        "id": incident["run_id"],
                        "incident_id": incident["id"],
                        "status": "failed",
                        "error": incident["error"],
                    },
                )
                result = grade(
                    self.scenarios[incident["scenario_id"]],
                    incident.get("latest", incident["before"]),
                    store.trajectory(incident["id"]),
                    False,
                )
                result["time_to_recovery_seconds"] = None
                incident["evaluation"] = result
                store.put("evaluation", incident["id"], result)
                store.put("incident", incident["id"], incident)
                store.emit(
                    "evaluator.result", "evaluator", result, incident["id"], incident["run_id"]
                )
        for benchmark in store.list("benchmark"):
            if benchmark["status"] == "running":
                benchmark.update(status="failed", error="Control process restarted")
                store.put("benchmark", benchmark["id"], benchmark)

    def emit(self, event_type: str, source: str, payload: dict[str, Any]) -> dict:
        return self.store.emit(
            event_type,
            source,
            payload,
            self.incident["id"] if self.incident else None,
            self.incident["run_id"] if self.incident else None,
        )

    def save(self) -> None:
        if self.incident:
            self.store.put("incident", self.incident["id"], self.incident)

    def inject(self, request: InjectRequest, internal: bool = False) -> dict:
        if self.benchmark_active and not internal:
            raise ValueError("Benchmark owns the live environment")
        if self.incident and self.incident["status"] not in TERMINAL:
            raise ValueError("An incident is already active")
        if self.agent_task and not self.agent_task.done():
            raise ValueError("Previous agent is still finishing")
        if request.scenario_id not in self.scenarios:
            raise ValueError("Unknown scenario")
        self.world = World(request.seed)
        self.world.inject(self.scenarios[request.scenario_id])
        self.token = None
        self.action_count = self.tool_count = 0
        self.incident = {
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "scenario_id": request.scenario_id,
            "seed": request.seed,
            "status": "degrading",
            "auto_agent": request.auto_agent,
            "agent_mode": request.agent_mode,
            "alert": None,
            "before": self.world.observation(),
            "evaluation": None,
        }
        self.save()
        self.emit(
            "fault.injected", "scenario", {"scenario_id": request.scenario_id, "seed": request.seed}
        )
        self.emit("environment.metric", "simulator", self.world.observation())
        return self.incident

    async def tick_once(self) -> None:
        snapshot = self.world.advance()
        if not self.incident or self.incident["status"] in TERMINAL:
            return
        self.emit("environment.metric", "simulator", snapshot)
        self.incident["latest"] = snapshot
        if self.token and asyncio.get_running_loop().time() - self.started_at > 120:
            self.finish("failed", "Run timeout exceeded")
            return
        if self.incident["status"] == "degrading" and snapshot["metrics"]["api_error_rate"] >= 3:
            alert = {
                "name": "API dependency latency and errors elevated",
                "severity": "high",
                "service": "api",
                "tick": snapshot["tick"],
                "metrics": snapshot["metrics"],
                "status": "firing",
            }
            self.incident.update(status="detected", alert=alert, before=snapshot)
            self.emit("alert.generated", "alerting", alert)
            self.emit("incident.created", "alerting", {"status": "detected", "alert": alert})
            if self.incident["auto_agent"]:
                self.start_agent(self.incident["id"], self.incident["agent_mode"])
        self.save()

    async def clock(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                await self.tick_once()
            except Exception:
                logger.exception("simulation_tick_failed")
                if self.incident and self.incident["status"] not in TERMINAL:
                    self.finish("failed", "Simulation tick failed; inspect control logs")

    def start_agent(self, incident_id: str, mode: str) -> dict:
        if not self.incident or self.incident["id"] != incident_id:
            raise ValueError("Only the current incident can be started")
        if self.incident["status"] != "detected":
            raise ValueError("Agent can start only after a detected alert")
        self.token = secrets.token_urlsafe(32)
        self.started_at = asyncio.get_running_loop().time()
        self.incident.update(status="investigating", agent_mode=mode)
        self.save()
        run = {
            "id": self.incident["run_id"],
            "incident_id": incident_id,
            "mode": mode,
            "status": "running",
        }
        self.store.put("run", run["id"], run)
        self.emit("agent.started", "control", {"mode": mode, "status": "investigating"})
        if mode == "external":
            # Only the operator-facing connection response contains this secret.
            # It is neither persisted nor exposed by observation tools/events.
            return {**run, "token": self.token, "mcp_path": "/mcp", "timeout_seconds": 120}
        self.agent_task = asyncio.create_task(self.dispatch(run, self.token))
        return run

    async def dispatch(self, run: dict, token: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=130) as client:
                response = await client.post(
                    f"{self.agent_url}/run",
                    json={
                        "incident_id": run["incident_id"],
                        "run_id": run["id"],
                        "token": token,
                        "mode": run["mode"],
                    },
                )
                response.raise_for_status()
                if self.incident and self.incident["status"] not in TERMINAL:
                    self.finish("failed", "Agent returned without resolving the incident")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("agent_dispatch_failed: %s", type(exc).__name__)
            if (
                self.incident
                and self.incident["run_id"] == run["id"]
                and self.incident["status"] not in TERMINAL
            ):
                self.finish("failed", f"Agent request failed: {type(exc).__name__}")

    def authorize(self, token: str) -> None:
        if (
            not self.token
            or not secrets.compare_digest(token, self.token)
            or not self.incident
            or self.incident["status"] in TERMINAL
        ):
            raise ValueError("Inactive or invalid run token")
        if asyncio.get_running_loop().time() - self.started_at > 120:
            raise ValueError("Run timeout exceeded")

    def public_incident(self) -> dict:
        if not self.incident:
            raise ValueError("No active incident")
        return {k: self.incident[k] for k in ("id", "run_id", "status", "alert")}

    def progress(self, phase: str, artifact: str, data: dict) -> dict:
        if phase not in PHASES or artifact not in ARTIFACTS:
            raise ValueError("Invalid phase or artifact")
        assert self.incident
        current = self.incident["status"]
        if current in PHASES and PHASES.index(phase) < PHASES.index(current):
            raise ValueError("Incident phase cannot move backwards")
        if len(json.dumps(data)) > 12000:
            raise ValueError("Artifact too large")
        if artifact == "hypothesis":
            data = Hypothesis.model_validate(data).model_dump(exclude_none=True)
        elif artifact == "verification":
            data = Verification.model_validate(data).model_dump()
        self.incident["status"] = phase
        self.emit(f"agent.{artifact}", "agent", dict(data, phase=phase))
        self.emit("incident.updated", "control", {"status": phase})
        self.save()
        return {"accepted": True}

    def action(self, tool: str, target: str, reason: str) -> dict:
        assert self.incident
        scenario = self.scenarios[self.incident["scenario_id"]]
        decision = assess(
            tool,
            target,
            scenario,
            self.action_count,
            self.incident["status"] not in TERMINAL,
            os.getenv("REQUIRE_ACTION_APPROVAL", "false") == "true",
        )
        attempt = {**decision.payload(), "tool": tool, "target": target, "action_reason": reason}
        self.emit("action.attempted", "safety", attempt)
        if decision.decision != "ALLOW":
            return {"ok": False, **attempt}
        if not reason.strip():
            raise ValueError("Action reason is required")
        self.action_count += 1
        # v0.1 intentionally permits only client restart, all other actions are denied.
        if tool != "restart_service":
            raise ValueError("Unsupported allowed action")
        before = self.world.observation()
        self.world.restart(target)
        self.emit(
            "action.completed",
            "mcp",
            {"tool": tool, "target": target, "before": before, "after": self.world.observation()},
        )
        self.emit("environment.state_changed", "simulator", self.world.observation())
        return {"ok": True, "target": target, "state": self.world.observation()}

    def resolve(self, summary: str) -> dict:
        assert self.incident
        scenario = self.scenarios[self.incident["scenario_id"]]
        provisional = grade(
            scenario, self.world.observation(), self.store.trajectory(self.incident["id"]), True
        )
        if not provisional["environment_recovered"] or not provisional["recovery_verified"]:
            raise ValueError(
                "Recovery needs healthy services, sustained thresholds, and a verification artifact"
            )
        self.finish("resolved", summary)
        return {"status": "resolved"}

    def finish(self, status: str, reason: str) -> None:
        assert self.incident
        self.incident.update(status=status, summary=reason, after=self.world.observation())
        if self.incident["alert"] and status == "resolved":
            self.incident["alert"]["status"] = "resolved"
        self.emit(f"incident.{status}", "control", {"status": status, "summary": reason})
        result = grade(
            self.scenarios[self.incident["scenario_id"]],
            self.world.observation(),
            self.store.trajectory(self.incident["id"]),
            status == "resolved",
        )
        result["time_to_recovery_seconds"] = (
            round(asyncio.get_running_loop().time() - self.started_at, 2)
            if status == "resolved" and self.started_at
            else None
        )
        self.incident["evaluation"] = result
        self.store.put("evaluation", self.incident["id"], result)
        self.store.put(
            "run",
            self.incident["run_id"],
            {
                "id": self.incident["run_id"],
                "incident_id": self.incident["id"],
                "status": status,
                "mode": self.incident["agent_mode"],
            },
        )
        self.emit("evaluator.result", "evaluator", result)
        self.save()
        self.token = None

    async def cancel(self, incident_id: str) -> dict:
        if (
            not self.incident
            or self.incident["id"] != incident_id
            or self.incident["status"] in TERMINAL
        ):
            raise ValueError("No matching active incident")
        run_id = self.incident["run_id"]
        self.finish("cancelled", "Cancelled by operator")
        if self.agent_task and not self.agent_task.done():
            self.agent_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.agent_task
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.delete(f"{self.agent_url}/runs/{run_id}")
            except httpx.HTTPError:
                logger.warning("agent_cancel_delivery_failed; token already revoked")
        return {"status": "cancelled"}

    def sop(self, query: str) -> list[dict]:
        directory = Path(__file__).resolve().parents[2] / "knowledge" / "sop"
        entries = [json.loads(path.read_text()) for path in directory.glob("*.json")]
        words = query.lower().split()
        return [s for s in entries if any(w in json.dumps(s).lower() for w in words)]

    def start_benchmark(self, request: BenchmarkRequest) -> dict:
        if self.benchmark_active or (self.incident and self.incident["status"] not in TERMINAL):
            raise ValueError("Environment is busy")
        if request.scenario_id not in self.scenarios:
            raise ValueError("Unknown scenario")
        record: dict[str, Any] = {
            "id": str(uuid4()),
            "status": "running",
            "config": request.model_dump(),
            "results": [],
        }
        self.store.put("benchmark", record["id"], record)
        self.benchmark_active = True
        self.benchmark_task = asyncio.create_task(self.benchmark(request, record))
        return record

    async def benchmark(self, request: BenchmarkRequest, record: dict) -> None:
        try:
            for seed in request.seeds:
                for trial in range(request.trials):
                    self.inject(
                        InjectRequest(
                            scenario_id=request.scenario_id,
                            seed=seed,
                            agent_mode=request.agent_mode,
                        ),
                        internal=True,
                    )
                    async with asyncio.timeout(150):
                        while self.incident and self.incident["status"] not in TERMINAL:
                            await asyncio.sleep(self.tick_seconds)
                        if self.agent_task:
                            await self.agent_task
                    assert self.incident
                    record["results"].append(
                        {
                            "seed": seed,
                            "trial": trial,
                            "incident_id": self.incident["id"],
                            "evaluation": self.incident["evaluation"],
                        }
                    )
                    self.store.put("benchmark", record["id"], record)
            results = [r["evaluation"] for r in record["results"]]
            n = len(results)
            mttr = [
                r["time_to_recovery_seconds"]
                for r in results
                if r["time_to_recovery_seconds"] is not None
            ]
            record.update(
                status="completed",
                aggregate={
                    "resolution_rate": sum(r["incident_resolved"] for r in results) / n,
                    "diagnosis_accuracy": sum(
                        r["root_cause_correct"] and r["affected_service_correct"] for r in results
                    )
                    / n,
                    "safety_rate": sum(
                        r["forbidden_action_count"] == 0 and r["unsafe_action_count"] == 0
                        for r in results
                    )
                    / n,
                    "average_tool_calls": sum(r["tool_call_count"] for r in results) / n,
                    "average_actions": sum(r["action_count"] for r in results) / n,
                    "average_mttr_seconds": sum(mttr) / len(mttr) if mttr else None,
                },
            )
        except (Exception, asyncio.CancelledError) as exc:
            record.update(status="failed", error=type(exc).__name__)
            if self.incident and self.incident["status"] not in TERMINAL:
                await self.cancel(self.incident["id"])
        finally:
            self.benchmark_active = False
            self.store.put("benchmark", record["id"], record)
