# Evidence-led dependency diagnosis

1. Observe: read the incident and active alerts. Describe symptoms before suggesting causes.
2. Investigate: inspect the dependency graph, time-series metrics, service state, logs and configuration. Compare the upstream producer's resource ownership with the downstream saturation. Distinguish a stopped dependency from resource pressure.
3. Diagnose: cite at least two concrete observations. Identify the resource behavior and owning service, not just the service emitting the alert. Do not infer a cause solely from an alert label.
4. Plan: retrieve a matching SOP, inspect its preconditions, alternatives and verification limits. Prefer the smallest reversible action on the owner of the abnormal resource growth.
5. Act: pass incident-scoped actions through MCP safety policy. Never flush shared data or bypass denied actions.
6. Verify: use fresh samples from distinct simulation ticks, check all success thresholds and confirm every service is running. Resolve only after at least three consecutive healthy ticks. If evidence contradicts the hypothesis, report failure rather than claiming success.

Publish concise evidence, hypothesis, decision and verification artifacts. Do not publish private chain-of-thought.
