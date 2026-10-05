"""Persisted agent identities; credentials are hashed and connection state is bounded."""

import asyncio
import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import httpx

from apps.control_api.store import Store
from packages.contracts import AgentCreate, AgentUpdate

HEARTBEAT_TTL = 15
PUBLIC_FIELDS = ("id", "name", "kind", "description", "enabled", "last_seen", "created_at")


class Registry:
    def __init__(self, store: Store, busy: Callable[[str], bool], runner_url: str):
        self.store, self.busy, self.runner_url = store, busy, runner_url
        self.health_checked = 0.0
        self.health_lock = asyncio.Lock()
        self.health_details: dict[str, str] = {}
        builtins: list[tuple[Literal["reference", "llm"], str]] = [
            ("reference", "Reference Agent"),
            ("llm", "LLM Agent"),
        ]
        for kind, name in builtins:
            agent_id = f"builtin-{kind}"
            if not store.get("agent", agent_id):
                self.create(AgentCreate(name=name, kind=kind), agent_id)
        # A fresh control process requires external agents to contact it again.
        for agent in store.list("agent"):
            agent["last_seen"] = None
            agent["available"] = False
            store.put("agent", agent["id"], agent)

    def get(self, agent_id: str) -> dict:
        item = self.store.get("agent", agent_id)
        if not item:
            raise ValueError("Agent not found")
        return item

    def online(self, item: dict) -> bool:
        return (
            bool(item["last_seen"])
            and (datetime.now(UTC) - datetime.fromisoformat(item["last_seen"])).total_seconds()
            < HEARTBEAT_TTL
        )

    def public(self, item: dict) -> dict:
        if not item["enabled"]:
            status = "disabled"
        elif self.busy(item["id"]):
            status = "busy"
        elif item["kind"] == "external":
            status = "online" if self.online(item) else "offline"
        else:
            status = "ready" if item.get("available", False) else "unavailable"
        return {**{key: item[key] for key in PUBLIC_FIELDS}, "connection_status": status}

    def list(self) -> list[dict]:
        return [self.public(item) for item in self.store.list("agent")]

    def create(self, body: AgentCreate, agent_id: str | None = None) -> dict:
        item = {
            **body.model_dump(),
            "id": agent_id or str(uuid4()),
            "enabled": True,
            "last_seen": None,
            "created_at": datetime.now(UTC).isoformat(),
            "available": False,
        }
        credentials = self.credentials(item) if body.kind == "external" else None
        self.store.put("agent", item["id"], item)
        result = {"agent": self.public(item)}
        if credentials:
            result["credentials"] = credentials
        return result

    def credentials(self, item: dict) -> dict:
        token = secrets.token_urlsafe(32)
        item["token_hash"] = hashlib.sha256(token.encode()).hexdigest()
        item["last_seen"] = None
        return {
            "agent_id": item["id"],
            "token": token,
            "mcp_path": "/mcp",
            "poll_path": f"/api/agent-gateway/{item['id']}/next",
        }

    def update(self, agent_id: str, body: AgentUpdate) -> dict:
        item = self.get(agent_id)
        if body.enabled is False and self.busy(agent_id):
            raise ValueError("An active Agent cannot be disabled")
        item.update(body.model_dump(exclude_none=True))
        self.store.put("agent", agent_id, item)
        return self.public(item)

    def rotate(self, agent_id: str) -> dict:
        item = self.get(agent_id)
        if item["kind"] != "external":
            raise ValueError("Only external agents have registration credentials")
        if self.busy(agent_id):
            raise ValueError("An active Agent cannot rotate credentials")
        credentials = self.credentials(item)
        self.store.put("agent", agent_id, item)
        return {"agent": self.public(item), "credentials": credentials}

    def authenticate(self, agent_id: str, token: str) -> dict:
        item = self.store.get("agent", agent_id)
        if (
            not item
            or item["kind"] != "external"
            or not item["enabled"]
            or not secrets.compare_digest(
                item.get("token_hash", ""), hashlib.sha256(token.encode()).hexdigest()
            )
        ):
            raise PermissionError("Invalid or disabled Agent credentials")
        return item

    def find_by_token(self, token: str) -> dict | None:
        """Resolve an enabled registration without exposing the stored credential hash."""
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        for item in self.store.list("agent"):
            if (
                item["kind"] == "external"
                and item["enabled"]
                and secrets.compare_digest(item.get("token_hash", ""), digest)
            ):
                return item
        return None

    def touch(self, agent_id: str) -> None:
        item = self.get(agent_id)
        item["last_seen"] = datetime.now(UTC).isoformat()
        self.store.put("agent", agent_id, item)

    async def refresh_health(self, force: bool = False) -> None:
        async with self.health_lock:
            now = asyncio.get_running_loop().time()
            if not force and now - self.health_checked < 5:
                return
            configured: dict = {}
            reachable = False
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    response = await client.get(f"{self.runner_url}/health")
                    response.raise_for_status()
                    health = response.json()
                reachable = health.get("status") == "ok"
                configured = health.get("configured", {})
                if not isinstance(configured, dict):
                    configured = {}
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
            self.health_checked = asyncio.get_running_loop().time()
            # Re-read after I/O so an operator's concurrent update is preserved.
            for item in self.store.list("agent"):
                kind = item["kind"]
                if kind == "external":
                    continue
                item["available"] = reachable and bool(configured.get(kind))
                if reachable:
                    item["last_seen"] = datetime.now(UTC).isoformat()
                self.health_details[kind] = (
                    "Runner is ready"
                    if item["available"]
                    else "LLM_API_KEY is not configured"
                    if reachable and kind == "llm"
                    else "Agent mode is unavailable"
                    if reachable
                    else "Agent runner is unreachable"
                )
                self.store.put("agent", item["id"], item)

    async def test(self, agent_id: str) -> dict:
        item = self.get(agent_id)
        if item["kind"] != "external":
            await self.refresh_health(force=True)
            item = self.get(agent_id)
        if not item["enabled"]:
            ok, detail = False, "Agent is disabled"
        elif item["kind"] == "external":
            ok = self.online(item)
            detail = "Authenticated connector is online" if ok else "No heartbeat in the last 15s"
        else:
            ok = item["available"]
            detail = self.health_details[item["kind"]]
        return {"ok": ok, "detail": detail, "agent": self.public(item)}
