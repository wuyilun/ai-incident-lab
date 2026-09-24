.PHONY: install dev test lint e2e scenario benchmark
SCENARIO ?= redis-connection-leak
install:
	uv sync --frozen
	npm ci --prefix apps/frontend
dev:
	uv run python scripts/dev.py
test:
	uv run pytest -q
lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages simulator evaluator apps lab_mcp
	npm run lint --prefix apps/frontend
	npm run build --prefix apps/frontend
e2e:
	uv run pytest tests/test_integration.py -q
	cd apps/frontend && npm run test:e2e
scenario:
	uv run python scripts/cli.py inject --scenario $(SCENARIO)
benchmark:
	uv run python scripts/cli.py benchmark --scenario $(SCENARIO) --trials 3
