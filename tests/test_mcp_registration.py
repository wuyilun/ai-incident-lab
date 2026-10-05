"""A single registration token supports the complete official MCP agent lifecycle."""

import asyncio
import json

import httpx
import pytest

from apps.agent.client import connect
from apps.agent.reference import run_reference


async def register(client, name):
    response = await client.post("/api/agents", json={"name": name, "kind": "external"})
    assert response.status_code == 201, response.text
    return response.json()


async def dispatch(client, agent_id):
    response = await client.post(
        "/api/incidents", json={"agent_id": agent_id, "scenario_id": "redis-connection-leak"}
    )
    assert response.status_code == 201, response.text
    incident = response.json()
    for _ in range(120):
        response = await client.get(f"/api/incidents/{incident['id']}")
        if response.json()["status"] == "dispatching":
            return response.json()
        await asyncio.sleep(0.05)
    raise AssertionError("Alert was not dispatched")


async def test_registration_token_full_mcp_lifecycle(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as operator:
        registered = await register(operator, "Direct MCP Agent")
        agent_id, token = registered["agent"]["id"], registered["credentials"]["token"]
        assert registered["credentials"]["mcp_path"] == "/mcp"
        async with connect(live_lab + "/mcp", token) as agent:
            listed = await agent.session.list_tools()
            assert {"check_connection", "receive_alert", "get_diagnostic_skill"} <= {
                tool.name for tool in listed.tools
            }
            identity = await agent.call("check_connection")
            assert identity["agent"]["id"] == agent_id
            assert identity["agent"]["connection_status"] == "online"
            assert identity["heartbeat_ttl_seconds"] == 15
            assert "token" not in json.dumps(identity)
            assert await agent.call("receive_alert") == {"assignment": None}
            with pytest.raises(RuntimeError, match="No acknowledged active assignment"):
                await agent.call("get_metrics")
            with pytest.raises(RuntimeError, match="No acknowledged active assignment"):
                await agent.call("get_diagnostic_skill")
            incident = await dispatch(operator, agent_id)
            with pytest.raises(RuntimeError, match="No acknowledged active assignment"):
                await agent.call("get_incident")
            assignment = (await agent.call("receive_alert"))["assignment"]
            assert assignment["incident_id"] == incident["id"]
            assert assignment["run_id"] == incident["run_id"]
            assert assignment["alert"]["status"] == "firing"
            assert (
                not {"scenario_id", "seed", "ground_truth", "evaluation", "token"}
                & assignment.keys()
            )
            assert (await agent.call("receive_alert"))["assignment"] == assignment
            skill = await agent.call("get_diagnostic_skill")
            assert skill["name"] == "diagnose.md"
            assert "Observe:" in skill["content"] and "Verify:" in skill["content"]
            for private in ("ground_truth", "scenario_id", '"seed"', '"evaluation"'):
                assert private not in json.dumps(skill)
            await run_reference(agent, poll_seconds=0.08)
            assert agent.resolved
            with pytest.raises(RuntimeError, match="No acknowledged active assignment"):
                await agent.call("get_metrics")
            assert await agent.call("receive_alert") == {"assignment": None}
            assert (await agent.call("check_connection"))["agent"]["id"] == agent_id
        result = (await operator.get(f"/api/incidents/{incident['id']}")).json()
        assert result["status"] == "resolved"
        assert result["evaluation"]["root_cause_correct"]
        assert result["evaluation"]["recovery_verified"]
        events = (await operator.get("/api/events", params={"incident_id": incident["id"]})).json()
        received = [event for event in events if event["event_type"] == "agent.alert_received"]
        assert len(received) == 1 and received[0]["payload"]["via"] == "mcp.receive_alert"
        assert sum(event["event_type"] == "agent.started" for event in events) == 1
        assert token not in json.dumps(events)
        visible = json.dumps([event for event in events if event["source"] in {"agent", "mcp"}])
        for private in ("ground_truth", "scenario_id", '"seed"', '"evaluation"'):
            assert private not in visible


async def test_direct_mcp_isolation_rotation_and_disabled_registration(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as operator:
        owner = await register(operator, "MCP owner")
        stranger = await register(operator, "MCP stranger")
        owner_id, token = owner["agent"]["id"], owner["credentials"]["token"]
        async with (
            connect(live_lab + "/mcp", token) as agent,
            connect(live_lab + "/mcp", stranger["credentials"]["token"]) as other,
        ):
            incident = await dispatch(operator, owner_id)
            assert await other.call("receive_alert") == {"assignment": None}
            with pytest.raises(RuntimeError, match="No acknowledged active assignment"):
                await other.call("get_logs", service="worker")
            await agent.call("receive_alert")
            with pytest.raises(RuntimeError, match="No acknowledged active assignment"):
                await other.call("restart_service", service="worker", reason="Not my assignment")
            denied = await agent.call("clear_cache", service="redis", reason="Verify safety policy")
            assert denied["decision"] == "DENY"
            await operator.delete(f"/api/incidents/{incident['id']}/agent")
            with pytest.raises(RuntimeError, match="No acknowledged active assignment"):
                await agent.call("restart_service", service="worker", reason="Cancelled run")
            rotated = await operator.post(f"/api/agents/{owner_id}/rotate-token")
            replacement = rotated.json()["credentials"]["token"]
            for tool in ("check_connection", "receive_alert", "get_metrics"):
                with pytest.raises(RuntimeError, match="[Ii]nvalid"):
                    await agent.call(tool)
        async with connect(live_lab + "/mcp", replacement) as agent:
            assert (await agent.call("check_connection"))["agent"]["id"] == owner_id
            disabled = await operator.patch(f"/api/agents/{owner_id}", json={"enabled": False})
            assert disabled.status_code == 200
            for tool in ("check_connection", "receive_alert", "get_metrics"):
                with pytest.raises(RuntimeError, match="[Ii]nvalid"):
                    await agent.call(tool)
        events = (await operator.get("/api/events", params={"incident_id": incident["id"]})).json()
        assert not any(event["event_type"] == "action.completed" for event in events)
        attempts = [event for event in events if event["event_type"] == "action.attempted"]
        assert len(attempts) == 1 and attempts[0]["payload"]["decision"] == "DENY"
        for secret in (token, replacement, stranger["credentials"]["token"]):
            assert secret not in json.dumps(events)


async def test_late_mutations_cannot_cross_registered_runs(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as operator:
        owner = await register(operator, "Sequential MCP Agent")
        agent_id, token = owner["agent"]["id"], owner["credentials"]["token"]
        async with connect(live_lab + "/mcp", token) as agent:
            first = await dispatch(operator, agent_id)
            await agent.call("receive_alert")
            assert agent.run_id == first["run_id"]
            await operator.delete(f"/api/incidents/{first['id']}/agent")
            second = await dispatch(operator, agent_id)
            await agent.call("receive_alert")
            assert agent.run_id == second["run_id"]
            mutations = {
                "restart_service": {"service": "worker", "reason": "Late restart"},
                "stop_service": {"service": "worker", "reason": "Late stop"},
                "clear_cache": {"service": "redis", "reason": "Late cache clear"},
                "report_progress": {
                    "phase": "diagnosing",
                    "artifact": "summary",
                    "data": {"text": "Late report"},
                },
                "resolve_incident": {"summary": "Late resolution"},
                "fail_incident": {"reason": "Late failure"},
            }
            for name, arguments in mutations.items():
                for stale in ({}, {"run_id": first["run_id"]}):
                    result = await agent.session.call_tool(name, {**arguments, **stale})
                    assert result.isError, (name, result)
                    assert "run_id must match" in str(result.content)
            observed = await agent.call("get_service_status")
            assert all(service["restarts"] == 0 for service in observed)
            active = (await operator.get(f"/api/incidents/{second['id']}")).json()
            assert active["status"] == "investigating"
            await agent.report("investigating", "observation", text="Current run only")
            repaired = await agent.call("restart_service", service="worker", reason="Current run")
            assert repaired["ok"]
            await agent.call("fail_incident", reason="Scope test complete")
        events = (await operator.get("/api/events", params={"incident_id": second["id"]})).json()
        rejected = [event for event in events if event["event_type"] == "agent.tool_rejected"]
        assert len(rejected) == 12
        assert sum(event["event_type"] == "action.completed" for event in events) == 1
        assert sum(event["event_type"] == "agent.observation" for event in events) == 1
        assert not any(event["event_type"] == "agent.summary" for event in events)
