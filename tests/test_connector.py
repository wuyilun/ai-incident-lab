import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from apps.agent import connector


def assignment(**overrides):
    return connector.Assignment(
        **{
            "incident_id": "incident-1",
            "run_id": "run-1",
            "token": "run-secret",
            "alert": {"metric": "redis_connections", "severity": "critical"},
            **overrides,
        }
    )


@pytest.mark.parametrize("status", [401, 403])
async def test_registration_rejection_is_immediate_and_redacted(status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, json={"detail": "registration-secret"})

    async with httpx.AsyncClient(
        base_url="http://lab", transport=httpx.MockTransport(respond)
    ) as http:
        gateway = connector.Gateway(http, "external-1")
        with pytest.raises(connector.ConnectorError, match="token rejected") as error:
            await gateway.request("GET", "/next")
    assert len(requests) == 1
    assert "registration-secret" not in str(error.value)


async def test_gateway_recovers_transient_disconnect_but_bounds_retries(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("private transport data", request=request)
        if len(requests) == 3:
            return httpx.Response(200, json={"assignment": None})
        return httpx.Response(503)

    monkeypatch.setattr(connector.asyncio, "sleep", AsyncMock())
    async with httpx.AsyncClient(
        base_url="http://lab", transport=httpx.MockTransport(respond)
    ) as http:
        gateway = connector.Gateway(http, "external-1")
        assert await gateway.request("GET", "/next") == {"assignment": None}
        assert len(requests) == 3
        with pytest.raises(connector.ConnectorError, match="after three attempts"):
            await gateway.request("POST", "/heartbeat")
    assert len(requests) == 6


async def test_repeated_inbox_delivery_never_reexecutes_run(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer registration-secret"
        if len(requests) <= 3:
            return httpx.Response(200, json={"assignment": assignment().model_dump()})
        return httpx.Response(401)

    http = httpx.AsyncClient(
        base_url="http://lab",
        transport=httpx.MockTransport(respond),
        headers={"Authorization": "Bearer registration-secret"},
    )
    monkeypatch.setattr(connector.httpx, "AsyncClient", lambda **kwargs: http)
    execute = AsyncMock(return_value=True)
    monkeypatch.setattr(connector, "run_assignment", execute)
    with pytest.raises(connector.ConnectorError, match="token rejected"):
        await connector.run_connector(
            "http://lab", "external-1", "registration-secret", "reference", poll_seconds=0
        )
    assert len(requests) == 4
    execute.assert_awaited_once()


def mock_mcp(monkeypatch, *, resolved=False):
    client = SimpleNamespace(report=AsyncMock(), call=AsyncMock(), resolved=resolved)
    connections = []

    @asynccontextmanager
    async def connect(url, token):
        connections.append((url, token))
        yield client

    monkeypatch.setattr(connector, "connect", connect)
    return client, connections


async def test_execution_receives_alert_and_uses_only_run_token_for_mcp(monkeypatch):
    client, connections = mock_mcp(monkeypatch, resolved=True)
    handler = AsyncMock()
    monkeypatch.setattr(connector, "run_reference", handler)
    monkeypatch.setenv("AGENT_POLL_SECONDS", "0.05")
    assert await connector.execute(assignment(), "http://lab", "reference")
    assert connections == [("http://lab/mcp", "run-secret")]
    assert client.report.await_args.kwargs["alert"] == assignment().alert
    handler.assert_awaited_once_with(client, 0.05)


async def test_failure_reports_via_mcp_without_provider_secrets(monkeypatch, caplog):
    client, connections = mock_mcp(monkeypatch)
    monkeypatch.setattr(
        connector,
        "run_llm",
        AsyncMock(side_effect=RuntimeError("run-secret registration-secret provider-secret")),
    )
    assert not await connector.execute(assignment(), "http://lab", "llm")
    client.call.assert_awaited_once_with(
        "fail_incident", reason="Connector task failed: RuntimeError"
    )
    assert len(connections) == 2
    assert "secret" not in caplog.text


async def test_timeout_records_failure_via_mcp(monkeypatch):
    client, _ = mock_mcp(monkeypatch)

    async def stalled_handler(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(connector, "run_reference", stalled_handler)
    assert not await connector.execute(assignment(timeout_seconds=5.01), "http://lab", "reference")
    client.call.assert_awaited_once_with(
        "fail_incident", reason="Connector task failed: TimeoutError"
    )


async def test_revoked_assignment_cancels_inflight_handler(monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def execute(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def watch(run_id):
        await started.wait()
        raise connector.AssignmentEnded("Assignment cancelled")

    gateway = SimpleNamespace(acknowledge=AsyncMock(), watch=watch)
    monkeypatch.setattr(connector, "execute", execute)
    with pytest.raises(connector.AssignmentEnded, match="cancelled"):
        await asyncio.wait_for(
            connector.run_assignment(gateway, assignment(), "http://lab", "reference"), timeout=2
        )
    gateway.acknowledge.assert_awaited_once_with("run-1")
    assert cancelled.is_set()


async def test_resolved_assignment_can_finish_mcp_cleanup_after_ack_rejection(monkeypatch):
    resolved, cleaned = asyncio.Event(), asyncio.Event()

    async def execute(*args):
        resolved.set()  # Server revoked the run token after accepting resolve_incident.
        await asyncio.sleep(0.02)  # Response delivery and MCP context cleanup are still pending.
        cleaned.set()
        return True

    async def watch(run_id):
        await resolved.wait()
        raise connector.AssignmentEnded("No active assignment for this Agent and run")

    gateway = SimpleNamespace(acknowledge=AsyncMock(), watch=watch)
    monkeypatch.setattr(connector, "execute", execute)
    assert await connector.run_assignment(gateway, assignment(), "http://lab", "reference")
    assert cleaned.is_set()


async def test_watch_heartbeats_and_checks_assignment_liveness():
    paths = []

    def respond(request):
        paths.append(request.url.path)
        if len(paths) == 4:
            return httpx.Response(409)
        return httpx.Response(200, json={"accepted": True, "status": "online"})

    async with httpx.AsyncClient(
        base_url="http://lab", transport=httpx.MockTransport(respond)
    ) as http:
        with pytest.raises(connector.AssignmentEnded):
            await connector.Gateway(http, "external-1").watch("run-1", interval=0.001)
    assert (
        paths
        == [
            "/api/agent-gateway/external-1/heartbeat",
            "/api/agent-gateway/external-1/assignments/run-1/ack",
        ]
        * 2
    )


def test_assignment_cannot_redirect_run_credential_or_include_scenario_truth():
    with pytest.raises(ValidationError):
        assignment(mcp_path="https://another-host/mcp")
    with pytest.raises(ValidationError):
        assignment(scenario_id="hidden")
    assert "run-secret" not in repr(assignment())


def test_cli_requires_environment_token(monkeypatch, caplog):
    monkeypatch.setattr("sys.argv", ["connector", "--agent-id", "external-1", "--once"])
    monkeypatch.delenv("INCIDENTLAB_AGENT_TOKEN", raising=False)
    assert connector.main() == 1
    assert "INCIDENTLAB_AGENT_TOKEN environment variable is required" in caplog.text
