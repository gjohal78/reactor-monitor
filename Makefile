.DEFAULT_GOAL := help
.PHONY: help up down logs migrate install test test-backend test-frontend lint lint-backend lint-frontend format

BACKEND  := backend
FRONTEND := frontend
VENV     := $(BACKEND)/.venv
PY       := $(VENV)/bin
VENV_STAMP := $(VENV)/.installed

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# --- Docker -----------------------------------------------------------------
up: ## Build and start postgres, backend and frontend
	docker compose up --build -d
	@echo "Frontend: http://localhost:5173  API docs: http://localhost:8000/docs"

down: ## Stop all services
	docker compose down

logs: ## Tail service logs
	docker compose logs -f

migrate: $(VENV_STAMP) ## Apply database migrations to DATABASE_URL
	cd $(BACKEND) && .venv/bin/alembic upgrade head

# --- Local toolchain --------------------------------------------------------
# Re-run pip whenever pyproject.toml changes (e.g. a new dependency), not just on first use.
$(VENV_STAMP): $(BACKEND)/pyproject.toml
	test -d $(VENV) || python3.12 -m venv $(VENV)
	$(PY)/pip install -e "$(BACKEND)[dev]"
	@touch $@

# Track npm's own marker file, not the node_modules/ directory: docker compose leaves an
# empty frontend/node_modules/ on the host (the container's node_modules volume mount point).
$(FRONTEND)/node_modules/.package-lock.json: $(FRONTEND)/package-lock.json
	cd $(FRONTEND) && npm ci
	@touch $@

install: $(VENV_STAMP) $(FRONTEND)/node_modules/.package-lock.json ## Install backend venv and frontend deps

# --- Quality ----------------------------------------------------------------
test: test-backend test-frontend ## Run all tests

test-backend: $(VENV_STAMP)
	cd $(BACKEND) && .venv/bin/pytest

test-frontend: $(FRONTEND)/node_modules/.package-lock.json
	cd $(FRONTEND) && npm test

lint: lint-backend lint-frontend ## Run ruff, mypy, eslint and tsc

lint-backend: $(VENV_STAMP)
	cd $(BACKEND) && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy

lint-frontend: $(FRONTEND)/node_modules/.package-lock.json
	cd $(FRONTEND) && npm run lint && npm run typecheck

format: $(VENV_STAMP) ## Auto-fix and format Python code
	cd $(BACKEND) && .venv/bin/ruff check --fix . && .venv/bin/ruff format .
