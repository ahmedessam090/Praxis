.DEFAULT_GOAL := help
COMPOSE := docker compose
UI_URL := http://localhost:8088

.PHONY: help install temporal-up temporal-down temporal-nuke worker ui api web dev \
        langfuse-up langfuse-down migrate makemigration golden test unit integration \
        smoke lint typecheck format clean
LANGFUSE_COMPOSE := docker/langfuse/docker-compose.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n", $$1, $$2}'

install: ## Pin Python 3.12, create venv, sync core+dev deps
	uv python pin 3.12
	uv sync --group dev

temporal-up: ## Start the Temporal stack (Postgres + server + UI)
	$(COMPOSE) up -d
	@echo "Temporal UI: $(UI_URL)   gRPC: localhost:7233"

temporal-down: ## Stop the stack (KEEP the data volume)
	$(COMPOSE) down

temporal-nuke: ## Stop the stack AND delete the persistence volume
	$(COMPOSE) down -v

worker: ## Run the Temporal worker (hosts workflows + activities)
	uv run python -m ta_assistant.temporal.worker

ui: ## (legacy) Run the old Streamlit UI — superseded by the Next.js app (make web)
	uv run streamlit run src/ta_assistant/presentation/app.py

api: ## Run the FastAPI service (the Next.js app's backend; needs temporal-up + a worker)
	uv run uvicorn ta_assistant.api.app:app --host 127.0.0.1 --port 8000 --reload

web: ## Run the Next.js frontend (needs `make api`)
	cd web && pnpm dev

langfuse-up: ## Start the self-hosted Langfuse stack (LLM usage + cost)
	$(COMPOSE) -f $(LANGFUSE_COMPOSE) up -d
	@echo "Langfuse UI: http://localhost:3001"

langfuse-down: ## Stop the Langfuse stack
	$(COMPOSE) -f $(LANGFUSE_COMPOSE) down

dev: ## Run worker + FastAPI + Next.js (Ctrl-C stops all; needs temporal-up)
	@echo "▶ worker + api + web — ensure 'make temporal-up' is running. Ctrl-C stops all."
	@trap 'kill 0' INT TERM EXIT; \
		uv run python -m ta_assistant.temporal.worker & \
		uv run uvicorn ta_assistant.api.app:app --host 127.0.0.1 --port 8000 & \
		(cd web && pnpm dev) & \
		wait

migrate: ## Apply DB migrations to head (creates data/ta.db)
	uv run alembic upgrade head

makemigration: ## Autogenerate a migration: make makemigration m="add patterns"
	uv run alembic revision --autogenerate -m "$(m)"

golden: ## Regenerate the golden workflow history for the replay test
	uv run python scripts/gen_golden_history.py

test: unit integration ## Run unit + integration tests (no Docker needed)

unit: ## Run unit tests (in-process; spins its own test server)
	uv run pytest -m "not integration"

integration: ## Run integration tests (worker-crash recovery + e2e via local dev server)
	uv run pytest -m integration

smoke: ## End-to-end check vs the running Docker stack (needs temporal-up + a worker)
	uv run python scripts/smoke.py

lint: ## Ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Ruff auto-format + fix
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## mypy (strict) on the package
	uv run mypy src

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache
