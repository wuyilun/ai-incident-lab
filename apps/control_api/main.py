import asyncio
import contextlib
import json
import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apps.control_api.leaderboard import leaderboard
from apps.control_api.runtime import Runtime
from apps.control_api.store import Store
from lab_mcp.server import create_mcp
from packages.contracts import (
    AgentCreate,
    AgentUpdate,
    BenchmarkRequest,
    InjectRequest,
    StartRequest,
)
from packages.logging import configure_logging

configure_logging()


def create_app(
    db_path: str | None = None, tick_seconds: float | None = None, agent_url: str | None = None
) -> FastAPI:
    store = Store(db_path or os.environ.get("LAB_DB") or "data/lab.sqlite")
    runtime = Runtime(
        store,
        tick_seconds if tick_seconds is not None else float(os.getenv("TICK_SECONDS", "1")),
        agent_url or os.environ.get("AGENT_URL") or "http://127.0.0.1:8001",
    )
    mcp = create_mcp(runtime)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            clock = asyncio.create_task(runtime.clock())
            yield
            for task in (clock, runtime.agent_task, runtime.benchmark_task):
                if task and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            store.close()

    app = FastAPI(title="Incident Agent Lab", version="0.3.0", lifespan=lifespan)
    app.state.runtime = runtime

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger(__name__).info(
            "request.completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
            },
        )
        return response

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "simulation": True}

    @app.get("/api/environment")
    async def environment():
        return runtime.world.observation()

    @app.get("/api/scenarios")
    async def scenarios():
        return [
            {
                "id": s.id,
                "name": s.name,
                "severity": s.severity,
                "target": s.target,
                "fault_type": s.fault.type,
                "description": s.description,
                "metric": s.metric,
            }
            for s in runtime.scenarios.values()
        ]

    @app.get("/api/leaderboard")
    async def rankings(scenario_id: str | None = None):
        return leaderboard(store, set(runtime.scenarios), scenario_id)

    @app.get("/api/agents")
    async def agents():
        await runtime.registry.refresh_health()
        return runtime.registry.list()

    @app.post("/api/agents", status_code=201)
    async def register_agent(body: AgentCreate):
        return runtime.registry.create(body)

    @app.patch("/api/agents/{agent_id}")
    async def update_agent(agent_id: str, body: AgentUpdate):
        return runtime.registry.update(agent_id, body)

    @app.post("/api/agents/{agent_id}/test")
    async def test_agent(agent_id: str):
        return await runtime.registry.test(agent_id)

    @app.post("/api/agents/{agent_id}/rotate-token")
    async def rotate_agent_token(agent_id: str):
        return runtime.registry.rotate(agent_id)

    def authenticate_agent(agent_id: str, request: Request) -> None:
        authorization = request.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        try:
            runtime.registry.authenticate(agent_id, token)
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from exc

    @app.get("/api/agent-gateway/{agent_id}/next")
    async def next_assignment(agent_id: str, request: Request):
        authenticate_agent(agent_id, request)
        return runtime.next_assignment(agent_id)

    @app.post("/api/agent-gateway/{agent_id}/heartbeat")
    async def heartbeat(agent_id: str, request: Request):
        authenticate_agent(agent_id, request)
        runtime.registry.touch(agent_id)
        return {"status": "online"}

    @app.post("/api/agent-gateway/{agent_id}/assignments/{run_id}/ack")
    async def acknowledge_assignment(agent_id: str, run_id: str, request: Request):
        authenticate_agent(agent_id, request)
        return runtime.acknowledge(agent_id, run_id)

    @app.post("/api/incidents", status_code=201)
    async def inject(body: InjectRequest):
        return runtime.inject(body)

    @app.get("/api/incidents")
    async def incidents():
        return store.list("incident")

    @app.get("/api/incidents/{incident_id}")
    async def incident(incident_id: str):
        item = store.get("incident", incident_id)
        if not item:
            raise HTTPException(404, "Incident not found")
        return item

    @app.post("/api/incidents/{incident_id}/agent")
    async def start(incident_id: str, body: StartRequest):
        return runtime.start_agent(incident_id, body.mode, body.agent_id)

    @app.delete("/api/incidents/{incident_id}/agent")
    async def cancel(incident_id: str):
        return await runtime.cancel(incident_id)

    @app.get("/api/incidents/{incident_id}/evaluation")
    async def evaluation(incident_id: str):
        item = store.get("evaluation", incident_id)
        if not item:
            raise HTTPException(404, "Evaluation not available")
        return item

    @app.get("/api/runs")
    async def runs():
        return store.list("run")

    @app.get("/api/events")
    async def events(
        after: int = Query(0, ge=0),
        incident_id: str | None = None,
        run_id: str | None = None,
        limit: int = Query(2000, ge=1, le=5000),
    ):
        return store.events(after, incident_id, run_id, limit)

    @app.get("/api/events/stream")
    async def stream(request: Request, after: int = Query(0, ge=0), incident_id: str | None = None):
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError as exc:
            raise HTTPException(400, "Invalid Last-Event-ID") from exc

        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                for event in store.events(cursor, incident_id):
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.4)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/benchmarks", status_code=202)
    async def benchmark(body: BenchmarkRequest):
        return runtime.start_benchmark(body)

    @app.get("/api/benchmarks")
    async def benchmarks():
        return store.list("benchmark")

    # Mount last: its /mcp route is handled by the official SDK, REST stays separate.
    app.mount("/", mcp.streamable_http_app())
    return app


app = create_app()
