import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.control_api.store import Store
from evaluator.grader import grade
from lab_mcp.safety import assess
from packages.contracts import Event, Scenario
from simulator.world import World, load_scenarios


@pytest.fixture
def scenario():
    return load_scenarios()["redis-connection-leak"]


def test_scenario_validation(scenario):
    payload = scenario.model_dump()
    payload["fault"]["intensity"] = 2
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
    payload = scenario.model_dump()
    payload["execute"] = "shell command"
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
    payload = scenario.model_dump()
    payload["forbidden_actions"] = payload["allowed_actions"]
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


@pytest.mark.parametrize("seed", [0, 42, 1234])
def test_causal_degradation_and_recovery(scenario, seed):
    world = World(seed)
    world.inject(scenario)
    metrics = [world.advance()["metrics"] for _ in range(10)]
    assert all(
        b["redis_connections"] > a["redis_connections"]
        for a, b in zip(metrics, metrics[1:], strict=False)
    )
    assert metrics[-1]["api_error_rate"] > 10
    assert metrics[-1]["api_latency_ms"] > 3000
    world.restart("worker")
    assert world.healthy_ticks == 0
    for _ in range(8):
        world.advance()
    assert world.healthy() and world.healthy_ticks >= 3
    assert world.restarts["worker"] == 1


def test_seed_reproducibility_and_wrong_remediation(scenario):
    a, b = World(13), World(13)
    a.inject(scenario)
    b.inject(scenario)
    assert [a.advance() for _ in range(8)] == [b.advance() for _ in range(8)]
    a.restart("redis")
    for _ in range(3):
        a.advance()
    assert not a.healthy()


def test_safety(scenario):
    assert assess("restart_service", "worker", scenario, 0, True).decision == "ALLOW"
    assert assess("clear_cache", "redis", scenario, 0, True).decision == "DENY"
    assert assess("restart_service", "api", scenario, 0, True).decision == "DENY"
    assert assess("restart_service", "worker", scenario, 2, True).decision == "DENY"
    assert assess("restart_service", "worker", scenario, 0, False).decision == "DENY"
    assert (
        assess("restart_service", "worker", scenario, 0, True, True).decision == "REQUIRE_APPROVAL"
    )


def test_store_persistence_and_cursor(tmp_path):
    path = str(tmp_path / "events.sqlite")
    store = Store(path)
    first = store.emit("agent.observation", "agent", {"evidence": "one"}, "inc-1", "run-1")
    second = store.emit("agent.action", "mcp", {"target": "worker"}, "inc-1", "run-1")
    store.emit("agent.observation", "agent", {}, "inc-2", "run-2")
    store.put("incident", "inc-1", {"status": "detected"})
    store.close()
    store = Store(path)
    assert Event.model_validate(first).version == 1
    assert store.events(after=first["sequence"], incident_id="inc-1") == [second]
    assert len(store.events(run_id="run-1")) == 2
    assert store.get("incident", "inc-1")["status"] == "detected"
    store.close()


def test_evaluator_does_not_trust_agent(scenario):
    world = World()
    world.inject(scenario)
    for _ in range(8):
        world.advance()
    events = [{"event_type": "agent.verification", "payload": {"healthy_ticks": 999}}]
    result = grade(scenario, world.observation(), events, True)
    assert not result["incident_resolved"]
    assert not result["environment_recovered"]
    assert not result["recovery_verified"]


def test_ground_truth_not_in_observations_or_knowledge(scenario):
    world = World()
    world.inject(scenario)
    for _ in range(7):
        world.advance()
    observation = json.dumps(
        {"world": world.observation(), "logs": list(world.logs), "config": world.config}
    )
    assert "ground_truth" not in observation
    assert scenario.id not in observation
    assert scenario.ground_truth.root_cause not in observation
    for path in Path("knowledge").rglob("*"):
        if path.is_file():
            assert "ground_truth" not in path.read_text()
            assert scenario.id not in path.read_text()


def test_agent_import_boundaries():
    forbidden = (
        "simulator",
        "evaluator",
        "apps.control_api",
        "lab_mcp",
        "sqlite3",
        "subprocess",
        "docker",
    )
    for path in Path("apps/agent").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            assert not any(name.startswith(forbidden) for name in imports), path


def test_structured_logs_escape_messages():
    import logging

    from packages.logging import JsonFormatter

    record = logging.LogRecord("lab", logging.INFO, "test", 1, 'quoted "message"\nnext', (), None)
    record.run_id = "run-1"
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["message"] == 'quoted "message"\nnext'
    assert parsed["run_id"] == "run-1"
