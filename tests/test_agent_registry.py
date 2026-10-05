import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from apps.control_api.runtime import Runtime
from apps.control_api.store import Store
from packages.contracts import AgentCreate, AgentUpdate, InjectRequest


@pytest.fixture
def runtime():
    store = Store(":memory:")
    runtime = Runtime(store)
    yield runtime
    store.close()


def register(runtime, name="External"):
    return runtime.registry.create(AgentCreate(name=name, kind="external"))


async def dispatch(runtime, agent_id):
    incident = runtime.inject(InjectRequest(agent_id=agent_id))
    for _ in range(20):
        await runtime.tick_once()
        if incident["status"] == "dispatching":
            return incident
    raise AssertionError("No alert was dispatched")


def test_registration_hash_rotation_and_heartbeat(runtime):
    created = register(runtime)
    item, credentials = created["agent"], created["credentials"]
    agent_id, token = item["id"], credentials["token"]
    assert item["connection_status"] == "offline"
    assert token not in json.dumps(runtime.store.list("agent"))
    assert "token_hash" not in json.dumps(runtime.registry.list())
    assert "token" not in json.dumps(runtime.registry.list())
    runtime.registry.authenticate(agent_id, token)
    other = register(runtime, "Other")
    with pytest.raises(PermissionError):
        runtime.registry.authenticate(other["agent"]["id"], token)
    runtime.registry.touch(agent_id)
    assert runtime.registry.public(runtime.registry.get(agent_id))["connection_status"] == "online"
    stored = runtime.registry.get(agent_id)
    stored["last_seen"] = (datetime.now(UTC) - timedelta(seconds=16)).isoformat()
    runtime.store.put("agent", agent_id, stored)
    assert runtime.registry.public(stored)["connection_status"] == "offline"
    rotated = runtime.registry.rotate(agent_id)["credentials"]["token"]
    with pytest.raises(PermissionError):
        runtime.registry.authenticate(agent_id, token)
    runtime.registry.authenticate(agent_id, rotated)
    runtime.registry.update(agent_id, AgentUpdate(enabled=False))
    with pytest.raises(PermissionError):
        runtime.registry.authenticate(agent_id, rotated)
    with pytest.raises(ValueError, match="disabled"):
        runtime.inject(InjectRequest(agent_id=agent_id))


async def test_assignment_ack_scope_idempotency_and_revocation(runtime):
    created, other = register(runtime), register(runtime, "Other")
    agent_id = created["agent"]["id"]
    incident = await dispatch(runtime, agent_id)
    run_id = incident["run_id"]
    first = runtime.next_assignment(agent_id)["assignment"]
    assert first and first == runtime.next_assignment(agent_id)["assignment"]
    assert runtime.next_assignment(other["agent"]["id"]) == {"assignment": None}
    assert not {"scenario_id", "seed", "ground_truth", "evaluation"} & first.keys()
    with pytest.raises(ValueError, match="Acknowledge"):
        runtime.authorize(first["token"])
    with pytest.raises(PermissionError):
        runtime.registry.authenticate(agent_id, first["token"])
    with pytest.raises(ValueError, match="invalid"):
        runtime.authorize(created["credentials"]["token"])
    with pytest.raises(ValueError, match="No active assignment"):
        runtime.acknowledge(other["agent"]["id"], run_id)
    with pytest.raises(ValueError, match="No active assignment"):
        runtime.acknowledge(agent_id, "different-run")
    with pytest.raises(ValueError, match="active"):
        runtime.registry.update(agent_id, AgentUpdate(enabled=False))
    with pytest.raises(ValueError, match="active"):
        runtime.registry.rotate(agent_id)
    assert runtime.acknowledge(agent_id, run_id) == {"accepted": True}
    started = runtime.started_at
    assert runtime.acknowledge(agent_id, run_id) == {"accepted": True}
    assert runtime.started_at == started
    runtime.authorize(first["token"])
    assert runtime.next_assignment(agent_id) == {"assignment": None}
    events = runtime.store.trajectory(incident["id"])
    for name in ("agent.alert_received", "agent.started"):
        assert sum(e["event_type"] == name for e in events) == 1
    assert all(isinstance(e["payload"]["tick"], int) for e in events)
    assert first["token"] not in json.dumps(events)
    assert created["credentials"]["token"] not in json.dumps(events)
    await runtime.cancel(incident["id"])
    with pytest.raises(ValueError, match="No active assignment"):
        runtime.acknowledge(agent_id, run_id)
    with pytest.raises(ValueError, match="invalid"):
        runtime.authorize(first["token"])
    assert runtime.registry.rotate(agent_id)["credentials"]["token"]


