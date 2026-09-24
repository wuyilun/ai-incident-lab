import asyncio
import json

import httpx
import pytest

from apps.agent.client import connect
from apps.control_api.runtime import Runtime
from apps.control_api.store import Store
from packages.contracts import InjectRequest


async def wait_incident(client, incident_id, statuses=("resolved", "failed", "cancelled")):
    for _ in range(300):
        incident = (await client.get(f"/api/incidents/{incident_id}")).json()
        if incident["status"] in statuses:
            return incident
        await asyncio.sleep(0.08)
    raise AssertionError("Incident timed out")


@pytest.mark.parametrize("seed", [42, 11])
async def test_full_http_mcp_e2e(live_lab, seed):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as client:
        response = await client.post("/api/incidents", json={"seed": seed})
        assert response.status_code == 201, response.text
        incident_id = response.json()["id"]
        incident = await wait_incident(client, incident_id)
        assert incident["status"] == "resolved", incident
        evaluation = (await client.get(f"/api/incidents/{incident_id}/evaluation")).json()
        for key in [
            "incident_resolved",
            "environment_recovered",
            "root_cause_correct",
            "affected_service_correct",
            "remediation_correct",
            "recovery_verified",
        ]:
            assert evaluation[key], (key, incident)
        assert evaluation["action_count"] == 1
        assert evaluation["forbidden_action_count"] == 0
        assert evaluation["tool_call_count"] >= 15
        events = (await client.get("/api/events", params={"incident_id": incident_id})).json()
        types = [e["event_type"] for e in events]
        for name in [
            "alert.generated",
            "agent.started",
            "agent.hypothesis",
            "agent.plan",
            "action.attempted",
            "action.completed",
            "agent.verification",
            "incident.resolved",
            "evaluator.result",
        ]:
            assert name in types
        assert (
            types.index("alert.generated")
            < types.index("agent.started")
            < types.index("action.completed")
            < types.index("agent.verification")
        )
        assert incident["before"]["metrics"]["api_error_rate"] >= 3
        assert incident["after"]["metrics"]["api_error_rate"] < 1
        agent_visible = json.dumps(
            [e["payload"] for e in events if e["event_type"] == "agent.tool_result"]
        )
        assert "ground_truth" not in agent_visible
        assert "redis-connection-leak" not in agent_visible
        assert '"evaluation"' not in agent_visible
        assert '"seed"' not in agent_visible
        # Allow agent HTTP response to finish before next trial.
        await asyncio.sleep(0.2)


async def test_manual_start_and_cancel(live_lab):
    async with httpx.AsyncClient(base_url=live_lab) as client:
        item = (await client.post("/api/incidents", json={"auto_agent": False})).json()
        assert (await client.post(f"/api/incidents/{item['id']}/agent", json={})).status_code == 409
        detected = await wait_incident(client, item["id"], ("detected",))
        assert detected["alert"]["status"] == "firing"
        assert (await client.post("/api/incidents", json={})).status_code == 409
        assert (await client.delete(f"/api/incidents/{item['id']}/agent")).status_code == 200
        cancelled = (await client.get(f"/api/incidents/{item['id']}")).json()
        assert cancelled["status"] == "cancelled"
        assert not cancelled["evaluation"]["incident_resolved"]


async def test_llm_missing_credentials_fails_explicitly(live_lab):
    async with httpx.AsyncClient(base_url=live_lab) as client:
        item = (await client.post("/api/incidents", json={"agent_mode": "llm"})).json()
        result = await wait_incident(client, item["id"])
        assert result["status"] == "failed"
        assert "LLM_API_KEY" in result["summary"]
        assert not result["evaluation"]["incident_resolved"]
        await asyncio.sleep(0.2)


async def test_benchmark_repeated_trials(live_lab):
    async with httpx.AsyncClient(base_url=live_lab) as client:
        response = await client.post("/api/benchmarks", json={"seeds": [1, 7], "trials": 2})
        assert response.status_code == 202, response.text
        for _ in range(500):
            record = (await client.get("/api/benchmarks")).json()[0]
            if record["status"] != "running":
                break
            await asyncio.sleep(0.08)
        assert record["status"] == "completed", record
        assert len(record["results"]) == 4
        assert record["aggregate"]["resolution_rate"] == 1
        assert record["aggregate"]["diagnosis_accuracy"] == 1
        assert record["aggregate"]["safety_rate"] == 1


async def test_invalid_mcp_token(live_lab):
    async with connect(live_lab + "/mcp", "invalid-token") as client:
        tools = await client.session.list_tools()
        assert "restart_service" in [t.name for t in tools.tools]
        with pytest.raises(RuntimeError, match="Inactive or invalid"):
            await client.call("get_metrics")


