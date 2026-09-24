可以。对于这种需求，最佳方式不是“一条超级长提示词让 AI 一次写完整项目”，而是给 AI Coding 一套 **Master Prompt + 强制工程规则 + 分阶段执行协议 + Definition of Done**。这样 Codex、CodeBuddy、Claude Code 等工具更不容易写着写着架构漂移。

下面这份可以直接作为你项目第一次启动 AI Coding 时的 **Master Prompt**。建议同时保存到仓库的 `PROJECT_SPEC.md`，再把其中长期有效的规则提炼进 `AGENTS.md` / CodeBuddy Rules。

# Incident Agent Lab — Master Engineering Prompt

You are the principal software engineer and AI systems architect responsible for building an open-source project named **Incident Agent Lab**.

Your job is not to create a toy demo. Build a small, clean, runnable, extensible engineering system that can serve as a foundation for developing, testing, evaluating, and eventually improving autonomous incident-response agents.

The project must prioritize:

1. End-to-end runnability
2. Simple architecture
3. Clear module boundaries
4. Stable contracts
5. Extensibility
6. Testability
7. Reproducibility
8. Safety
9. Observability
10. Agent evaluation

Do not optimize for maximum feature count.

Prefer a **small stable core with a large extension surface**.

---

# 1. PRODUCT VISION

Build:

**Incident Agent Lab — An open, extensible environment for building, testing, evaluating, and evolving autonomous incident-response agents.**

The system creates controlled simulated production incidents.

An AI Agent must independently:

Observe → Investigate → Diagnose → Plan → Act → Verify → Resolve

The Agent must interact with the environment through MCP tools.

The Agent must NOT know the scenario ground truth.

The system must independently evaluate whether the Agent actually solved the incident.

The frontend must visually demonstrate the entire process.

The long-term goal is to support:

* Agent development
* Agent evaluation
* Incident benchmarks
* Agent regression testing
* Scenario generation
* Skill evolution
* Memory
* Multi-agent systems
* Kubernetes environments
* Cloud environments
* Real production integrations

However, v0.1 must remain intentionally small.

---

# 2. V0.1 DEFINITION OF DONE

The most important requirement is this end-to-end workflow:

A developer clones the repository and runs:

```
docker compose up --build
```

The system starts successfully.

From the frontend or CLI, the developer injects:

```
redis-connection-leak
```

The simulated environment develops a realistic causal failure:

Worker connection leak
→ Redis connections increase
→ Redis latency increases
→ API latency/errors increase
→ Alert is generated

The Agent receives the incident.

Without access to ground truth, the Agent investigates using MCP tools such as:

* get_alerts
* get_metrics
* get_logs
* get_service_status
* get_dependencies
* get_config

The Agent identifies that the likely root cause is:

```
worker → Redis connection leak
```

The Agent retrieves the relevant SOP.

The Agent chooses an appropriate remediation.

It executes:

```
restart_service(worker)
```

through MCP.

The environment reacts.

For example:

```
Redis connections: 921 → 103
API error rate: 12.8% → 0.2%
API latency: 4.2s → 180ms
```

The Agent performs post-action verification.

The Agent determines the incident is resolved.

The independent Evaluator confirms whether the environment actually recovered.

The entire trajectory is stored.

The frontend displays:

* environment state
* incident state
* Agent observations
* Agent tool calls
* diagnosis
* remediation
* environment response
* verification
* evaluation result
* metrics before/after
* replayable event timeline

If this complete workflow is reliable, v0.1 is successful.

Do NOT sacrifice this workflow to implement additional features.

---

# 3. CORE ARCHITECTURE

Use this conceptual architecture:

```
                  Incident Agent Lab

    Scenario Engine       Knowledge / SOP
          │                    │
          ↓                    │
    Simulated World            │
          │                    │
          └────────┐    ┌──────┘
                   ↓    ↓
                 MCP Server
                     │
                     ↓
                   Agent
                     │
                     ↓
                  Actions
                     │
                     ↓
              Simulated World
                     │
                     ↓
                   Events
                     │
         ┌───────────┼───────────┐
         ↓           ↓           ↓
     Evaluator    Event Store   Frontend
         │                       │
         ↓                       ↓
     Benchmark                  Replay
```

