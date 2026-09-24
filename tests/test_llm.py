"""Offline provider-adapter contract tests, not model-quality evaluation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from apps.agent import llm


async def test_llm_uses_discovered_tools_and_skill(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_POLL_SECONDS", "0")
    replies = [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "private provider field",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "get_metrics", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "2",
                    "type": "function",
                    "function": {
                        "name": "fail_incident",
                        "arguments": '{"reason":"insufficient evidence"}',
                    },
                }
            ],
        },
    ]
    requests = []

    def provider(request):
        import json

        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": replies.pop(0)}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: http)
    session = SimpleNamespace(
        list_tools=AsyncMock(
            return_value=SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="get_metrics",
                        description="Fresh metrics",
                        inputSchema={"type": "object"},
                    )
                ]
            )
        )
    )
    client = SimpleNamespace(
        session=session,
        report=AsyncMock(),
        call=AsyncMock(return_value={"status": "failed"}),
        resolved=False,
    )
    await llm.run_llm(client)
    assert [call.args[0] for call in client.call.call_args_list] == ["get_metrics", "fail_incident"]
    assert requests[0]["tools"][0]["function"]["name"] == "get_metrics"
    assert "Evidence-led dependency diagnosis" in requests[0]["messages"][0]["content"]
    assert "redis-connection-leak" not in requests[0]["messages"][0]["content"]
    assert all("reasoning_content" not in m for m in requests[1]["messages"])


async def test_llm_cannot_claim_success_without_resolution(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-placeholder")
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"role": "assistant", "content": "All fixed!"}}]}
            )
        )
    )
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: http)
    client = SimpleNamespace(
        session=SimpleNamespace(list_tools=AsyncMock(return_value=SimpleNamespace(tools=[]))),
        report=AsyncMock(),
        resolved=False,
    )
    with pytest.raises(RuntimeError, match="before verified resolution"):
        await llm.run_llm(client)
