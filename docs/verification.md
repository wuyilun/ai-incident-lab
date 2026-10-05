# Verification record

Dates: 2026-09-23–2026-10-03. This file records actual executions, not planned capabilities.

## Topology correctness and diagnostic complexity (2026-10-03)

- Python suite: **77 passed in 38.57s**. New tests prove observed health is independent of hidden injected target, healthy dependencies do not inherit caller faults, unrelated consumer outage does not fail the API, and pool exhaustion propagates only through relevant dependencies. Operator injection target stays out of MCP observations.
- Pool diagnosis has 11 regressions, including missing/conflicting evidence, healthy-database comparison, premature recovery rejection and a real MCP repair that restarts only db_proxy.
- Local browser suite: **7 passed in 1.3m**. Tests ten-node topology, six scenarios, injection preview/active/recovered markers, replay, direct dependency focus and expanded view. SVG route samples are checked against node rectangles; no line penetrations found.
- Frontend ESLint/typecheck/production build passed; Ruff/format passed (60 files), mypy passed (25 files). Expanded fault topology screenshot visually reviewed.
- Docker rebuild/startup completed. All **7 production browser tests passed in 1.3m**, including geometric non-intersection checks and the connection-pool diagnostic contrast. Deployment stays at http://localhost:5173 with the final pool incident resolved.
- Artifacts: `artifacts/python-topology.log`, `artifacts/browser-topology.log`, `artifacts/topology-expanded-fault.png`, `artifacts/docker-topology-build.log`, `artifacts/docker-topology-startup.log`, `artifacts/docker-browser-topology.log`.

## v0.3 extensible environment and direct MCP (2026-10-02)

- Full Python suite: **60 passed in 38.78s**. Includes all five causal faults, wrong-target repair remaining ineffective, configurable topology validation/extension, direct registration-token MCP for all scenarios, leaderboard coverage weighting and cancellation exclusion.
- Registration-token mutations require the current run_id. Regression cancels task A and starts B for the same Agent, then proves all six mutation/reporting tools reject A's late requests and requests without a run_id. Original run-token integrations remain compatible.
- Frontend lint/typecheck/build passed. Ruff and format check passed (58 files), mypy passed (25 files including the direct MCP example).
- Local browser suite: **6 passed in 1.1m**. Registers an external Agent in the page and runs `scripts/mcp_agent.py` with only MCP URL + registration token, verifies real alert reception, diagnosis/remediation, reports/replay/mobile and leaderboard filtering. Four additional browser tests verify CPU, database latency, consumer backlog and queue outage through the dynamic six-node topology and scenario-specific charts; cancellation remains covered.
- Visual review: dynamic topology fault screenshot and leaderboard screenshot inspected. Results are actual persisted evaluations; no synthetic leaderboard rows are injected.
- Production Docker build/startup and health checks passed. All **6 production browser tests passed in 1.2m**, including direct-token MCP through nginx and all five fault repairs. Final API read confirmed six running services, five scenarios, and persisted evaluated leaderboard entries.
- Deployment remains running at http://localhost:5173 with the last queue-outage incident resolved. Existing history was preserved.
- Repaired the local Python interpreter installation and moved it from temporary storage into ignored `data/python`, so OS temporary cleanup no longer breaks this workspace virtualenv.

Artifacts: `artifacts/python-v03.log`, `artifacts/browser-v03.log`, `artifacts/expanded-topology-fault.png`, `artifacts/leaderboard.png`, `artifacts/docker-v03-build.log`, `artifacts/docker-v03-startup.log`, `artifacts/docker-browser-v03.log`, `artifacts/leaderboard-v03.json`.

## v0.2 registration and workbench verification (2026-09-25–27)

- Full Python suite: **49 passed in 18.53s**. Includes actual standalone Connector subprocess → authenticated assignment → acknowledgement → official MCP → one correct repair → sustained recovery; cross-Agent isolation, duplicate delivery/ack, credential rotation, disabled/busy handling, receipt deadlines, restart and cancellation.
- Connector regressions include a successful resolution racing with heartbeat acknowledgement during MCP cleanup; real cancellation remains bounded.
- Ruff check and format check passed (51 files); mypy passed (22 source files).
- Frontend ESLint, TypeScript and Vite production build passed.
- Local browser suite: **2 passed in 25.2s**; page registration, real external connector through the frontend origin, automatic repair, report download, desktop layout, replay, reload, mobile overflow and cancellation.
- Production Compose build/startup passed; control and Agent containers are healthy, frontend serves v0.2 at http://localhost:5173. Existing SQLite history was preserved.
- Production browser suite: **2 passed in 34.7s**, including the final alert-marker replay regression. The external Connector used nginx's frontend origin for both authenticated REST and MCP; it received the alert, repaired through the official MCP client and exited successfully.
- Production builtin Reference smoke passed: Redis connections **575.8 → 110.2**, API latency **1209.2 → 180 ms**, error rate **3.71% → 0.2%**. One Worker restart, 22 tool calls, 3.41 seconds from Agent start to verified recovery; independent root cause and sustained recovery checks passed, with zero unsafe/forbidden actions.
- Final source passes `git diff --check`. The running deployment is left with the final smoke incident resolved and simulated services healthy.

