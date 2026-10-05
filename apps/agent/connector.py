"""Authenticated inbox connector; all environment access stays in the MCP client."""

import argparse
import asyncio
import contextlib
import logging
import os
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.agent.client import connect
from apps.agent.llm import run_llm
from apps.agent.reference import run_reference

logger = logging.getLogger(__name__)


class ConnectorError(RuntimeError):
    """Safe, credential-free message suitable for the connector console."""


class AssignmentEnded(ConnectorError):
    pass


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    token: str = Field(min_length=1, repr=False)
    mcp_path: Literal["/mcp"] = "/mcp"
    alert: dict[str, Any]
    timeout_seconds: float = Field(default=120, gt=5)


class Gateway:
    def __init__(self, http: httpx.AsyncClient, agent_id: str):
        self.http = http
        self.path = f"/api/agent-gateway/{quote(agent_id, safe='')}"

    async def request(self, method: str, path: str) -> dict[str, Any]:
        # Inbox fetch, heartbeat and ack are idempotent. MCP actions are never retried here.
        for attempt in range(3):
            try:
                response = await self.http.request(method, self.path + path)
            except httpx.TransportError:
                response = None
            if response is None or response.status_code >= 500:
                if attempt == 2:
                    raise ConnectorError("Control API unavailable after three attempts")
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code in {401, 403}:
                raise ConnectorError("Agent registration token rejected or agent disabled")
            if response.status_code in {409, 410}:
                raise AssignmentEnded("Assignment ended, cancelled, or run credential revoked")
            if not response.is_success:
                raise ConnectorError(f"Control API rejected request (HTTP {response.status_code})")
            try:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError
                return data
            except ValueError:
                raise ConnectorError("Control API returned an invalid response") from None
        raise AssertionError("Unreachable retry state")

    async def acknowledge(self, run_id: str) -> None:
        result = await self.request("POST", f"/assignments/{quote(run_id, safe='')}/ack")
        if result.get("accepted") is not True:
            raise AssignmentEnded("Assignment was not accepted")

    async def watch(self, run_id: str, interval: float = 5) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.request("POST", "/heartbeat")
            # Repeating ack checks cancellation without granting additional environment access.
            await self.acknowledge(run_id)


async def execute(assignment: Assignment, origin: str, mode: str) -> bool:
    url = origin + assignment.mcp_path
    try:
        async with asyncio.timeout(min(115, assignment.timeout_seconds - 5)):
            async with connect(url, assignment.token) as client:
                await client.report(
                    "investigating",
                    "observation",
                    transport="registered-agent",
                    alert=assignment.alert,
                )
                if mode == "reference":
                    await run_reference(client, float(os.getenv("AGENT_POLL_SECONDS", "1")))
                else:
                    await run_llm(client)
                return client.resolved
    except Exception as exc:
        # Provider/transport error strings may contain credentials; publish only the exception type.
        reason = f"Connector task failed: {type(exc).__name__}"
        logger.error("%s", reason)
        with contextlib.suppress(Exception):
            async with asyncio.timeout(3):
                async with connect(url, assignment.token) as client:
                    await client.call("fail_incident", reason=reason)
        return False


async def run_assignment(gateway: Gateway, assignment: Assignment, origin: str, mode: str) -> bool:
    await gateway.acknowledge(assignment.run_id)
    logger.info(
        "Received alert for incident %s (run %s)", assignment.incident_id, assignment.run_id
    )
    worker = asyncio.create_task(execute(assignment, origin, mode))
    heartbeat = asyncio.create_task(gateway.watch(assignment.run_id))
    try:
        await asyncio.wait({worker, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
        # Resolution revokes the run token: prefer an already completed handler over its last ack.
        if worker.done():
            return worker.result()
        try:
            await heartbeat
        except AssignmentEnded:
            # The server can resolve before the MCP response/context finishes closing.
            # Allow bounded cleanup; genuine cancellation still stops a stalled handler.
            done, _ = await asyncio.wait({worker}, timeout=1)
            if worker in done:
                return worker.result()
            raise
        return False
    finally:
        for task in (worker, heartbeat):
            task.cancel()
        await asyncio.gather(worker, heartbeat, return_exceptions=True)


async def run_connector(
    origin: str,
    agent_id: str,
    token: str,
    mode: str,
    *,
    once: bool = False,
    poll_seconds: float = 1,
) -> int:
    seen: set[str] = set()
    async with httpx.AsyncClient(
        base_url=origin, headers={"Authorization": f"Bearer {token}"}, timeout=3
    ) as http:
        gateway = Gateway(http, agent_id)
        logger.info("Connecting registered agent %s (%s)", agent_id, mode)
        while True:
            envelope = await gateway.request("GET", "/next")
            if "assignment" not in envelope:
                raise ConnectorError("Control API response is missing assignment")
            if envelope["assignment"] is not None:
                try:
                    assignment = Assignment.model_validate(envelope["assignment"])
                except ValidationError:
                    # Pydantic's error text contains input values, including the run credential.
                    raise ConnectorError("Control API returned an invalid assignment") from None
                if assignment.run_id not in seen:
                    seen.add(assignment.run_id)
                    try:
                        succeeded = await run_assignment(gateway, assignment, origin, mode)
                    except AssignmentEnded as exc:
                        logger.warning("%s", exc)
                        succeeded = False
                    logger.info(
                        "Assignment %s: %s", assignment.run_id, "resolved" if succeeded else "ended"
                    )
                    if once:
                        return 0 if succeeded else 1
            await asyncio.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000", help="Control API origin")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--mode", choices=("reference", "llm"), default="reference")
    parser.add_argument("--once", action="store_true", help="Exit after handling one assignment")
    parser.add_argument("--poll-seconds", type=float, default=1)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        origin = args.url.rstrip("/")
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ConnectorError("--url must be an HTTP(S) origin without credentials or path")
        if args.poll_seconds <= 0:
            raise ConnectorError("--poll-seconds must be positive")
        token = os.getenv("INCIDENTLAB_AGENT_TOKEN", "").strip()
        if not token:
            raise ConnectorError("INCIDENTLAB_AGENT_TOKEN environment variable is required")
        if args.mode == "llm" and not os.getenv("LLM_API_KEY"):
            raise ConnectorError("LLM_API_KEY is required for LLM mode")
        return asyncio.run(
            run_connector(
                origin,
                args.agent_id,
                token,
                args.mode,
                once=args.once,
                poll_seconds=args.poll_seconds,
            )
        )
    except ConnectorError as exc:
        logger.error("%s", exc)
        return 1
    except (ValueError, httpx.InvalidURL):
        logger.error("Invalid connector configuration")
        return 1
    except KeyboardInterrupt:
        logger.info("Connector stopped")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
