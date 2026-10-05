import asyncio

import httpx
import pytest
from pydantic import ValidationError

from apps.agent.client import connect
from apps.agent.reference import run_reference
from apps.control_api.leaderboard import leaderboard
from apps.control_api.store import Store
from simulator.environment import Environment, load_environment
from simulator.world import World, load_scenarios


@pytest.mark.parametrize("scenario_id", list(load_scenarios()))
def test_each_fault_has_causal_metrics_and_correct_scoped_repair(scenario_id):
    scenario = load_scenarios()[scenario_id]
    world = World(42)
    world.inject(scenario)
    history = [world.advance() for _ in range(8)]
    assert history[-1]["metrics"]["api_error_rate"] >= 3
    assert not world.healthy()
    assert any(s["health"] != "healthy" for s in history[-1]["services"])
    world.restart("gateway")
    world.advance()
    assert not world.healthy()
    world.restart(scenario.target)
    for _ in range(12):
        world.advance()
    assert world.healthy() and world.healthy_ticks >= 3
    assert world.metrics()[scenario.metric] < history[-1]["metrics"][scenario.metric]


def test_topology_extension_and_validation():
    data = load_environment().model_dump(by_alias=True)
    data["services"].append(
        {"name": "search", "label": "Search", "kind": "search", "config": {}, "metric_keys": []}
    )
    data["dependencies"].append({"from": "api", "to": "search"})
    world = World(environment=Environment.model_validate(data))
    assert "search" in world.status
    assert any(
        e["from"] == "api" and e["to"] == "search" for e in world.observation()["dependencies"]
    )
    world.restart("search")
    assert world.restarts["search"] == 1
    data["dependencies"].append({"from": "ghost", "to": "api"})
    with pytest.raises(ValidationError):
        Environment.model_validate(data)


async def test_one_registered_mcp_agent_repairs_all_scenarios_and_is_ranked(live_lab):
    async with httpx.AsyncClient(base_url=live_lab, timeout=5) as operator:
        registration = (
            await operator.post(
                "/api/agents", json={"name": "Multi-scenario MCP", "kind": "external"}
            )
        ).json()
        agent_id, token = registration["agent"]["id"], registration["credentials"]["token"]
        scenarios = (await operator.get("/api/scenarios")).json()
        assert len(scenarios) == len(load_scenarios())
        for scenario in scenarios:
            async with connect(live_lab + "/mcp", token) as client:
                await client.call("check_connection")
                response = await operator.post(
                    "/api/incidents", json={"scenario_id": scenario["id"], "agent_id": agent_id}
                )
                assert response.status_code == 201, response.text
                incident = response.json()
                for _ in range(100):
                    assignment = (await client.call("receive_alert"))["assignment"]
                    if assignment:
                        break
                    await asyncio.sleep(0.08)
                else:
                    pytest.fail("No alert received")
                await run_reference(client, poll_seconds=0.08)
                result = (await operator.get(f"/api/incidents/{incident['id']}")).json()
                assert result["status"] == "resolved", result
                assert result["evaluation"]["root_cause_correct"], result
                assert result["evaluation"]["recovery_verified"], result
                assert result["evaluation"]["action_count"] == 1
        board = (await operator.get("/api/leaderboard")).json()
        row = next(r for r in board["entries"] if r["agent_id"] == agent_id)
        assert row["rank"] == 1 and row["score"] == 100
        assert row["scenario_count"] == row["sample_count"] == len(scenarios)
        assert row["resolution_rate"] == row["diagnosis_accuracy"] == row["safety_rate"] == 1
        filtered = (
            await operator.get("/api/leaderboard", params={"scenario_id": scenarios[0]["id"]})
        ).json()
        assert filtered["total_scenarios"] == 1
        assert (
            next(r for r in filtered["entries"] if r["agent_id"] == agent_id)["sample_count"] == 1
        )


def test_ranking_balances_scenarios_and_excludes_cancelled(tmp_path):
    store = Store(str(tmp_path / "ranking.sqlite"))
    for agent_id in ("broad", "narrow", "untested"):
        store.put("agent", agent_id, {"id": agent_id, "name": agent_id, "kind": "external"})
    good = {
        "incident_resolved": True,
        "recovery_verified": True,
        "root_cause_correct": True,
        "affected_service_correct": True,
        "tool_call_count": 20,
        "time_to_recovery_seconds": 2,
    }
    for index in range(12):
        store.put(
            "incident",
            f"n-{index}",
            {"agent_id": "narrow", "scenario_id": "a", "status": "resolved", "evaluation": good},
        )
    for scenario in ("a", "b"):
        store.put(
            "incident",
            f"b-{scenario}",
            {
                "agent_id": "broad",
                "scenario_id": scenario,
                "status": "resolved",
                "evaluation": good,
            },
        )
    store.put(
        "incident",
        "cancel",
        {"agent_id": "broad", "scenario_id": "a", "status": "cancelled", "evaluation": {}},
    )
    board = leaderboard(store, {"a", "b"})
    assert [r["agent_id"] for r in board["entries"]] == ["broad", "narrow", "untested"]
    assert [r["score"] for r in board["entries"]] == [100, 50, None]
    assert board["entries"][0]["sample_count"] == 2
    assert board["entries"][2]["rank"] is None
    store.close()
