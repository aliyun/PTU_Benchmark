# ──────────────────────────────────────────────
# PTU Benchmark — Makefile
# ──────────────────────────────────────────────

.PHONY: help install install-dev setup test lint run run-all run-a run-b run-c run-d run-e compare poc clean

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

test:  ## Run unit tests
	python -m pytest tests/ -v

# ── Benchmark runs ─────────────────────────────────────────────

run:  ## Run all benchmark scenarios
	python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --export

run-all: run  ## Alias for 'run'

run-a:  ## Run Scenario A only (Single Request Baseline)
	python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --scenarios A

run-b:  ## Run Scenario B only (Concurrent Load)
	python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --scenarios B

run-c:  ## Run Scenario C only (Sustained Throughput)
	python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --scenarios C

run-d:  ## Run Scenario D only (Peak Burst)
	python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --scenarios D

run-e:  ## Run Scenario E only (Long Context)
	python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --scenarios E

list:  ## List available scenarios
	python -m ptu_benchmark --list

run-project: run  ## Alias for 'run'

project-test: run  ## Alias for 'run'

# ── A/B comparison ─────────────────────────────────────────────

# Override at the CLI:  make compare A=projects/ptu B=projects/token-api SCN="A B"
A ?= projects/qwen3.6-plus-2026-04-02_100K_10K
B ?= projects/token-api
SCN ?= A B

compare:  ## A/B compare two projects → 3 reports (A, B, compare). Vars: A, B, SCN
	python -m ptu_benchmark --project $(A) --compare-with $(B) --scenarios $(SCN)

poc: compare  ## Alias for 'compare' — single-shot POC A/B run

# ── Cleanup ────────────────────────────────────────────────────

clean:  ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned"
