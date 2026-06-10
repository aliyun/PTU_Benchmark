# ──────────────────────────────────────────────
# PTU Benchmark — Makefile
# ──────────────────────────────────────────────

.PHONY: help install install-dev setup test test-integration lint format typecheck run run-all run-a run-b run-c run-d run-e compare poc clean

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────

install:  ## Install production dependencies
	pip install -r requirements.txt

install-dev:  ## Install development dependencies
	pip install -r requirements.txt
	pip install pytest pytest-asyncio

setup:  ## Copy .env.example to .env (if .env doesn't exist)
	@test -f .env || cp .env.example .env
	@echo ".env file ready — edit it with your API key and model ID"

# ── Testing ────────────────────────────────────────────────────

test:  ## Run unit tests (excludes integration tests)
	python -m pytest tests/ -v -m "not integration"

test-integration:  ## Run integration tests
	python -m pytest tests/ -m integration -v

# ── Benchmark runs ─────────────────────────────────────────────
# Override at the command line:
#   make run P=projects/my-ptu B=projects/token-api SCN="A B D"
#   make run-a P=projects/my-ptu
#
# All targets run with A/B comparison by default (PTU vs Token API).
# Use --no-compare in the CLI directly if you need a single-project run.

P ?= projects/qwen3.6-plus-2026-04-02_500K_100K
B ?= projects/token-api
SCN ?= A B C D E

run:  ## Run all scenarios with A/B comparison. Vars: P, B, SCN
	python -m ptu_benchmark --project $(P) --compare-with $(B) --scenarios $(SCN)

run-all: run  ## Alias for 'run'

run-a:  ## Run Scenario A only (with compare). Vars: P, B
	python -m ptu_benchmark --project $(P) --compare-with $(B) --scenarios A

run-b:  ## Run Scenario B only (with compare). Vars: P, B
	python -m ptu_benchmark --project $(P) --compare-with $(B) --scenarios B

run-c:  ## Run Scenario C only (with compare). Vars: P, B
	python -m ptu_benchmark --project $(P) --compare-with $(B) --scenarios C

run-d:  ## Run Scenario D only (with compare). Vars: P, B
	python -m ptu_benchmark --project $(P) --compare-with $(B) --scenarios D

run-e:  ## Run Scenario E only (with compare). Vars: P, B
	python -m ptu_benchmark --project $(P) --compare-with $(B) --scenarios E

list:  ## List available scenarios
	python -m ptu_benchmark --list

# ── Aliases ───────────────────────────────────────────────────

compare: run  ## Alias for 'run' (A/B comparison)
poc: run      ## Alias for 'run' — single-shot POC A/B run

# ── Code Quality ──────────────────────────────────────────────

lint:  ## Run ruff linter
	ruff check src/ tests/

format:  ## Format code with ruff
	ruff format src/ tests/

typecheck:  ## Run mypy type checking
	mypy src/ptu_benchmark/

# ── Cleanup ────────────────────────────────────────────────────

clean:  ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned"
