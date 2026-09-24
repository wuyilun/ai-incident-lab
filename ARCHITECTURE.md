# Architecture

Three deployable services: control (FastAPI + official MCP SDK), agent (isolated FastAPI runner), frontend (React/Vite, served by nginx). API/Redis/Worker are simulated logical services inside a seeded causal world, not real infrastructure containers.

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
