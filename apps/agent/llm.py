"""OpenAI-compatible Chat Completions adapter; environment tools discovered via MCP."""

import asyncio
import json
import os

import httpx

from apps.agent.client import ToolClient
from apps.agent.reference import load_skill


async def run_llm(client: ToolClient) -> None:
    key = os.getenv("LLM_API_KEY")
    if not key:
        raise RuntimeError("LLM_API_KEY is required for LLM mode")
    discovered = await client.session.list_tools()
    tools = [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema},
        }
        for t in discovered.tools
    ]
    messages = [
        {
            "role": "system",
            "content": "You are a bounded incident response agent. Use only the provided MCP tools for all environment access. Follow the diagnostic skill below. Use report_progress to publish concise evidence and decisions, never private chain-of-thought. Start with get_incident/get_alerts. Hypothesis root_cause should name the failure behavior (e.g. connection_leak), and service its owner. Retrieve an SOP before acting. Never claim success without fresh verification, then call resolve_incident. Stop on safety denial. If blocked call fail_incident.\n\n"
            + load_skill(),
        }
    ]
    await client.report(
        "investigating", "observation", skill="diagnose.md", method=load_skill(), adapter="llm"
    )
    async with httpx.AsyncClient(timeout=30) as http:
        for _ in range(24):
            response = await http.post(
                os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
                + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": os.getenv("LLM_MODEL", "gpt-4.1-mini"),
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                },
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            # Keep provider-specific private reasoning fields out of persisted artifacts/context.
            messages.append(
                {k: message[k] for k in ("role", "content", "tool_calls") if k in message}
            )
            calls = message.get("tool_calls", [])
            if not calls:
                if client.resolved:
                    return
                raise RuntimeError("Model stopped before verified resolution")
            for call in calls:
                name = call["function"]["name"]
                result = await client.call(name, **json.loads(call["function"]["arguments"]))
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)}
                )
                if client.resolved or name == "fail_incident":
                    return
            await asyncio.sleep(float(os.getenv("AGENT_POLL_SECONDS", "1")))
    raise RuntimeError("LLM iteration budget exhausted")
