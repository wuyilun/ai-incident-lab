"""Deterministic evidence-driven baseline, deliberately not marketed as an LLM."""

import asyncio
from pathlib import Path

from apps.agent.client import ToolClient

SKILL_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "skills" / "diagnose.md"


def load_skill() -> str:
    return SKILL_PATH.read_text()


async def run_reference(client: ToolClient, poll_seconds: float = 1.0) -> None:
    skill = load_skill()
    incident = await client.call("get_incident")
    alerts = await client.call("get_alerts")
    await client.report(
        "investigating",
        "observation",
        skill="diagnose.md",
        method=skill,
        alert=alerts,
        incident_id=incident["id"],
    )
    metrics = await client.call("get_metrics")
    dependencies = await client.call("get_dependencies")
    services = await client.call("get_service_status")
    if not alerts or any(s["status"] != "running" for s in services):
        raise RuntimeError(
            "Evidence does not support a running-service resource-pressure diagnosis"
        )
    candidates = sorted({e["from"] for e in dependencies if e["to"] == "redis"})
    owners = []
    for service in candidates:
        logs = await client.call("get_logs", service=service)
        config = await client.call("get_config", service=service)
        leaking = [line for line in logs if "acquired without release" in line["message"]]
        if len(leaking) >= 2 and "pool_limit" in config:
            owners.append((service, leaking, config))
    history = metrics["history"]
    if (
        len(owners) != 1
        or len(history) < 2
        or history[-1]["redis_connections"] <= history[0]["redis_connections"]
    ):
        raise RuntimeError("Insufficient evidence: no unique growing connection owner")
    owner, logs, config = owners[0]
    evidence = [
        f"Redis connections grew {history[0]['redis_connections']} → {history[-1]['redis_connections']}",
        f"{owner}: {logs[-1]['message']}",
        f"{owner} pool limit is {config['pool_limit']}; dependency is running",
    ]
    await client.report(
        "diagnosing",
        "hypothesis",
        root_cause="connection_leak",
        service=owner,
        evidence=evidence,
        confidence=0.94,
    )
    procedures = await client.call("get_sop", query="connections pool")
    procedure = next(
        (s for s in procedures if s["remediation"]["target"] == "identified_client_owner"), None
    )
    if not procedure:
        raise RuntimeError("No applicable SOP")
    remediation = procedure["remediation"]
    await client.report(
        "planning",
        "plan",
        sop=procedure["id"],
        action=remediation["tool"],
        target=owner,
        rationale=remediation["reason"],
    )
    await client.report("acting", "observation", decision="Execute scoped reversible remediation")
    result = await client.call(remediation["tool"], service=owner, reason=remediation["reason"])
    if not result["ok"]:
        raise RuntimeError(f"Safety policy: {result['decision']}")
    await client.report("verifying", "observation", decision="Wait for independent healthy samples")
    limits = procedure["verification"]
    last_tick = -1
    consecutive = 0
    for _ in range(35):
        current = await client.call("get_metrics")
        if current["tick"] != last_tick:
            last_tick = current["tick"]
            m = current["metrics"]
            healthy = (
                m["redis_connections"] < limits["redis_connections_lt"]
                and m["api_error_rate"] < limits["api_error_rate_lt"]
                and m["api_latency_ms"] < limits["api_latency_ms_lt"]
                and all(s["status"] == "running" for s in current["services"])
            )
            consecutive = consecutive + 1 if healthy else 0
            if (
                consecutive >= limits["healthy_ticks"]
                and current["healthy_ticks"] >= limits["healthy_ticks"]
            ):
                await client.report(
                    "verifying",
                    "verification",
                    healthy_ticks=consecutive,
                    metrics=m,
                    evidence="Fresh samples across distinct ticks; all services running",
                )
                await client.call(
                    "resolve_incident",
                    summary=f"{owner} connection pool reset via {procedure['id']}; sustained recovery verified",
                )
                return
        await asyncio.sleep(poll_seconds)
    raise RuntimeError("Recovery verification timed out")
