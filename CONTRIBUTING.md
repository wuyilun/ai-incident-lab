# Contributing

Start with the [README](README.md), [architecture](ARCHITECTURE.md), and repository [engineering rules](AGENTS.md). Keep changes focused and explain the user-visible behavior they improve.

## Local setup

Run `make install`, copy `.env.example` to `.env`, and run `make dev`. Never put real credentials in examples, tests, screenshots, issues, or commits. Use synthetic values in tests and environment variables for local credentials.

Before submitting:

```sh
make test
make lint
# For browser or interaction changes:
cd apps/frontend && npm run test:e2e
```

For a local secret scan, install [Gitleaks](https://github.com/gitleaks/gitleaks), then run `gitleaks git --redact` and `gitleaks dir --redact` on a clean export of the files you intend to publish. CI scans Git history. Optional pre-commit integration is provided in `.pre-commit-config.yaml`; install pre-commit and run `pre-commit install` to enable it.

## Design boundaries

Agents access the environment through MCP, never simulator state or evaluation ground truth. Mutations pass through safety policy. Replay derives from persisted events. New scenarios need causal observations, a safe recovery path, and meaningful tests; see the [extension guide](docs/architecture/extending-environments.md).

In pull requests, describe the problem, resulting behavior, verification performed, and any limitations. Report vulnerabilities following [SECURITY.md](SECURITY.md).