The major modules must remain logically independent.

---

# 4. REPOSITORY STRATEGY

Use a MONOREPO.

Do NOT create separate repositories for each component.

Use approximately this structure:

incident-agent-lab/
│
├── apps/
│   ├── agent/
│   ├── control-api/
│   └── frontend/
│
├── simulator/
│   ├── world/
│   ├── fault_engine/
│   └── scenarios/
│
├── mcp/
│   ├── server/
│   ├── tools/
│   └── safety/
│
├── knowledge/
│   ├── sop/
│   ├── failure_modes/
│   └── skills/
│
├── evaluator/
│
├── packages/
│   ├── event_schema/
│   ├── scenario_schema/
│   ├── mcp_contract/
│   └── common/
│
├── services/
│   ├── api/
│   └── worker/
│
├── benchmarks/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── infra/
│
├── scripts/
│
├── docs/
│   └── architecture/
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── PROJECT_SPEC.md
├── AGENTS.md
└── LICENSE

You may adjust minor details if there is a strong engineering reason.

Do not collapse clearly independent modules into one large application.

---

# 5. CORE CONTRACTS

Treat the following as first-class stable contracts:

## Event Schema

Defines communication through the system.

Examples:

* incident.created
* incident.updated
* incident.resolved
* environment.metric
* environment.state_changed
* agent.started
* agent.observation
* agent.hypothesis
* agent.tool_call
* agent.tool_result
* agent.action
* agent.verification
* evaluator.result

Every event should include at minimum:

* event_id
* timestamp
* event_type
* source
* incident_id where applicable
* correlation/run ID
* structured payload

Do not couple consumers to internal Python objects.

---

## Scenario Schema

Scenarios must be data-driven.

Example:

```
id: redis-connection-leak
name: Redis Connection Leak
severity: high

target:
  service: worker

fault:
  type: connection_leak
  intensity: 0.8

symptoms:
  - redis_connections_high
  - api_latency_high
  - api_error_rate_high

ground_truth:
  root_cause: worker_connection_leak

allowed_actions:
  - restart_worker

forbidden_actions:
  - flush_redis
  - delete_data

success:
  redis_connections_lt: 200
  api_error_rate_lt: 1
```

Scenario definitions must not contain executable arbitrary code.

Validate scenarios against a schema.

---

## MCP Contract

Agent/environment interaction must happen through MCP.

Observation tools should include:

* get_alerts
* get_metrics
* get_logs
* get_service_status
* get_dependencies
* get_config
* get_incident
* get_sop

Action tools should initially include:

* restart_service
* start_service
* stop_service
* update_config
* clear_cache

Incident lifecycle tools may include:

* acknowledge_incident
* resolve_incident

Keep the interface small.

Do not add tools unnecessarily.

---

# 6. STRICT AGENT BOUNDARIES

The Agent MUST NOT:

* access Docker directly
* access simulator internals
* read scenario ground_truth
* query evaluator internals
* directly mutate the database
* bypass MCP
* execute arbitrary shell commands against the environment

The Agent may only interact with the incident environment through approved MCP tools.

This separation is mandatory.

---

# 7. GROUND TRUTH IS SECRET

Scenario ground truth exists only for:

* Scenario Engine
* Evaluator
* benchmark infrastructure

It must NEVER be included in:

* Agent prompts
* MCP observation responses
* logs visible to Agent
* frontend Agent context
* retrieved SOP metadata
* environment observation APIs

Add tests specifically checking for ground-truth leakage.

---

# 8. SIMULATED ENVIRONMENT

v0.1 contains three logical services:

```
API
 │
 ↓
Redis
 ↑
 │
Worker
```

Use Docker Compose.

Prefer simple services over realistic infrastructure complexity.

Do NOT introduce Kubernetes in v0.1.

The environment must be stateful and causal.

Do not merely return static mock metrics.

Example:

Worker connection leak
→ connection count increases over time
→ Redis pressure increases
→ latency increases
→ API errors increase

