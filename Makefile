.DEFAULT_GOAL := help
.PHONY: help up down logs install test test-backend test-frontend lint lint-backend lint-frontend format

BACKEND  := backend
FRONTEND := frontend
VENV     := $(BACKEND)/.venv
PY       := $(VENV)/bin

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

# --- Local toolchain --------------------------------------------------------
$(VENV):
	python3.12 -m venv $(VENV)
	$(PY)/pip install -e "$(BACKEND)[dev]"

$(FRONTEND)/node_modules: $(FRONTEND)/package-lock.json
	cd $(FRONTEND) && npm ci
	@touch $@

install: $(VENV) $(FRONTEND)/node_modules ## Install backend venv and frontend deps

# --- Quality ----------------------------------------------------------------
test: test-backend test-frontend ## Run all tests

test-backend: $(VENV)
	cd $(BACKEND) && .venv/bin/pytest

test-frontend: $(FRONTEND)/node_modules
	cd $(FRONTEND) && npm test

lint: lint-backend lint-frontend ## Run ruff, mypy, eslint and tsc

lint-backend: $(VENV)
	cd $(BACKEND) && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy

lint-frontend: $(FRONTEND)/node_modules
	cd $(FRONTEND) && npm run lint && npm run typecheck

format: $(VENV) ## Auto-fix and format Python code
	cd $(BACKEND) && .venv/bin/ruff check --fix . && .venv/bin/ruff format .
