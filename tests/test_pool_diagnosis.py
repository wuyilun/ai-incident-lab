"""Pool starvation needs owner evidence plus a healthy database contrast."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from apps.agent.client import connect
from apps.agent.reference import run_reference

SOP = json.loads(Path("knowledge/sop/database-pool-pressure.json").read_text())
TIMEOUT = "Connection acquisition timed out; pool wait queue growing"


class Observations:
    """Only the observable MCP contract, with independently adjustable evidence."""

    def __init__(self):
        self.metrics = {
            "db_pool_active": 100,
            "db_pool_wait_ms": 1500,
            "database_latency_ms": 20,
            "api_cpu_percent": 25,
            "api_latency_ms": 2200,
            "api_error_rate": 12,
            "redis_connections": 100,
            "queue_depth": 20,
        }
        self.states = dict.fromkeys(("api", "payment", "worker", "db_proxy", "database"), "running")
        self.dependencies = [
            {"from": name, "to": "db_proxy"} for name in ("api", "payment", "worker")
        ] + [{"from": "db_proxy", "to": "database"}]
        self.logs = {
            name: [{"message": "Dependency timeout waiting for db_proxy"}]
            for name in ("api", "payment", "worker")
        }
        self.logs["db_proxy"] = [{"message": TIMEOUT}, {"message": TIMEOUT}]
        self.logs["database"] = [{"message": "Query execution healthy"}]
        self.config = {"db_proxy": {"pool_limit": 100}}
        self.actions = []
        self.reports = []
        self.recovery_override = {}
        self.tick = 5
        self.resolved = False

    async def call(self, name, **arguments):
        if name == "get_incident":
            return {"id": "incident-observation"}
        if name == "get_alerts":
            return [{"name": "API errors elevated", "service": "api"}]
        if name == "get_dependencies":
            return self.dependencies
        if name == "get_service_status":
            return [{"name": name, "status": status} for name, status in self.states.items()]
        if name == "get_logs":
            return self.logs.get(arguments["service"], [])
        if name == "get_config":
            return self.config.get(arguments["service"], {})
        if name == "get_metrics":
            self.tick += 1
            metrics = dict(self.metrics)
            if self.actions:
                metrics.update(
                    db_pool_active=12, db_pool_wait_ms=10, api_latency_ms=180, api_error_rate=0.2
                )
                metrics.update(self.recovery_override)
            return {
                "tick": self.tick,
                "metrics": metrics,
                "services": await self.call("get_service_status"),
                "history": [{"redis_connections": 100}, {"redis_connections": 100}],
                "healthy_ticks": 3,
            }
        if name == "get_sop":
            assert arguments["query"] == "pool-acquisition-timeout"
            return [SOP]
        if name == "restart_service":
            self.actions.append(arguments)
            return {"ok": True}
        if name == "resolve_incident":
            self.resolved = True
            return {"status": "resolved"}
        raise AssertionError(name)

    async def report(self, phase, artifact, **data):
        self.reports.append({"phase": phase, "artifact": artifact, **data})


async def test_pool_owner_diagnosis_uses_database_contrast():
    observed = Observations()
    await run_reference(observed, poll_seconds=0)
    assert observed.resolved
    assert [action["service"] for action in observed.actions] == ["db_proxy"]
    diagnosis = next(report for report in observed.reports if report["artifact"] == "hypothesis")
    assert diagnosis["root_cause"] == "connection_pool_exhaustion"
    assert diagnosis["service"] == "db_proxy"
    assert "query latency=20" in " ".join(diagnosis["evidence"])
    assert "100/100" in " ".join(diagnosis["evidence"])


@pytest.mark.parametrize(
    "missing",
    ["occupancy", "wait", "repeated_logs", "healthy_database", "database_edge", "normal_cpu"],
)
async def test_timeout_cascade_alone_does_not_justify_restart(missing):
    observed = Observations()
    if missing == "occupancy":
        observed.metrics["db_pool_active"] = 25
    elif missing == "wait":
        observed.metrics["db_pool_wait_ms"] = 5
    elif missing == "repeated_logs":
        observed.logs["db_proxy"] = [{"message": TIMEOUT}]
    elif missing == "healthy_database":
        observed.metrics["database_latency_ms"] = 800
    elif missing == "database_edge":
        observed.dependencies = [edge for edge in observed.dependencies if edge["to"] != "database"]
    else:
        observed.metrics["api_cpu_percent"] = 95
    with pytest.raises(RuntimeError, match="no unique failure and owner"):
        await run_reference(observed, poll_seconds=0)
    assert observed.actions == []
    assert not observed.resolved


async def test_ambiguous_pool_owner_blocks_repair():
    observed = Observations()
    observed.states["second_pool"] = "running"
    observed.dependencies.append({"from": "second_pool", "to": "database"})
    observed.logs["second_pool"] = list(observed.logs["db_proxy"])
    observed.config["second_pool"] = {"pool_limit": 100}
    with pytest.raises(RuntimeError, match="no unique failure and owner"):
        await run_reference(observed, poll_seconds=0)
    assert observed.actions == []


@pytest.mark.parametrize("unrecovered", [{"db_pool_active": 80}, {"db_pool_wait_ms": 150}])
async def test_api_recovery_cannot_mask_unrecovered_pool(unrecovered):
    observed = Observations()
    observed.recovery_override = unrecovered
    with pytest.raises(RuntimeError, match="Recovery verification timed out"):
        await run_reference(observed, poll_seconds=0)
    assert observed.actions[0]["service"] == "db_proxy"
    assert not observed.resolved
    assert not any(report["artifact"] == "verification" for report in observed.reports)


async def test_pool_exhaustion_repairs_through_registered_mcp(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as operator:
        registration = await operator.post(
            "/api/agents", json={"name": "Pool diagnostician", "kind": "external"}
        )
        assert registration.status_code == 201, registration.text
        agent = registration.json()
        injection = await operator.post(
            "/api/incidents",
            json={
                "scenario_id": "db-connection-pool-exhaustion",
                "agent_id": agent["agent"]["id"],
            },
        )
        assert injection.status_code == 201, injection.text
        incident_id = injection.json()["id"]
        async with connect(live_lab + "/mcp", agent["credentials"]["token"]) as client:
            for _ in range(100):
                received = await client.call("receive_alert")
                if received["assignment"]:
                    break
                await asyncio.sleep(0.08)
            else:
                raise AssertionError("Pool alert not received")
            await run_reference(client, poll_seconds=0.08)
            assert client.resolved
        result = (await operator.get(f"/api/incidents/{incident_id}")).json()
        assert result["status"] == "resolved"
        assert result["evaluation"]["root_cause_correct"]
        assert result["evaluation"]["affected_service_correct"]
        assert result["evaluation"]["recovery_verified"]
        events = (await operator.get("/api/events", params={"incident_id": incident_id})).json()
        completed = [
            event["payload"] for event in events if event["event_type"] == "action.completed"
        ]
        assert len(completed) == 1 and completed[0]["target"] == "db_proxy"
        assert result["after"]["metrics"]["db_pool_active"] < 70
        assert result["after"]["metrics"]["db_pool_wait_ms"] < 100
        assert result["after"]["metrics"]["database_latency_ms"] == 20
