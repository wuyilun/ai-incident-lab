"""Minimal direct MCP reference client: one URL and one registration token."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from apps.agent.client import ToolClient, connect
from apps.agent.llm import run_llm
from apps.agent.reference import run_reference


async def run(url: str, token: str, mode: str, once: bool, poll: float) -> int:
    async with connect(url, token) as connection:
        await connection.call("check_connection")
        print("MCP connected; waiting for an assigned alert", flush=True)
        while True:
            # Idle polling is outside the per-incident diagnostic budget.
            result = await connection.session.call_tool("receive_alert", {})
            if result.isError:
                raise RuntimeError("Alert reception rejected")
            data = result.structuredContent
            if data is None:
                data = json.loads(next(c.text for c in result.content if c.type == "text"))
            data = data.get("result", data)
            assignment = data.get("assignment")
            if not assignment:
                await asyncio.sleep(poll)
                continue
            client = ToolClient(connection.session)
            client.run_id = assignment["run_id"]
            try:
                async with asyncio.timeout(115):
                    await client.call("get_diagnostic_skill")
                    if mode == "reference":
                        await run_reference(client, poll_seconds=poll)
                    else:
                        await run_llm(client)
                ok = client.resolved
            except Exception as exc:
                print(f"Diagnosis failed: {type(exc).__name__}", file=sys.stderr)
                try:
                    await client.call(
                        "fail_incident", reason=f"Direct MCP Agent: {type(exc).__name__}"
                    )
                except Exception:
                    pass  # Cancellation/revocation may already have closed the run.
                ok = False
            print("Verified recovery" if ok else "Run did not resolve", flush=True)
            if once:
                return 0 if ok else 1


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:5173/mcp")
    parser.add_argument("--mode", choices=("reference", "llm"), default="reference")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1)
    args = parser.parse_args()
    token = os.getenv("INCIDENTLAB_AGENT_TOKEN", "")
    if not token or args.poll_seconds <= 0:
        parser.error("Set INCIDENTLAB_AGENT_TOKEN and use a positive poll interval")
    if args.mode == "llm" and not os.getenv("LLM_API_KEY"):
        parser.error("LLM_API_KEY is required for LLM mode")
    try:
        return asyncio.run(run(args.url, token, args.mode, args.once, args.poll_seconds))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"MCP connection failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