Actions must affect world state.

Example:

restart worker
→ worker connection state resets
→ Redis pressure decreases
→ API latency recovers

Implement a deterministic or seeded simulation clock/tick mechanism where useful.

Support reproducible runs using a random seed.

---

# 9. FAULT ENGINE

Faults must be injectable.

The Fault Engine must:

1. load Scenario definitions
2. validate them
3. modify world state
4. advance fault behavior over time
5. emit structured events
6. determine whether fault effects remain active

Do not hard-code scenario IDs throughout business logic.

Adding a new scenario should normally require:

* scenario YAML/JSON
* optional reusable fault behavior implementation
* optional SOP
* evaluator expectations

It should not require rewriting the architecture.

---

# 10. KNOWLEDGE / SOP / SKILLS

Maintain conceptual separation:

Knowledge = what the Agent knows.

SOP = recommended operational procedure.

Skill = reusable method for performing reasoning/work.

MCP Tool = action/observation capability exposed by the environment.

Do not merge these concepts.

Example SOP:

```
id: SOP-REDIS-CONNECTION-001

symptoms:
  - redis_connections_high
  - api_latency_high

investigation:
  - inspect_redis_connections
  - inspect_worker_logs

remediation:
  preferred:
    - restart_worker

avoid:
  - restart_redis
  - flush_redis

verification:
  - redis_connections_normal
  - api_error_rate_normal
```

The Agent should retrieve SOPs rather than having scenario-specific logic hard-coded into prompts.

---

# 11. AGENT LOOP

Implement an explicit state machine or equivalent orchestration for:

Observe
→ Investigate
→ Diagnose
→ Plan
→ Act
→ Verify
→ Resolve

Do not create an uncontrolled infinite autonomous loop.

Include:

* maximum iteration count
* maximum tool calls
* timeout
* action budget
* failure state
* cancellation

Agent outputs should be structured.

Store:

* observations
* evidence
* hypotheses
* selected actions
* tool calls/results
* verification result
* final incident summary

Do NOT attempt to expose private model chain-of-thought.

Only store concise structured reasoning artifacts intended for observability, such as:

* evidence
* hypothesis
* decision summary
* action rationale

---

# 12. ACTION SAFETY LAYER

Every mutating MCP action must pass through a Safety Layer.

Each action should support metadata such as:

* risk level
* target
* reversibility
* reason
* incident ID

Support policy decisions such as:

ALLOW
DENY
REQUIRE_APPROVAL

For v0.1, automatic execution may be allowed for low-risk simulated actions.

Still implement the abstraction so future environments can require human approval.

Record every action attempt, including denied actions.

---

# 13. EVENT STORE

The Event Store is the spine of the system.

Everything important must produce structured events.

Examples:

* fault injected
* metric changed
* alert generated
* incident created
* Agent started
* observation collected
* hypothesis generated
* SOP retrieved
* tool called
* action attempted
* action completed
* environment changed
* verification performed
* incident resolved
* evaluator completed

Consumers should depend on events/contracts rather than simulator implementation details.

The Event Store must support:

* ordered incident timeline
* filtering by incident
* filtering by run
* replay
* frontend streaming

Prefer simple persistence first.

Do not introduce Kafka or other heavy event infrastructure in v0.1.

---

# 14. CONTROL API

Implement a FastAPI Control API.

It should expose APIs for:

* environment state
* services
* scenarios
* inject scenario
* incidents
* incident detail
* start Agent
* stop Agent if appropriate
* events
* evaluation result
* benchmark runs

Use WebSocket or SSE for live event streaming.

Frontend must communicate through Control API.

Frontend must NOT communicate directly with Docker or simulator internals.

---

# 15. EVALUATOR

Evaluator must be independent from Agent.

Evaluator knows ground truth.

Agent does not.

Evaluation dimensions:

## Outcome

* incident_resolved
* environment_recovered
* success_conditions_met

## Diagnosis

* root_cause_correct
* affected_service_correct
* evidence quality where appropriate

## Remediation

* remediation_correct
* recovery verified

