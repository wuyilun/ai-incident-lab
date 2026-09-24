# Verification record

Dates: 2026-09-23–24. This file records actual executions, not planned capabilities.

## Executed and passed

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
