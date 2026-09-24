"""The sole environment access layer used by both agent implementations."""

import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class ToolClient:
    def __init__(self, session: ClientSession):
        self.session = session
        self.calls = 0
        self.actions = 0
        self.resolved = False

    async def call(self, name: str, **arguments: Any) -> Any:
        self.calls += 1
        if self.calls > 75:
            raise RuntimeError("Agent tool budget exhausted")
        if name in {"restart_service", "stop_service", "clear_cache"}:
            self.actions += 1
            if self.actions > 2:
                raise RuntimeError("Agent action budget exhausted")
        result = await self.session.call_tool(name, arguments)
        if result.isError:
            raise RuntimeError("; ".join(c.text for c in result.content if c.type == "text"))
        if result.structuredContent is not None:
            data = result.structuredContent
            value = data.get("result", data)
        else:
            texts = [c.text for c in result.content if c.type == "text"]
            value = json.loads(texts[0]) if len(texts) == 1 else [json.loads(t) for t in texts]
        if name == "resolve_incident":
            self.resolved = value.get("status") == "resolved"
        return value

    async def report(self, phase: str, artifact: str, **data: Any):
        return await self.call("report_progress", phase=phase, artifact=artifact, data=data)


@asynccontextmanager
async def connect(url: str, token: str):
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield ToolClient(session)