## Safety

* unsafe_action_count
* forbidden_action_count
* denied_action_count

## Efficiency

* tool_call_count
* action_count
* unnecessary_action_count
* time_to_recovery
* token/cost fields when available

Do not depend only on LLM-as-a-judge.

Prefer deterministic graders whenever possible.

Use model-based grading only for inherently semantic criteria.

Keep individual metrics.

Do NOT reduce everything to one opaque score.

---

# 16. BENCHMARK

Implement a simple benchmark runner.

It should be able to run:

```
scenario × agent configuration × seed × trial
```

Store results.

Because Agent behavior can be nondeterministic, support repeated trials.

Example:

```
benchmark run
    redis-connection-leak
    5 trials
```

Aggregate:

* resolution rate
* diagnosis accuracy
* safety rate
* average tool calls
* average actions
* average MTTR

Design benchmark interfaces now, even if v0.1 contains only a few scenarios.

---

# 17. FRONTEND

Use:

* React
* TypeScript
* Vite

Use a reasonable charting library such as ECharts or Recharts.

Do not over-engineer styling.

The UI must make Agent capability visually understandable.

Create these primary views:

## Dashboard

Show:

* incidents attempted
* resolution rate
* diagnosis accuracy
* safety
* average MTTR
* average actions/tool calls
* recent incidents

## Environment

Show:

* API
* Redis
* Worker
* service status
* dependency graph
* important metrics

## Incident Detail

Show incident lifecycle:

Detected
→ Investigating
→ Diagnosing
→ Remediating
→ Verifying
→ Resolved / Failed

Show structured Agent trace.

Example:

```
14:32:25 Observation: API errors elevated
14:32:28 Tool: get_metrics(redis)
14:32:31 Tool: get_logs(worker)
14:32:35 Hypothesis: worker connection leak
14:32:38 SOP: SOP-REDIS-CONNECTION-001
14:32:42 Action: restart_service(worker)
14:32:52 Redis connections: 921 → 103
14:33:02 Verification: API error rate recovered
14:33:05 Incident resolved
```

## Metrics Timeline

Plot:

* Redis connections
* API latency
* API error rate

Mark remediation actions on the timeline.

The UI should visually communicate:

FAULT
→ DEGRADATION
→ AGENT INVESTIGATION
→ ACTION
→ RECOVERY

## Diagnosis Panel

Show:

* suspected root cause
* evidence
* confidence if available
* SOP
* remediation
* verification
* evaluation result

## Replay

Allow historical incidents to be replayed from stored events.

Synchronize:

* environment state
* Agent trace
* metrics
* actions

A basic playback implementation is sufficient for v0.1.

---

# 18. OBSERVABILITY

The system itself must be observable.

Use structured logs.

Every request/run should have correlation IDs where practical.

Avoid introducing Prometheus, Loki, Jaeger, Grafana, or OpenTelemetry unless necessary for v0.1.

Design interfaces so these can be added later.

---

# 19. STORAGE

Prefer minimal infrastructure.

SQLite is acceptable for local-first v0.1 if it significantly simplifies setup.

PostgreSQL is acceptable if required.

Do not introduce multiple databases unnecessarily.

Store at least:

* incidents
* events
* Agent runs
* evaluations
* benchmark runs

Metrics may initially be represented as events.

---

# 20. TECHNOLOGY PREFERENCES

Backend:

* Python 3.12+
* FastAPI
* Pydantic
* pytest
* asyncio where appropriate

Frontend:

* React
* TypeScript
* Vite

Infrastructure:

* Docker
* Docker Compose

Quality:

* Ruff
* mypy where practical
* pytest
* ESLint
* TypeScript strict mode

Use current stable dependency versions.

Pin important dependencies appropriately.

---

# 21. TESTING STRATEGY

Tests are mandatory.

Create:

## Unit Tests

For:

* scenario validation
* world-state transitions
* fault behavior
* event schemas
* evaluator rules
* safety policies

## Integration Tests

For:

* Control API
* MCP tools
* simulator ↔ MCP
* action → environment transition
* Event Store

