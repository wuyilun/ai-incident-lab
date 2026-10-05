"""Topology health represents observations; operator fault markers never enter MCP."""

from apps.control_api.runtime import Runtime
from apps.control_api.store import Store
from packages.contracts import InjectRequest
from simulator.world import World, load_scenarios


def nodes(world):
    return {s["name"]: s for s in world.observation()["services"]}


def test_healthy_dependency_does_not_inherit_its_callers_fault():
    world = World()
    world.inject(load_scenarios()["api-cpu-saturation"])
    for _ in range(5):
        world.advance()
    state = nodes(world)
    assert state["api"]["health"] == state["gateway"]["health"] == "degraded"
    assert state["redis"]["health"] == state["database"]["health"] == "healthy"
    edges = world.observation()["dependencies"]
    assert next(e for e in edges if e["from"] == "gateway")["affected"]
    assert not any(e["affected"] for e in edges if e["from"] == "api")


def test_connection_pool_cascades_but_database_and_async_branch_stay_healthy():
    world = World()
    world.inject(load_scenarios()["db-connection-pool-exhaustion"])
    for _ in range(6):
        world.advance()
    state = nodes(world)
    for service in ("db_proxy", "api", "payment", "inventory", "gateway", "worker"):
        assert state[service]["health"] == "degraded"
    for service in ("database", "redis", "queue", "notification"):
        assert state[service]["health"] == "healthy"
    edge = next(e for e in world.observation()["dependencies"] if e["from"] == "db_proxy")
    assert edge["to"] == "database" and not edge["affected"]
    world.restart("database")
    assert world.metrics()["db_pool_active"] == 100
    assert world.metrics()["api_error_rate"] >= 3
    world.restart("db_proxy")
    for _ in range(8):
        world.advance()
    assert all(s["health"] == "healthy" for s in nodes(world).values())
    assert not any(e["affected"] for e in world.observation()["dependencies"])


def test_unrelated_consumer_outage_does_not_fail_api():
    world = World()
    world.status["notification"] = "stopped"
    assert world.metrics()["api_error_rate"] == 0.2
    assert nodes(world)["api"]["health"] == "healthy"
    assert nodes(world)["notification"]["health"] == "unavailable"


def test_observed_health_does_not_depend_on_private_target():
    world = World()
    world.connections = 650
    before = world.observation()
    world.fault_target = "database"
    assert world.observation() == before
    assert nodes(world)["redis"]["health"] == "degraded"
    assert nodes(world)["database"]["health"] == "healthy"


def test_fault_target_only_in_operator_event(tmp_path):
    runtime = Runtime(Store(str(tmp_path / "lab.sqlite")))
    runtime.inject(InjectRequest(scenario_id="db-connection-pool-exhaustion", auto_agent=False))
    events = runtime.store.trajectory(runtime.incident["id"])
    assert events[0]["event_type"] == "fault.injected"
    assert events[0]["payload"]["target"] == "db_proxy"
    observed = runtime.world.observation()
    assert "target" not in observed and "fault_type" not in observed
    assert "scenario_id" not in runtime.public_incident()
    runtime.store.close()
