"""Operator registration → authenticated inbox → isolated connector → real MCP repair."""

import asyncio
import json
import os
import sys

import httpx

from apps.agent.client import connect


async def wait_for(client, path, predicate, attempts=350):
    for _ in range(attempts):
        response = await client.get(path)
        response.raise_for_status()
        value = response.json()
        if predicate(value):
            return value
        await asyncio.sleep(0.08)
    raise AssertionError(f"Timed out waiting for {path}: {value}")


async def register(client, name="External diagnostic agent"):
    response = await client.post(
        "/api/agents",
        json={"name": name, "kind": "external", "description": "Independent MCP connector"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["agent"], body["credentials"]


async def test_registered_connector_receives_alert_and_repairs(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as client:
        agent, credentials = await register(client)
        assert agent["connection_status"] == "offline"
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "apps.agent.connector",
            "--url",
            live_lab,
            "--agent-id",
            agent["id"],
            "--mode",
            "reference",
            "--once",
            "--poll-seconds",
            "0.05",
            env=dict(
                os.environ,
                INCIDENTLAB_AGENT_TOKEN=credentials["token"],
                INCIDENTLAB_POLL_SECONDS="0.05",
                AGENT_POLL_SECONDS="0.08",
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await wait_for(
                client,
                "/api/agents",
                lambda items: any(
                    a["id"] == agent["id"] and a["connection_status"] == "online" for a in items
                ),
            )
            injection = await client.post(
                "/api/incidents", json={"agent_id": agent["id"], "auto_agent": True, "seed": 37}
            )
            assert injection.status_code == 201, injection.text
            incident_id = injection.json()["id"]
            result = await wait_for(
                client,
                f"/api/incidents/{incident_id}",
                lambda i: i["status"] in {"resolved", "failed", "cancelled"},
            )
            assert result["status"] == "resolved", result
            assert result["agent_id"] == agent["id"]
            assert result["agent_name"] == agent["name"]
            assert result["agent_mode"] == "external"
            assert result["evaluation"]["root_cause_correct"]
            assert result["evaluation"]["recovery_verified"]
            assert result["evaluation"]["action_count"] == 1
            out, err = await asyncio.wait_for(process.communicate(), timeout=10)
            assert process.returncode == 0, (out, err)
            assert credentials["token"].encode() not in out + err
            events = (await client.get("/api/events", params={"incident_id": incident_id})).json()
            types = [event["event_type"] for event in events]
            required = [
                "fault.injected",
                "alert.generated",
                "alert.dispatched",
                "agent.alert_received",
                "agent.started",
                "agent.hypothesis",
                "action.completed",
                "agent.verification",
                "incident.resolved",
            ]
            positions = [types.index(kind) for kind in required]
            assert positions == sorted(positions)
            for event in events:
                assert isinstance(event["payload"]["tick"], int), event
            assert types.count("agent.alert_received") == 1
            assert types.count("agent.started") == 1
            assert credentials["token"] not in json.dumps(events)
            assert "ground_truth" not in json.dumps(
                [e for e in events if e["event_type"] == "agent.tool_result"]
            )
            agents = (await client.get("/api/agents")).json()
            assert credentials["token"] not in json.dumps(agents)
        finally:
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=10)


async def test_inbox_redelivery_ack_isolation_and_revocation(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as client:
        owner, credentials = await register(client, "Owning agent")
        stranger, other_credentials = await register(client, "Other agent")
        owner_path = f"/api/agent-gateway/{owner['id']}"
        auth = {"Authorization": f"Bearer {credentials['token']}"}
        other_auth = {"Authorization": f"Bearer {other_credentials['token']}"}
        assert (await client.get(owner_path + "/next", headers=other_auth)).status_code in {
            401,
            403,
        }
        injected = await client.post("/api/incidents", json={"agent_id": owner["id"]})
        assert injected.status_code == 201, injected.text
        incident_id, run_id = injected.json()["id"], injected.json()["run_id"]
        await wait_for(
            client, f"/api/incidents/{incident_id}", lambda i: i["status"] == "dispatching"
        )
        before = (await client.get("/api/events", params={"incident_id": incident_id})).json()
        assert not any(e["event_type"] in {"agent.started", "agent.alert_received"} for e in before)
        assignment = (await client.get(owner_path + "/next", headers=auth)).json()["assignment"]
        duplicate = (await client.get(owner_path + "/next", headers=auth)).json()["assignment"]
        assert assignment == duplicate
        assert assignment["alert"]["status"] == "firing"
        assert assignment["run_id"] == run_id
        assert not {"scenario_id", "ground_truth", "evaluation", "seed"}.intersection(assignment)
        wrong = await client.post(
            f"/api/agent-gateway/{stranger['id']}/assignments/{run_id}/ack", headers=other_auth
        )
        assert wrong.status_code in {403, 404, 409, 410}
        for _ in range(2):
            ack = await client.post(owner_path + f"/assignments/{run_id}/ack", headers=auth)
            assert ack.status_code == 200, ack.text
        assert (await client.get(owner_path + "/next", headers=auth)).json()["assignment"] is None
        assert (
            await client.patch(f"/api/agents/{owner['id']}", json={"enabled": False})
        ).status_code == 409
        assert (await client.post(f"/api/agents/{owner['id']}/rotate-token")).status_code == 409
        await client.delete(f"/api/incidents/{incident_id}/agent")
        assert (await client.get(owner_path + "/next", headers=auth)).json()["assignment"] is None
        assert (
            await client.post(owner_path + f"/assignments/{run_id}/ack", headers=auth)
        ).status_code in {409, 410}
        async with connect(live_lab + "/mcp", assignment["token"]) as mcp:
            response = await mcp.session.call_tool("get_metrics", {})
            assert response.isError
        rotated = await client.post(f"/api/agents/{owner['id']}/rotate-token")
        assert rotated.status_code == 200
        assert rotated.json()["credentials"]["token"] != credentials["token"]
        assert (await client.post(owner_path + "/heartbeat", headers=auth)).status_code in {
            401,
            403,
        }
        events = (await client.get("/api/events", params={"incident_id": incident_id})).json()
        assert sum(e["event_type"] == "agent.started" for e in events) == 1
        assert sum(e["event_type"] == "agent.alert_received" for e in events) == 1
        assert credentials["token"] not in json.dumps(events)
        assert assignment["token"] not in json.dumps(events)
