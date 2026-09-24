from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from typing import Literal

from packages.contracts import Scenario


@dataclass(frozen=True)
class Decision:
    decision: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
    reason: str
    risk: str = "low"
    reversible: bool = True

    def payload(self) -> dict:
        return asdict(self)


def assess(
    tool: str,
    target: str,
    scenario: Scenario,
    action_count: int,
    active: bool,
    require_approval: bool = False,
) -> Decision:
    action = f"{tool}:{target}"
    if not active:
        return Decision("DENY", "Run is not active")
    if any(fnmatchcase(action, pattern) for pattern in scenario.forbidden_actions):
        return Decision("DENY", "Forbidden action", "high", False)
    if action not in scenario.allowed_actions:
        return Decision("DENY", "Action is outside scenario allowlist", "medium")
    if action_count >= 2:
        return Decision("DENY", "Action budget exhausted")
    if require_approval:
        return Decision("REQUIRE_APPROVAL", "Operator approval policy is enabled")
    return Decision("ALLOW", "Low-risk simulated action within run budget")
