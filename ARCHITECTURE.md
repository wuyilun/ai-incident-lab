# Architecture

Three deployable services: control (FastAPI + official MCP SDK), agent (isolated FastAPI runner), frontend (React/Vite, served by nginx). Gateway/API/Worker/Redis/database/queue are simulated logical services inside a seeded causal world, not real infrastructure containers.

```
frontend → control API → scenario engine → world → alerts
               ↓                           ↓
            SQLite events ← MCP tools ← agent runner
               ↓               ↓             ↑
           evaluator       safety policy   skills / SOP retrieval
```

## Boundaries
- `packages/contracts.py`: shared wire schemas, no implementation imports.
- `simulator/`: private scenario truth and mutable world. No Agent imports.
- `apps/control_api/`: persistence, orchestration, REST and SSE.
- `lab_mcp/`: official protocol server, scoped observations, safety-gated actions. Named to avoid shadowing the SDK's `mcp` package.
- `apps/agent/`: MCP client + bounded reference/LLM loops. Deployment contains only agent code and diagnostic skills, no simulator/scenarios/evaluator/store.
- `knowledge/skills/`: reusable diagnostic method; `knowledge/sop/`: retrievable operational procedure, no scenario identifiers or hidden ground truth.
- `evaluator/`: deterministic scoring of private expectations, world state and recorded evidence.
- `apps/frontend/`: REST/SSE consumer; historical state reconstructed from event snapshots.

## Intentional simplifications
One live world/incident at a time; SQLite and one control worker avoid distributed coordination. Benchmarks serialize trials. Tick is deterministic for a seed; wall-clock agent latency may change incident duration. World snapshots persist each tick. Interrupted active runs fail explicitly on restart, preserving their trajectory.

## Risks and controls
Truth leakage → explicit observation projections and leakage tests. Fake resolution → multiple healthy ticks and independent evaluator. Unsafe tools → central policy, run/action budgets, audited denials. Stale agent → run-scoped token revoked at completion/cancel. Lost UI events → cursor-based SSE and persisted snapshots. Model hallucination → tools from MCP discovery, structured artifacts, bounded loop. Local-only unauthenticated control API → bind published ports to localhost.

## Registered Agents and delivery

The registry persists public Agent identity and a hash of each external registration credential. Managed Agents share the isolated runner; a five-second cached health probe reports supported/configured modes. External Agents poll a Bearer-authenticated inbox and maintain a 15-second heartbeat lease. No arbitrary webhook URLs, message broker, inbound Agent ports or additional services are required.

An injection snapshots the selected Agent identity. At the alert threshold, orchestration creates a scoped run and assignment. The external connector receives and explicitly acknowledges that assignment before MCP access is allowed; only this acknowledgement emits `agent.alert_received` and `agent.started`. Repeated delivery and acknowledgement are idempotent. Managed Agents acknowledge implicitly on their first actual alert/incident MCP observation. Pending delivery expires after 30 seconds, execution after 120 seconds; completion/cancellation revokes the run credential. Active Agents cannot be disabled or rotated mid-run. Registration and run credentials never appear in event traces.

The frontend and nginx/Vite proxy both REST and Streamable HTTP MCP on the same origin. The two-column workbench projects environment snapshots and Agent artifacts from one persisted event cursor. Every incident event carries the simulation tick, so three aligned metric charts can mark lifecycle events consistently; events sharing a tick are separately selectable in the marker rail. Downloaded reports use only artifacts at or before the selected cursor.

## v0.3 direct MCP and extensible simulation

Registration credentials can now authenticate directly to the same official MCP endpoint. `check_connection` refreshes presence; `receive_alert` acknowledges only the authenticated Agent's assignment. All subsequent calls reuse the same credential; mutating/reporting tools also require the assignment's run_id, preventing stale calls from a cancelled task affecting a later task. The REST inbox remains a compatibility adapter. `get_diagnostic_skill` exposes the reusable method after task acknowledgement; private scenario truth remains inaccessible.

The environment JSON defines service identity, labels, kinds, public configuration, node metric projections and dependency edges. World observations drive topology rendering and dependency impairment; five explicit causal fault mechanisms modify evolving process/resource state. Adding a scenario using existing mechanics is data-only; new mechanics require implementation and tests. Reference diagnosis derives a unique match from live logs/configuration/metrics and retrieves a matching SOP.

Leaderboard rows are derived from persisted evaluated resolved/failed incidents, grouped by Agent and scenario. Equal scenario weights, coverage penalty and explicit sample counts prevent repeated easy trials replacing coverage. Cancelled incidents are excluded. The board is a local experimental comparison, not an authenticated cross-provider benchmark.