@pytest.mark.parametrize("entrypoint", ["tick", "next", "ack"])
async def test_unacknowledged_assignment_expires(runtime, entrypoint):
    agent_id = register(runtime)["agent"]["id"]
    incident = await dispatch(runtime, agent_id)
    runtime.dispatched_at = asyncio.get_running_loop().time() - 31
    if entrypoint == "tick":
        await runtime.tick_once()
    elif entrypoint == "next":
        assert runtime.next_assignment(agent_id) == {"assignment": None}
    else:
        with pytest.raises(ValueError, match="expired"):
            runtime.acknowledge(agent_id, incident["run_id"])
    assert incident["status"] == "failed"
    assert runtime.token is None
    assert not any(
        event["event_type"] == "agent.alert_received"
        for event in runtime.store.trajectory(incident["id"])
    )


async def test_acknowledged_assignment_has_bounded_execution(runtime):
    agent_id = register(runtime)["agent"]["id"]
    incident = await dispatch(runtime, agent_id)
    runtime.acknowledge(agent_id, incident["run_id"])
    runtime.started_at -= 121
    with pytest.raises(ValueError, match="expired"):
        runtime.acknowledge(agent_id, incident["run_id"])
    assert incident["status"] == "failed"
    assert runtime.token is None


async def test_restart_preserves_registration_but_revokes_assignment(tmp_path):
    store = Store(str(tmp_path / "registry.sqlite"))
    runtime = Runtime(store)
    registration = register(runtime)
    agent_id, token = registration["agent"]["id"], registration["credentials"]["token"]
    runtime.registry.touch(agent_id)
    incident = await dispatch(runtime, agent_id)
    run_token = runtime.next_assignment(agent_id)["assignment"]["token"]
    restarted = Runtime(store)
    restarted.registry.authenticate(agent_id, token)
    assert (
        restarted.registry.public(restarted.registry.get(agent_id))["connection_status"]
        == "offline"
    )
    assert restarted.next_assignment(agent_id) == {"assignment": None}
    assert store.get("incident", incident["id"])["status"] == "failed"
    with pytest.raises(ValueError, match="invalid"):
        restarted.authorize(run_token)
    assert all(
        isinstance(event["payload"]["tick"], int) for event in store.trajectory(incident["id"])
    )
    store.close()


async def test_runner_health_cache_preserves_concurrent_edits(runtime, monkeypatch):
    import httpx

    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    reachable = True
    configured = {"reference": True, "llm": False}

    async def health(request):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        if not reachable:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, json={"status": "ok", "configured": configured})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "apps.control_api.registry.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(health), **kwargs),
    )
    assert (
        runtime.registry.public(runtime.registry.get("builtin-reference"))["connection_status"]
        == "unavailable"
    )
    first = asyncio.create_task(runtime.registry.refresh_health())
    await entered.wait()
    second = asyncio.create_task(runtime.registry.refresh_health())
    runtime.registry.update(
        "builtin-reference", AgentUpdate(name="Renamed during request", enabled=False)
    )
    release.set()
    await asyncio.gather(first, second)
    assert calls == 1
    stored = runtime.registry.get("builtin-reference")
    assert stored["name"] == "Renamed during request" and stored["enabled"] is False
    assert runtime.registry.public(stored)["connection_status"] == "disabled"
    llm = await runtime.registry.test("builtin-llm")
    assert llm["ok"] is False and "LLM_API_KEY" in llm["detail"]
    assert calls == 2  # Explicit connection tests bypass the cache.
    configured["llm"] = True
    runtime.registry.health_checked -= 6
    await runtime.registry.refresh_health()
    assert calls == 3
    assert (
        runtime.registry.public(runtime.registry.get("builtin-llm"))["connection_status"] == "ready"
    )
    reachable = False
    unavailable = await runtime.registry.test("builtin-llm")
    assert unavailable["ok"] is False
    assert unavailable["agent"]["connection_status"] == "unavailable"
