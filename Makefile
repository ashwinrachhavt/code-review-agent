SHELL := /bin/bash

# Paths
BACKEND_DIR := backend
FRONTEND_DIR := frontend

# Binaries (override with `make VAR=value`)
PYTHON ?= python3
UVICORN ?= uvicorn

.PHONY: help install install-backend install-frontend lint lint-backend lint-frontend \
	format format-backend test test-backend run run-backend run-frontend pre-commit-install ci \
	run-redis run-worker health-celery

help:
	@echo "Common tasks:"
	@echo "  make install            # install backend (editable)"
	@echo "  make lint               # ruff + next lint (if pnpm present)"
	@echo "  make format             # ruff format backend"
	@echo "  make test               # pytest (backend)"
	@echo "  make run-backend        # start FastAPI with uvicorn"
	@echo "  make run-frontend       # start Next.js dev server (pnpm)"
	@echo "  make run-redis          # start Redis (docker)"
	@echo "  make run-worker         # start Celery worker (requires Redis)"
	@echo "  make health-celery      # check /health/celery endpoint"
	@echo "  make pre-commit-install # install pre-commit hooks for backend"
	@echo "  make ci                 # lint + tests (backend)"

install: install-backend

install-backend:
	$(PYTHON) -m pip install -e $(BACKEND_DIR)

install-frontend:
	@if [ -d $(FRONTEND_DIR) ]; then \
		if command -v pnpm >/dev/null 2>&1; then \
			cd $(FRONTEND_DIR) && pnpm install; \
		else \
			echo "pnpm not found, skipping frontend install"; \
		fi; \
	else \
		echo "$(FRONTEND_DIR) not found, skipping"; \
	fi

lint: lint-backend lint-frontend

lint-backend:
	$(PYTHON) -m ruff check $(BACKEND_DIR)

lint-frontend:
	@if [ -d $(FRONTEND_DIR) ]; then \
		if command -v pnpm >/dev/null 2>&1; then \
			cd $(FRONTEND_DIR) && pnpm lint; \
		else \
			echo "pnpm not found, skipping frontend lint"; \
		fi; \
	else \
		echo "$(FRONTEND_DIR) not found, skipping"; \
	fi

format: format-backend

format-backend:
	$(PYTHON) -m ruff format $(BACKEND_DIR)

test: test-backend

test-backend:
	cd $(BACKEND_DIR) && pytest

run: run-backend

run-backend:
	$(UVICORN) backend.main:app --reload

run-frontend:
	@if [ -d $(FRONTEND_DIR) ]; then \
		if command -v pnpm >/dev/null 2>&1; then \
			cd $(FRONTEND_DIR) && pnpm dev; \
		else \
			echo "pnpm not found, install from https://pnpm.io/"; \
		fi; \
	else \
		echo "$(FRONTEND_DIR) not found"; \
	fi

run-redis:
	@docker run --rm -p 6379:6379 --name code-review-redis redis:7-alpine

run-worker:
	celery -A backend.app.celery_app.celery_app worker -l info -Q celery -c 2

health-celery:
	@curl -s http://localhost:8000/health/celery | python -m json.tool

pre-commit-install:
	cd $(BACKEND_DIR) && pre-commit install

ci: lint-backend test-backend
