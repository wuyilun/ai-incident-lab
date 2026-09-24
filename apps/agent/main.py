import asyncio
import contextlib
import logging
import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.agent.client import connect
from apps.agent.llm import run_llm
from apps.agent.reference import run_reference

logger = logging.getLogger(__name__)
app = FastAPI(title="Incident Lab Agent Runner")
tasks: dict[str, asyncio.Task] = {}


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str
    run_id: str
    token: str = Field(repr=False)
    mode: Literal["reference", "llm"]


@app.get("/health")
async def health():
    return {"status": "ok", "modes": ["reference", "llm"]}


async def execute(body: RunRequest):
    async with asyncio.timeout(115):
        async with connect(os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp"), body.token) as client:
            try:
                if body.mode == "reference":
                    await run_reference(client, float(os.getenv("AGENT_POLL_SECONDS", "1")))
                else:
                    await run_llm(client)
                return {"status": "resolved" if client.resolved else "failed"}
            except Exception as exc:
                logger.warning("agent_run_failed: %s", type(exc).__name__)
                # Error text is an observable diagnostic, never include credentials or request headers.
                reason = str(exc)[:500] if isinstance(exc, RuntimeError) else type(exc).__name__
                with contextlib.suppress(Exception):
                    await client.call("fail_incident", reason=reason)
                return {"status": "failed", "error": reason}


@app.post("/run")
async def run(body: RunRequest):
    if tasks:
        raise HTTPException(409, "Agent is busy")
    task = asyncio.create_task(execute(body))
    tasks[body.run_id] = task
    try:
        return await task
    except TimeoutError as exc:
        raise HTTPException(504, "Agent timeout") from exc
    finally:
        tasks.pop(body.run_id, None)


@app.delete("/runs/{run_id}")
async def cancel(run_id: str):
    task = tasks.get(run_id)
    if task:
        task.cancel()
    return {"cancelled": task is not None}