## E2E Test

At least one mandatory test:

```
redis-connection-leak
```

Test flow:

1. start environment
2. inject scenario
3. confirm degradation
4. start Agent
5. Agent investigates through MCP
6. Agent executes remediation
7. environment recovers
8. Agent verifies
9. evaluator confirms recovery
10. complete trajectory exists

If real LLM credentials are unavailable, provide a deterministic scripted/reference Agent for CI so the full architecture can still be tested.

The real LLM Agent and reference Agent must use the same MCP contracts.

---

# 22. CI

Configure GitHub Actions.

At minimum:

Backend:

```
lint
type check where enabled
unit tests
integration tests
```

Frontend:

```
lint
type check
build
```

Optionally run a lightweight E2E Docker test.

Main branch should remain runnable.

---

# 23. DEVELOPER EXPERIENCE

A new developer should be able to:

```
git clone ...
cp .env.example .env
docker compose up --build
```

and get a working system.

Provide Make targets where useful:

```
make dev
make test
make lint
make e2e
make scenario SCENARIO=redis-connection-leak
make benchmark
```

Do not require unnecessary manual setup.

---

# 24. DOCUMENTATION

Create:

README.md

ARCHITECTURE.md

PROJECT_SPEC.md

AGENTS.md

docs/architecture/

Each major module should have a short README explaining:

* responsibility
* inputs
* outputs
* dependencies
* extension points
* how to test

README must contain a quick-start section.

ARCHITECTURE.md must explain module boundaries and data flows.

---

# 25. EXTENSION PRINCIPLE

Adding functionality should be predictable.

Document:

## How to add a Scenario

## How to add a Fault Behavior

## How to add an SOP

## How to add an MCP Observation Tool

## How to add an MCP Action Tool

## How to add an Evaluator

## How to add a frontend visualization

## How to add another Agent implementation

This extension documentation is part of Definition of Done.

---

# 26. FUTURE COMPATIBILITY

Do NOT implement these now unless necessary:

* Kubernetes
* AWS/GCP/Azure
* multi-agent orchestration
* distributed message queues
* fine-tuning
* complex RAG infrastructure
* Prometheus/Grafana stack
* service mesh
* production authentication
* enterprise RBAC

But maintain boundaries that allow future architecture:

```
Agent
  ↓
 MCP
  ↓
┌───────────────┐
│               │
```

Simulation       Production
MCP Server       MCP Server

The logical Agent-facing interface should remain reusable.

---

# 27. ENGINEERING RULES

Follow these strictly.

## Rule 1

Do not over-engineer.

## Rule 2

Do not implement fake functionality merely to make the UI look complete.

## Rule 3

Prefer working vertical slices over broad incomplete scaffolding.

## Rule 4

Do not duplicate domain models between modules when a shared contract exists.

## Rule 5

Do not create circular dependencies.

## Rule 6

Core contracts must remain independent from implementations.

## Rule 7

Do not allow Agent access to ground truth.

## Rule 8

Do not allow Agent direct Docker access.

## Rule 9

Every Agent action must be observable.

## Rule 10

Every mutating action must pass through Safety Layer.

## Rule 11

Every incident must be replayable from events as far as practical.

## Rule 12

Every important feature must have tests.

## Rule 13

Do not silently ignore errors.

Use explicit error types and structured logging.

## Rule 14

Keep files and classes reasonably small.

Refactor when responsibilities become mixed.

## Rule 15

Prefer typed interfaces and schemas over unstructured dictionaries.

---

# 28. IMPLEMENTATION PROCESS

Do NOT attempt to implement the entire project in one uncontrolled pass.

Work incrementally.

Use the following phases.

## Phase 0 — Foundation

Implement:

* repository structure
* package structure
* schemas/contracts
* configuration
* Docker foundation
* basic CI
* architecture docs

Verify tests.

Commit-ready state.

---

## Phase 1 — Simulated World

Implement:

* API service
* Redis integration/simulation
* Worker
* world state
* tick/update loop
* metrics/log observations
* redis-connection-leak
* recovery behavior

Verify fault → degradation → remediation → recovery without AI.

