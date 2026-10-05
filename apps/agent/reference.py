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
    if not alerts:
        raise RuntimeError("An active alert is required before diagnosis")
    states = {service["name"]: service["status"] for service in services}
    redis_clients = {edge["from"] for edge in dependencies if edge["to"] == "redis"}
    database_clients = {edge["from"] for edge in dependencies if edge["to"] == "database"}
    history = metrics["history"]
    findings = []
    pressure_signals = (
        (
            "cpu_saturation",
            "CPU saturation; busy loop detected",
            "api_cpu_percent",
            90,
            "busy-loop",
        ),
        (
            "slow_queries",
            "Query execution stalled; slow query backlog",
            "database_latency_ms",
            600,
            "slow-query-backlog",
        ),
        (
            "queue_backlog",
            "Consumer stalled; messages not acknowledged",
            "queue_depth",
            500,
            "stalled-consumer",
        ),
    )
    for service, state in sorted(states.items()):
        logs = await client.call("get_logs", service=service)
        config = await client.call("get_config", service=service)
        messages = [line["message"] for line in logs]
        exited = [
            message for message in messages if "Service process exited unexpectedly" in message
        ]
        if state == "stopped" and exited:
            findings.append(
                (
                    "service_down",
                    service,
                    [f"{service} status is stopped", exited[-1]],
                    "exited-process",
                )
            )
        if state != "running":
            continue
        pool_timeouts = [
            message
            for message in messages
            if "Connection acquisition timed out; pool wait queue growing" in message
        ]
        observed = metrics["metrics"]
        pool_limit = config.get("pool_limit", 0)
        if (
            service in database_clients
            and states.get("database") == "running"
            and isinstance(pool_limit, (int, float))
            and pool_limit > 0
            and observed.get("db_pool_active", 0) >= pool_limit * 0.9
            and observed.get("db_pool_wait_ms", 0) > 100
            and observed.get("database_latency_ms", float("inf")) < 200
            and observed.get("api_cpu_percent", float("inf")) < 80
            and len(pool_timeouts) >= 2
        ):
            findings.append(
                (
                    "connection_pool_exhaustion",
                    service,
                    [
                        f"{service} pool has {observed['db_pool_active']}/{pool_limit} active connections; acquisition wait={observed['db_pool_wait_ms']} ms",
                        f"{service}: {len(pool_timeouts)} repeated acquisition timeouts; {pool_timeouts[-1]}",
                        f"Its database dependency is running with query latency={observed['database_latency_ms']} ms; API CPU={observed['api_cpu_percent']}% is normal",
                        "Upstream request timeouts are consistent with waiting for the saturated pool, not stalled database queries",
                    ],
                    "pool-acquisition-timeout",
                )
            )
        for cause, message, metric, threshold, query in pressure_signals:
            matching = [line for line in messages if message in line]
            value = metrics["metrics"].get(metric, 0)
            if matching and value > threshold:
                findings.append(
                    (
                        cause,
                        service,
                        [
                            f"{metric}={value} exceeds {threshold}",
                            f"{service}: {matching[-1]}",
                            f"{service} configuration: {config}",
                        ],
                        query,
                    )
                )
        leaking = [line for line in logs if "acquired without release" in line["message"]]
        if (
            service in redis_clients
            and states.get("redis") == "running"
            and len(leaking) >= 2
            and "pool_limit" in config
            and len(history) >= 2
            and history[-1]["redis_connections"] > history[0]["redis_connections"]
        ):
            findings.append(
                (
                    "connection_leak",
                    service,
                    [
                        f"Redis connections grew {history[0]['redis_connections']} → {history[-1]['redis_connections']}",
                        f"{service}: {leaking[-1]['message']}",
                        f"{service} pool limit is {config['pool_limit']}; dependency is running",
                    ],
                    "connections pool",
                )
            )
    if len(findings) != 1:
        raise RuntimeError("Insufficient or conflicting evidence: no unique failure and owner")
    root_cause, owner, evidence, query = findings[0]
    await client.report(
        "diagnosing",
        "hypothesis",
        root_cause=root_cause,
        service=owner,
        evidence=evidence,
        confidence=0.94,
    )
    procedures = await client.call("get_sop", query=query)
    target = {
        "connection_leak": "identified_client_owner",
        "connection_pool_exhaustion": "identified_pool_owner",
    }.get(root_cause, "identified_service")
    procedure = next((s for s in procedures if s["remediation"]["target"] == target), None)
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
            healthy = all(
                m[name.removesuffix("_lt")] < limit
                for name, limit in limits.items()
                if name.endswith("_lt")
            ) and all(s["status"] == "running" for s in current["services"])
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
                    summary=f"{owner} recovered via {procedure['id']}; sustained recovery verified",
                )
                return
        await asyncio.sleep(poll_seconds)
    raise RuntimeError("Recovery verification timed out")
