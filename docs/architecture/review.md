# v0.1 architecture review

Review scope: scenario → causal world → threshold alert → isolated agent → official MCP tools → safety policy → remediation → observed verification → independent evaluation → persisted replay.

## Verified boundaries

- Agent source has no simulator, evaluator, SQLite, subprocess or Docker imports; AST test enforces this. Its Docker build copies only agent code and skills.
- The official MCP SDK hosts Streamable HTTP. No home-grown JSON-RPC imitation. Real separate-process protocol tests cover discovery, calls, structured results, errors and run-token invalidation.
- Scenarios are validated JSON. No arbitrary expression or shell evaluation. Public observations are explicit projections, not `__dict__` serialization.
- Reference behavior is clearly identified as a deterministic diagnostic baseline. It checks rising resource metrics, repeated client logs, configuration, topology and service availability; action and verification come from the retrieved SOP.
- All environment mutations pass through the scenario-aware safety policy. Only Worker restart is allowed for the current scenario; denials are events and evaluator inputs.
- Verification is checked against actual MCP metric-return events from distinct ticks after the last action, in addition to sustained healthy world state. A fabricated healthy count is insufficient.
- Hypothesis/verification artifacts are schema validated before persistence. Bad types cannot poison later grading.
- One active incident and one active agent eliminate cross-run mutable-state races. Run tokens are never stored or sent to the frontend event stream; cancelled/expired/completed tokens cannot access tools.
- No model private reasoning fields are persisted. Diagnostic evidence is intentionally public structured output.
- UI replay slices the event stream first, then derives topology, metrics, hypothesis, action and evaluation from that prefix.

## Findings fixed during implementation

1. High: trusting the Agent verification counter could label unobserved recovery as verified. Fixed by checking distinct actual MCP samples.
2. High: unvalidated arbitrary progress fields could crash grading. Fixed with typed Hypothesis/Verification contracts.
3. Medium: interrupted runs lacked an evaluation on control restart. Fixed by grading the last persisted snapshot with resolved=false.
4. Medium: browser-test process groups survived Playwright's default forced shutdown. Added explicit graceful shutdown and child-process cleanup.
5. Medium: naive JSON log formatting broke on quoted messages. Replaced with JSON serialization, with a regression test.
6. Low: large frontend file and external font dependency. Extracted focused view components, formatted sources and removed external font requests.

## Intentional limits

This is a trusted local laboratory. Control endpoints have no production authentication; container file isolation is not a sandbox for hostile third-party agent code. Current simulator supports one reusable connection-leak behavior. Production incident adapters, concurrent worlds, human approval continuation and actual LLM quality/cost evaluation are outside v0.1. The supplied external agent must obey the documented MCP-only environment contract.
