SHELL := /bin/bash

# Avoid .pyc/__pycache__ creation across all Python invocations
export PYTHONDONTWRITEBYTECODE=1

# Paths
BACKEND_DIR := backend
FRONTEND_DIR := frontend

# Binaries (override with `make VAR=value`)
PYTHON ?= python3
UVICORN ?= uvicorn

.PHONY: help install install-backend install-frontend lint lint-all lint-backend lint-frontend \
	format format-backend test test-backend run run-backend run-frontend pre-commit-install ci \
	clean clean-pyc clean-egg purge

help:
	@echo "Common tasks:"
	@echo "  make install            # install backend (editable)"
	@echo "  make lint-backend       # ruff (backend)"
	@echo "  make lint-frontend      # next lint (frontend)"
	@echo "  make lint-all           # backend + frontend lint"
	@echo "  make format             # ruff format backend"
	@echo "  make test               # pytest (backend)"
	@echo "  make run-backend        # start FastAPI with uvicorn"
	@echo "  make run-frontend       # start Next.js dev server (pnpm)"
	@echo "  make pre-commit-install # install pre-commit hooks for backend"
	@echo "  make ci                 # lint + tests (backend)"
	@echo "  make clean              # remove __pycache__, *.pyc, *.egg-info"

install: install-backend

install-backend:
	@if command -v uv >/dev/null 2>&1; then \
		cd $(BACKEND_DIR) && uv sync; \
	else \
		$(PYTHON) -m pip install -e $(BACKEND_DIR); \
	fi

# Optional: editable install (will create an egg-info directory). Avoid in CI.
install-backend-editable:
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install --system -e $(BACKEND_DIR); \
	else \
		$(PYTHON) -m pip install -e $(BACKEND_DIR); \
	fi

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

# Default lint runs backend only; use lint-all for both
lint: lint-backend

# Run both linters
lint-all: lint-backend lint-frontend

lint-backend:
	@if command -v uv >/dev/null 2>&1; then \
		uvx ruff check $(BACKEND_DIR) --config $(BACKEND_DIR)/pyproject.toml; \
	else \
		$(PYTHON) -m ruff check $(BACKEND_DIR) --config $(BACKEND_DIR)/pyproject.toml; \
	fi

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
	@if command -v uv >/dev/null 2>&1; then \
		uvx ruff format $(BACKEND_DIR) --config $(BACKEND_DIR)/pyproject.toml; \
	else \
		$(PYTHON) -m ruff format $(BACKEND_DIR) --config $(BACKEND_DIR)/pyproject.toml; \
	fi

test: test-backend

test-backend:
	@if command -v uv >/dev/null 2>&1; then \
		cd $(BACKEND_DIR) && uv sync && uv run pytest -c pyproject.toml; \
	else \
		$(PYTHON) -m pytest -c $(BACKEND_DIR)/pyproject.toml; \
	fi

run: run-backend

run-backend:
	@if command -v uv >/dev/null 2>&1; then \
		cd $(BACKEND_DIR) && PYTHONPATH=.. uv run uvicorn backend.main:app --reload; \
	else \
		PYTHONPATH=$(BACKEND_DIR) $(UVICORN) backend.main:app --reload; \
	fi

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

pre-commit-install:
	@if command -v uv >/dev/null 2>&1; then \
		uvx pre-commit install; \
	else \
		cd $(BACKEND_DIR) && pre-commit install; \
	fi

ci: lint-backend test-backend

# Cleaning helpers
clean: clean-pyc clean-egg

clean-pyc:
	@echo "Removing Python cache files and __pycache__ directories..."
	@find . -type f -name '*.py[co]' -delete || true
	@find . -type d -name '__pycache__' -prune -exec rm -rf {} + || true
	@find . -type d -name '.pytest_cache' -prune -exec rm -rf {} + || true
	@find . -type d -name '.ruff_cache' -prune -exec rm -rf {} + || true

clean-egg:
	@echo "Removing egg-info metadata directories..."
	@find . -type d -name '*.egg-info' -prune -exec rm -rf {} + || true

# Alias
purge: clean
