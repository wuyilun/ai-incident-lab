# Engineering rules

Keep the implementation small and causal. Agent environment access must go through official MCP tools. Never import simulator, persistence or evaluator from agent code. Never include scenario ground truth in observations, SOPs or agent prompts. Route mutations through safety policy and record denied attempts. Keep replay based on persisted events. Add meaningful tests for contract changes and run Python lint/tests plus frontend lint/typecheck/build. Do not claim unexecuted checks passed. Do not add infrastructure or agents beyond the task's requirements.
