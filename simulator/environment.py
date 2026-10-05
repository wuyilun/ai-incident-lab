"""Declarative topology: validated data, never executable scenario code."""

from pathlib import Path

from pydantic import Field, model_validator

from packages.contracts import Contract


class Service(Contract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    label: str
    kind: str
    tier: int = Field(default=0, ge=0, le=10)
    config: dict[str, str | int | float] = Field(default_factory=dict)
    metric_keys: list[str] = Field(default_factory=list)


class Dependency(Contract):
    from_: str = Field(alias="from")
    to: str
    kind: str = "dependency"
    label: str = "依赖"


class Environment(Contract):
    id: str
    name: str
    services: list[Service] = Field(min_length=1)
    dependencies: list[Dependency]

    @model_validator(mode="after")
    def valid_graph(self):
        names = {s.name for s in self.services}
        if len(names) != len(self.services):
            raise ValueError("Service names must be unique")
        if any(
            e.from_ not in names or e.to not in names or e.from_ == e.to for e in self.dependencies
        ):
            raise ValueError("Dependencies must join two existing distinct services")
        return self


def load_environment() -> Environment:
    return Environment.model_validate_json(
        (Path(__file__).parent / "environments" / "commerce.json").read_text()
    )
