"""Official MCP transport; every call authenticated, scoped and audited."""

from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from apps.control_api.registry import HEARTBEAT_TTL
from apps.control_api.runtime import Runtime

RUN_SCOPED_TOOLS = {
    "restart_service",
    "stop_service",
    "clear_cache",
    "report_progress",
    "resolve_incident",
    "fail_incident",
}


def create_mcp(runtime: Runtime) -> FastMCP:
    server = FastMCP(
        "Incident Agent Lab",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["localhost:*", "127.0.0.1:*", "control:*", "testserver"],
            allowed_origins=["http://localhost:*", "http://127.0.0.1:*"],
        ),
    )

    def registered_agent(ctx: Context) -> dict | None:
        request = ctx.request_context.request
        if request is None:
            raise ValueError("Missing MCP request context")
        authorization = request.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        return runtime.registry.find_by_token(token)

    def audited(fn):
        @wraps(fn)
        async def wrapped(*args, **kwargs):
            ctx = kwargs.get("ctx")
            if ctx is None:
                raise ValueError("Missing MCP request context")
            request = ctx.request_context.request
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            agent = registered_agent(ctx)
            if agent:
                runtime.registry.touch(agent["id"])
                if not runtime.agent_busy(agent["id"]) or not runtime.received:
                    raise ValueError("No acknowledged active assignment; call receive_alert first")
                runtime.authorize(runtime.token or "")
            else:
                runtime.authorize(token)
            if fn.__name__ in RUN_SCOPED_TOOLS and (agent or kwargs.get("run_id") is not None):
                assert runtime.incident
                if kwargs.get("run_id") != runtime.incident["run_id"]:
                    runtime.emit(
                        "agent.tool_rejected",
                        "mcp",
                        {
                            "tool": fn.__name__,
                            "decision": "DENY",
                            "requested_run_id": kwargs.get("run_id"),
                            "reason": "run_id must match the assignment returned by receive_alert",
                        },
                    )
                    raise ValueError("run_id must match the assignment returned by receive_alert")
            if runtime.tool_count >= 80:
                raise ValueError("Tool call budget exhausted")
            runtime.tool_count += 1
            arguments = {k: v for k, v in kwargs.items() if k != "ctx"}
            runtime.emit("agent.tool_call", "mcp", {"tool": fn.__name__, "arguments": arguments})
            try:
                result = await fn(*args, **kwargs)
                runtime.emit("agent.tool_result", "mcp", {"tool": fn.__name__, "result": result})
                return result
            except Exception as exc:
                runtime.emit("agent.tool_result", "mcp", {"tool": fn.__name__, "error": str(exc)})
                raise

        return wrapped

    @server.tool()
    async def check_connection(ctx: Context) -> dict[str, Any]:
        """Check registration-token connectivity and refresh heartbeat. Safe while idle; call every 10s when waiting. Run tokens cannot use this tool."""
        agent = registered_agent(ctx)
        if not agent:
            raise ValueError("Invalid or disabled Agent registration credentials")
        runtime.registry.touch(agent["id"])
        return {
            "agent": runtime.registry.public(runtime.registry.get(agent["id"])),
            "mcp_path": "/mcp",
            "heartbeat_ttl_seconds": HEARTBEAT_TTL,
        }

    @server.tool()
    async def receive_alert(ctx: Context) -> dict[str, Any]:
        """Poll and acknowledge your assigned alert with the registration token. Returns assignment:null while idle; retry every 1s. Once assigned, use the SAME token for all diagnosis, SOP, remediation and reporting tools. Receiving again is idempotent. Never needs a REST inbox or a second token."""
        agent = registered_agent(ctx)
        if not agent:
            raise ValueError("Invalid or disabled Agent registration credentials")
        agent_id = agent["id"]
        runtime.registry.touch(agent_id)
        if not runtime.agent_busy(agent_id) or not runtime.token:
            return {"assignment": None}
        assert runtime.incident
        newly_received = not runtime.received
        if newly_received:
            runtime.emit("agent.tool_call", "mcp", {"tool": "receive_alert", "arguments": {}})
        runtime.acknowledge(agent_id, runtime.incident["run_id"], via="mcp.receive_alert")
        incident = runtime.public_incident()
        assignment = {
            "incident_id": incident["id"],
            "run_id": incident["run_id"],
            "alert": incident["alert"],
            "status": incident["status"],
            "timeout_seconds": 120,
        }
        if newly_received:
            runtime.emit(
                "agent.tool_result",
                "mcp",
                {
                    "tool": "receive_alert",
                    "result": {"assignment": assignment},
                },
            )
        return {"assignment": assignment}

    @server.tool()
    @audited
    async def get_incident(ctx: Context) -> dict[str, Any]:
        """Read the current alert/incident, without scenario metadata."""
        runtime.receive_alert("mcp.get_incident")
        return runtime.public_incident()

    @server.tool()
    @audited
    async def get_alerts(ctx: Context) -> list[dict[str, Any]]:
        """Read current alert including measured symptoms."""
        runtime.receive_alert("mcp.get_alerts")
        incident = runtime.public_incident()
        return [incident["alert"]] if incident["alert"] else []

    @server.tool()
    @audited
    async def get_metrics(ctx: Context) -> dict[str, Any]:
        """Read fresh metrics plus recent time-series samples."""
        assert runtime.incident
        samples = [
            e["payload"]
            for e in runtime.store.trajectory(runtime.incident["id"])
            if e["event_type"] == "environment.metric"
        ][-12:]
        return {
            **runtime.world.observation(),
            "history": [{"tick": s["tick"], **s["metrics"]} for s in samples],
        }

    @server.tool()
    @audited
    async def get_logs(service: str, ctx: Context) -> list[dict[str, Any]]:
        """Read bounded runtime logs for any service discovered by get_service_status."""
        if service not in runtime.world.status:
            raise ValueError("Unknown service")
        return [line for line in runtime.world.logs if line["service"] == service][-15:]

    @server.tool()
    @audited
    async def get_service_status(ctx: Context) -> list[dict[str, Any]]:
        """Read logical service states and restart counts."""
        return runtime.world.observation()["services"]

    @server.tool()
    @audited
    async def get_dependencies(ctx: Context) -> list[dict[str, Any]]:
        """Read directed service dependency edges."""
        return runtime.world.observation()["dependencies"]

    @server.tool()
    @audited
    async def get_config(service: str, ctx: Context) -> dict[str, Any]:
        """Read allowlisted non-secret service configuration."""
        if service not in runtime.world.config:
            raise ValueError("Unknown service")
        return runtime.world.config[service]

    @server.tool()
    @audited
    async def get_diagnostic_skill(ctx: Context) -> dict[str, Any]:
        """Read and apply this evidence-led diagnostic method before diagnosis. Gather observations using MCP, then retrieve get_sop after establishing evidence for a cause. The method contains no incident answer."""
        path = Path(__file__).resolve().parents[1] / "knowledge" / "skills" / "diagnose.md"
        return {"name": path.name, "content": path.read_text()}

    @server.tool()
    @audited
    async def get_sop(query: str, ctx: Context) -> list[dict[str, Any]]:
        """Retrieve operational procedures by symptoms; includes verification limits."""
        return runtime.sop(query)

    @server.tool()
    @audited
    async def restart_service(
        service: str, reason: str, ctx: Context, run_id: str | None = None
    ) -> dict[str, Any]:
        """Request a safety-gated simulated service restart with a reason. Registration-token callers must pass run_id from receive_alert."""
        return runtime.action("restart_service", service, reason)

    @server.tool()
    @audited
    async def clear_cache(
        service: str, reason: str, ctx: Context, run_id: str | None = None
    ) -> dict[str, Any]:
        """Request cache clear. Current policy denies destructive shared-cache actions. Registration-token callers must pass run_id from receive_alert."""
        return runtime.action("clear_cache", service, reason)

    @server.tool()
    @audited
    async def stop_service(
        service: str, reason: str, ctx: Context, run_id: str | None = None
    ) -> dict[str, Any]:
        """Request service stop. Denied unless explicitly allowed by policy. Registration-token callers must pass run_id from receive_alert."""
        return runtime.action("stop_service", service, reason)

    @server.tool()
    @audited
    async def report_progress(
        phase: str, artifact: str, data: dict[str, Any], ctx: Context, run_id: str | None = None
    ) -> dict[str, Any]:
        """Record a concise artifact. Phases: investigating, diagnosing, planning, acting, verifying. Artifacts: observation, hypothesis (root_cause, service, evidence), plan, verification (healthy_ticks), summary. Registration-token callers must pass run_id from receive_alert."""
        return runtime.progress(phase, artifact, data)

    @server.tool()
    @audited
    async def resolve_incident(
        summary: str, ctx: Context, run_id: str | None = None
    ) -> dict[str, Any]:
        """Resolve only after sustained recovery and a recorded verification; independently checked. Registration-token callers must pass run_id from receive_alert."""
        return runtime.resolve(summary)

    @server.tool()
    @audited
    async def fail_incident(reason: str, ctx: Context, run_id: str | None = None) -> dict[str, Any]:
        """Explicitly fail the bounded run when evidence or execution is insufficient. Registration-token callers must pass run_id from receive_alert."""
        runtime.finish("failed", reason)
        return {"status": "failed"}

    return server