Artifacts: `artifacts/docker-backend-build.log`, `artifacts/docker-frontend-build.log`, `artifacts/docker-startup.log`, `artifacts/docker-browser-verification.log`, `artifacts/docker-smoke.log`, `artifacts/smoke-result.json`, `artifacts/agent-registry.png`, `artifacts/console-trace.png`, `artifacts/console-desktop.png`, `artifacts/console-mobile.png`.

The limits stated below remain applicable: Reference is deterministic, infrastructure is simulated, and no live LLM provider was evaluated.

## v0.1 baseline — executed and passed

| Check | Result |
| --- | --- |
| `pytest -q` | **27 passed**; unit tests, actual separate-process HTTP/MCP integration, end-to-end incident response, repeated benchmarks, negative paths and offline LLM adapter contracts |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| `mypy packages simulator evaluator apps lab_mcp` | Passed, 20 source files |
| Frontend ESLint + TypeScript + Vite production build | Passed |
| Playwright against local services | **2 passed**: injection → diagnosis → SOP → remediation → evaluation → replay/reload/mobile; manual alert → cancellation |
| `docker compose config --quiet` | Passed |
| Docker Compose full build + startup | Passed; control and agent healthy, frontend serving production assets |
| Compose black-box smoke | Passed; full HTTP/MCP remediation and independent evaluation |
| Playwright against nginx/Compose production frontend | **2 passed**, 22.6 seconds; same injection, recovery, replay, mobile and cancellation checks |
| Compose persisted benchmark | **3/3 resolved**, 100% diagnosis accuracy and safety; mean 22 tool calls, 1 action, 3.51s recovery |
| Agent container file isolation | Verified: no simulator, evaluator, control source or Docker socket |

The Python E2E test uses actual independently launched control and agent processes and the official MCP client. It verifies metrics degraded before acting, one correct remediation, sustained recovery, independent root-cause grading, complete event ordering and no scenario metadata/ground-truth leakage into MCP responses. The benchmark test runs two seeds × two trials with 100% resolution/diagnosis/safety for the Reference agent.

Negative checks include unsafe/wrong-target action denial, invalid/revoked tokens, action budgets, timeouts, premature resolution, forged healthy counts, malformed artifacts, process restart, missing LLM credentials and a model response that claims success without using resolution tools.

## Browser artifacts

- `artifacts/console-desktop.png`
- `artifacts/console-mobile.png`
- `artifacts/browser-verification.log`
- `artifacts/docker-browser-verification.log`

Verified at 1440 × 1080 and 390 × 844 viewport sizes. No uncaught browser JavaScript errors or document horizontal overflow. Replay at the first event hides later diagnosis and evaluation. Historical data survives page reload. Local tests used installed Chrome via `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; CI installs Playwright Chromium.

## Deployment verification

Completed `docker compose build`, `docker compose up -d`, container health checks, Agent container isolation checks and `python scripts/smoke.py` against the running Compose deployment.

The host's Docker Desktop credential helper stalled during initial build; the same Compose commands succeeded with an empty temporary `DOCKER_CONFIG`, without accessing stored registry credentials. No global Docker configuration was modified. This workaround is specific to the host, not an application dependency.

Actual seed=42 smoke result:

| Metric | At alert | After verified repair |
| --- | --- | --- |
| Redis connections | 575.8 | 110.2 |
| API latency | 1209.2 ms | 180 ms |
| API error rate | 3.71% | 0.2% |

One Worker restart, 22 MCP tool calls, 3.9 seconds from Agent start to verified recovery, zero unsafe/forbidden actions. Root cause, responsible service, remediation and sustained sampled recovery all graded correct. Metrics are from this actual run, not hard-coded expected values.

Artifacts: `artifacts/docker-build.log`, `artifacts/docker-smoke.log`, `artifacts/smoke-result.json`, `artifacts/docker-benchmark.json`.

The deployment is left running at http://localhost:5173, with the last benchmark incident resolved and the simulated services healthy.

## Honest limits

No real provider credentials were supplied. LLM adapter behavior was verified with an offline HTTP provider fixture; actual model diagnostic accuracy, token usage and cost were not evaluated. Reference results do not imply LLM benchmark performance. GitHub Actions configuration was created but has not run on a remote GitHub runner in this session.