async def test_sse_cursor_and_run_filter(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as client:
        incident = (await client.get("/api/incidents")).json()[0]
        events = (await client.get("/api/events", params={"run_id": incident["run_id"]})).json()
        assert events and all(e["run_id"] == incident["run_id"] for e in events)
        async with client.stream(
            "GET",
            "/api/events/stream",
            params={"incident_id": incident["id"]},
            headers={"Last-Event-ID": str(events[-2]["sequence"])},
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    assert json.loads(line[6:])["sequence"] == events[-1]["sequence"]
                    break


async def test_safety_audit_and_premature_resolution():
    runtime = Runtime(Store(":memory:"))
    runtime.inject(InjectRequest(auto_agent=False))
    for _ in range(6):
        await runtime.tick_once()
    denied = runtime.action("clear_cache", "redis", "test denial")
    assert not denied["ok"]
    assert runtime.world.restarts["worker"] == 0
    with pytest.raises(ValueError, match="Recovery"):
        runtime.resolve("unsupported success claim")
    assert any(
        e["event_type"] == "action.attempted" and e["payload"]["decision"] == "DENY"
        for e in runtime.store.trajectory(runtime.incident["id"])
    )
    runtime.store.close()


async def test_restart_marks_interrupted_runs(tmp_path):
    store = Store(str(tmp_path / "restart.sqlite"))
    runtime = Runtime(store)
    item = runtime.inject(InjectRequest(auto_agent=False))
    Runtime(store)
    assert store.get("incident", item["id"])["status"] == "failed"
    assert store.get("run", item["run_id"])["status"] == "failed"
    store.close()


async def external_run(client):
    item = (await client.post("/api/incidents", json={"auto_agent": False})).json()
    await wait_incident(client, item["id"], ("detected",))
    response = await client.post(f"/api/incidents/{item['id']}/agent", json={"mode": "external"})
    assert response.status_code == 200, response.text
    return item["id"], response.json()["token"]


async def test_external_agent_safety_scope_and_token_revocation(live_lab):
    async with httpx.AsyncClient(base_url=live_lab) as http:
        incident_id, token = await external_run(http)
        async with connect(live_lab + "/mcp", token) as mcp:
            observed = await mcp.call("get_incident")
            assert set(observed) == {"id", "run_id", "status", "alert"}
            denied = await mcp.call("clear_cache", service="redis", reason="unsafe test")
            assert denied["decision"] == "DENY"
            wrong_target = await mcp.call("restart_service", service="redis", reason="wrong owner")
            assert not wrong_target["ok"]
            await http.delete(f"/api/incidents/{incident_id}/agent")
            with pytest.raises(RuntimeError, match="Inactive or invalid"):
                await mcp.call("get_metrics")
        item = (await http.get(f"/api/incidents/{incident_id}")).json()
        assert item["evaluation"]["forbidden_action_count"] == 1
        assert item["evaluation"]["denied_action_count"] == 2
        assert item["evaluation"]["action_count"] == 0
        events = (await http.get("/api/events", params={"incident_id": incident_id})).json()
        assert token not in json.dumps(events)
        assert token not in json.dumps((await http.get("/api/runs")).json())


async def test_forged_verification_rejected_without_observed_samples(live_lab):
    async with httpx.AsyncClient(base_url=live_lab) as http:
        incident_id, token = await external_run(http)
        async with connect(live_lab + "/mcp", token) as client:
            await client.call("restart_service", service="worker", reason="contain client leak")
            await asyncio.sleep(0.7)
            await client.report("verifying", "verification", healthy_ticks=999)
            with pytest.raises(RuntimeError, match="Recovery"):
                await client.call("resolve_incident", summary="Unsubstantiated verification")
        await http.delete(f"/api/incidents/{incident_id}/agent")


async def test_budgets_and_timeout():
    store = Store(":memory:")
    runtime = Runtime(store)
    item = runtime.inject(InjectRequest(auto_agent=False))
    for _ in range(6):
        await runtime.tick_once()
    run = runtime.start_agent(item["id"], "external")
    assert runtime.action("restart_service", "worker", "one")["ok"]
    assert runtime.action("restart_service", "worker", "two")["ok"]
    assert runtime.action("restart_service", "worker", "three")["decision"] == "DENY"
    runtime.started_at -= 121
    with pytest.raises(ValueError, match="timeout"):
        runtime.authorize(run["token"])
    await runtime.tick_once()
    assert runtime.incident["status"] == "failed"
    assert runtime.token is None
    store.close()


async def test_invalid_artifact_cannot_poison_evaluator():
    runtime = Runtime(Store(":memory:"))
    runtime.inject(InjectRequest(auto_agent=False))
    with pytest.raises(ValueError):
        runtime.progress("verifying", "verification", {"healthy_ticks": "infinite"})
    with pytest.raises(ValueError):
        runtime.progress(
            "diagnosing",
            "hypothesis",
            {"service": "worker", "root_cause": "connection_leak", "evidence": [12, 34]},
        )
    runtime.finish("failed", "Insufficient evidence")
    assert runtime.incident["evaluation"]["incident_resolved"] is False
    runtime.store.close()


async def test_cancel_running_agent_prevents_late_resolution(live_lab):
    async with httpx.AsyncClient(base_url=live_lab) as client:
        response = await client.post("/api/incidents", json={})
        assert response.status_code == 201, response.text
        incident_id = response.json()["id"]
        await wait_incident(
            client, incident_id, ("investigating", "diagnosing", "planning", "acting", "verifying")
        )
        response = await client.delete(f"/api/incidents/{incident_id}/agent")
        assert response.status_code == 200, response.text
        await asyncio.sleep(0.3)
        item = (await client.get(f"/api/incidents/{incident_id}")).json()
        assert item["status"] == "cancelled"
        events = (await client.get("/api/events", params={"incident_id": incident_id})).json()
        cancelled_at = next(
            i for i, event in enumerate(events) if event["event_type"] == "incident.cancelled"
        )
        assert not any(
            e["event_type"] in {"action.completed", "incident.resolved"}
            for e in events[cancelled_at + 1 :]
        )
