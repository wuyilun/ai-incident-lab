# Evidence-led dependency diagnosis

1. Observe: read the incident and active alerts. Describe symptoms before suggesting causes.
2. Investigate: inspect the dependency graph, time-series metrics, service state, logs and configuration for each service. Trace the alert to the component owning the abnormal behavior; an upstream error is often only a symptom.
3. Diagnose: cite at least two concrete observations and require one unambiguous failure and owning service. Use these evidence patterns:
   - Growing datastore connections, repeated acquire-without-release records, and a client pool configuration identify a leaking client. Confirm the datastore is running and the client actually depends on it.
   - CPU above 90 percent together with busy-loop records identifies CPU saturation in the service emitting those records.
   - Database latency above 600 ms together with stalled execution and slow-query backlog records identifies slow queries at the database.
   - Distinguish waiting for a database connection from slow database query execution. A running database client with at least 90 percent of its configured pool occupied, acquisition wait above 100 ms and repeated acquisition-timeout records may own an exhausted pool. Confirm its dependency graph leads to a running database whose query latency remains below 200 ms, and confirm normal upstream CPU. Correlated API, payment or worker timeouts are downstream consequences of waiting for the pool. A single timeout record or API error spike is insufficient; do not restart upstream clients or a healthy database. If query execution is also slow or evidence points to multiple owners, report ambiguity before acting.
   - More than 500 queued messages together with a running consumer's stalled acknowledgement records identifies a consumer backlog. Diagnose the consumer rather than restarting the healthy queue merely because it stores the backlog.
   - A stopped service together with an unexpected process-exit record identifies service unavailability. Distinguish this from pressure in an otherwise running service.
   Metrics alone, a configuration limit alone, or an alert label alone are insufficient. If evidence matches multiple causes or no cause, report the ambiguity without executing a speculative repair.
4. Plan: retrieve a matching SOP, inspect its preconditions, alternatives and verification limits. Prefer the smallest reversible action on the owner of the abnormal resource growth.
5. Act: pass incident-scoped actions through MCP safety policy. Never flush shared data or bypass denied actions.
6. Verify: use fresh samples from distinct simulation ticks, check the SOP's success thresholds and confirm every service is running. Check the original symptom has cleared: connections, CPU, database latency, pool occupancy and acquisition wait, or queue depth as applicable. For pool pressure require fewer than 70 active connections and acquisition wait below 100 ms, with database queries still healthy. Require the environment's healthy sample count and at least three consecutive independently observed healthy ticks. If evidence contradicts the hypothesis, report failure rather than claiming success.

Publish concise evidence, hypothesis, decision and verification artifacts. Do not publish private chain-of-thought.