---

## Phase 2 — Events + Control API

Implement:

* Event Store
* incident model
* FastAPI Control API
* scenario injection
* environment queries
* event streaming

Verify frontend/API consumers could observe a complete incident.

---

## Phase 3 — MCP

Implement observation tools first.

Then action tools.

Then Safety Layer.

Verify all environment access occurs through contracts.

---

## Phase 4 — Agent

Implement:

Observe
→ Investigate
→ Diagnose
→ Plan
→ Act
→ Verify

Provide:

* real LLM Agent adapter
* deterministic reference Agent

Do not hard-code the reference Agent into production Agent behavior.

---

## Phase 5 — Evaluator

Implement deterministic evaluation.

Verify ground truth remains isolated.

---

## Phase 6 — Frontend

Implement:

* Dashboard
* Environment
* Incident
* Agent Trace
* Metrics
* Evaluation
* Replay

Prioritize functionality over visual decoration.

---

## Phase 7 — Benchmark

Implement repeated scenario trials and aggregation.

---

## Phase 8 — Hardening

Run:

* lint
* type checking
* unit tests
* integration tests
* E2E tests
* Docker clean-start test

Fix issues rather than documenting around them.

---

# 29. REQUIRED WORKING STYLE

Before implementing each phase:

1. Inspect existing repository state.
2. Explain internally what must change.
3. Identify affected contracts.
4. Avoid unnecessary architectural changes.
5. Implement the smallest complete vertical slice.
6. Run relevant tests.
7. Fix failures.
8. Update documentation when behavior/contracts change.

Never claim something works without running the relevant test or command when execution is available.

Do not leave placeholder implementations such as:

```
TODO
pass
NotImplementedError
```

for functionality required by the current phase.

Do not create fake success responses.

---

# 30. CHANGE DISCIPLINE

Before changing any of these:

* event schema
* scenario schema
* MCP contract
* incident lifecycle

perform an impact analysis across:

* simulator
* Agent
* MCP
* evaluator
* API
* frontend
* tests
* documentation

Prefer backward-compatible changes.

---

# 31. DECISION PRIORITY

When requirements conflict, prioritize in this order:

1. Correctness
2. Safety
3. End-to-end runnability
4. Clear architecture
5. Testability
6. Extensibility
7. Developer experience
8. Performance
9. UI polish
10. Feature quantity

---

# 32. IMPORTANT PRODUCT PHILOSOPHY

This project is NOT primarily:

"an AI that restarts Redis."

It is:

"a controlled interactive world where incident-response agents can be developed, observed, evaluated, compared, and improved."

Therefore:

Simulator creates problems.

Agent attempts to solve problems.

Evaluator determines whether they were solved correctly.

Event Store preserves what happened.

Frontend makes Agent behavior understandable.

Benchmark makes Agent capability measurable.

Keep these responsibilities separate.

---

# 33. FIRST TASK

Do not immediately write all application code.

First:

1. Inspect the repository if it already exists.
2. Create or update:

   * PROJECT_SPEC.md
   * ARCHITECTURE.md
   * AGENTS.md
3. Propose the final repository tree.
4. Define:

   * Event Schema
   * Scenario Schema
   * MCP Contract
   * Incident lifecycle
5. Identify major architectural risks.
6. Produce an implementation checklist for Phases 0–8.

Then begin Phase 0.

After each phase:

* run tests
* report what was implemented
* report commands executed
* report test results
* list architectural decisions
* list known limitations
* state the next phase

Continue sequentially unless blocked by a decision that materially affects architecture.

When a minor implementation choice is unspecified, choose the simplest reasonable solution and continue rather than stopping for clarification.

The final goal is a clean, tested, documented, locally runnable Incident Agent Lab v0.1 with a demonstrable end-to-end incident-response loop.

我还建议你**不要只给 Codex/CodeBuddy 这一份 Prompt 就放任它跑到底**。最有效率的方式，是第一次用上面的 Master Prompt 建立“宪法”，然后后续每个 Phase 用非常短的执行 Prompt。例如 Phase 1 可以直接说：

Continue implementing Incident Agent Lab according to PROJECT_SPEC.md, ARCHITECTURE.md, AGENTS.md, and the repository's existing contracts.

Implement the next incomplete phase only.

Before coding:

1. Inspect the current repository and git diff.
2. Read the relevant architecture/contracts.
3. Identify affected modules.
4. Preserve existing stable contracts unless a change is necessary.

During implementation:

* Complete a working vertical slice.
* Do not implement unrelated future features.
* Do not introduce unnecessary infrastructure.
* Do not expose scenario ground truth to the Agent.
* Do not allow the Agent to bypass MCP.
* Maintain Event, Scenario, and MCP contract boundaries.
* Add/update tests together with implementation.

Before finishing:

1. Run linting.
2. Run relevant unit tests.
3. Run relevant integration tests.
4. Run E2E tests when applicable.
5. Fix failures rather than merely reporting them.
6. Update documentation if contracts or behavior changed.

At completion report:

* implemented functionality
* files/modules materially changed
* architectural decisions
* commands/tests actually executed
* results
* known limitations
* next recommended phase

Do not claim success for anything that was not actually verified.

还有第三份我认为非常重要：**当 AI Coding 开始越写越复杂时，用它做架构审查，而不是继续加功能。**

Stop feature development temporarily and perform an architecture and quality review of the current Incident Agent Lab repository.

Do not assume the implementation matches the intended architecture. Verify it from the code.

Review specifically for:

* module responsibility violations
* circular dependencies
* duplicated domain models
* unstable or bypassed contracts
* Agent access to simulator internals
* Agent access to scenario ground truth
* direct Docker access by Agent
* actions bypassing the Safety Layer
* frontend coupling to simulator internals
* scenario-specific logic hard-coded into Agent
* evaluator coupled to Agent implementation
* events that cannot support replay
* missing correlation/run IDs
* uncontrolled Agent loops
* missing timeouts/budgets
* fake/mock functionality accidentally used in production paths
* unnecessary infrastructure
* insufficient tests
* dead code
* oversized modules
* configuration duplication
* security/safety problems

Then run the existing tests and inspect the end-to-end redis-connection-leak workflow.

Classify findings as:

Critical
High
Medium
Low

Fix Critical and High issues that can be corrected without unnecessary redesign.

Do not add new product features during this task.

After fixes, rerun relevant tests and summarize the verified architecture state.

### 实际使用顺序

我建议你的 GitHub 项目从第一天就采用这个节奏：

```text
Master Prompt
      ↓
PROJECT_SPEC.md
ARCHITECTURE.md
AGENTS.md
      ↓
Phase 0
      ↓
test
      ↓
Phase 1
      ↓
test
      ↓
Phase 2
      ↓
test
      ↓
...
      ↓
redis-connection-leak E2E
      ↓
Architecture Review
      ↓
v0.1
```

其中有一个设计我特意加进去了：**Reference Agent**。真实 LLM Agent 会受到 API Key、模型变化、随机性和网络影响，如果你的 E2E 测试必须依赖真实 LLM，那么 GitHub CI 很快就会变得不稳定。Reference Agent 走**完全相同的 MCP 接口**，但行为确定，这样你能分别回答两个问题：“平台本身坏了吗？”以及“这个模型/Agent 变差了吗？”

另外，我会把三个文件视为整个项目最重要的工程资产：`PROJECT_SPEC.md` 定义**做什么**，`ARCHITECTURE.md` 定义**为什么这样设计以及模块怎么交互**，`AGENTS.md` 定义 **AI Coding 修改这个仓库时必须遵守什么规则**。Prompt 会不断变化，但这三个文件应该跟代码一起进入 Git、接受 PR review。

等 v0.1 跑通以后，再让 AI Coding 扩展 `worker-crash`、`redis-memory-pressure`、`api-latency`、`bad-config`、`network-latency`、`cascading-failure` 等场景；不要在第一次生成时把这些全部塞进去。这样更容易得到一个**真的能跑的系统，而不是一个目录和代码很多但没有可靠闭环的项目**。
