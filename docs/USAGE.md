# Usage Guide

> CLI reference, environment configuration, and tuning parameters for the PTU Benchmark Suite.

---

## Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [CLI Reference](#cli-reference)
4. [Environment Variables](#environment-variables)
5. [Running Benchmarks](#running-benchmarks)
6. [Exporting Results](#exporting-results)
7. [Comparing Token API vs PTU](#comparing-token-api-vs-ptu)
8. [Troubleshooting](#troubleshooting)

---

## Installation

### From Source (Recommended)

```bash
git clone <repo-url> PTU-Benchmark
cd PTU-Benchmark

python3 -m venv .venv
source .venv/bin/activate

# Production install
pip install -e .

# Or with dev dependencies (includes pytest)
pip install -e ".[dev]"
```

### Using Make

```bash
make install       # production only
make install-dev   # includes pytest
make setup         # creates .env from template
```

---

## Configuration

All configuration is driven by environment variables, loaded from a `.env` file.

### Creating Your `.env` File

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DASHSCOPE_API_KEY` | Model Studio API key from Alibaba Cloud console | `sk-abc123...` |
| `PTU_MODEL_ID` | Model ID of your active PTU deployment | `qwen3.6-plus-2026-04-02` |
| `BASE_URL` | API endpoint URL | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

### Optional Tuning Variables

| Variable | Default | Applies To | Description |
|----------|---------|------------|-------------|
| `CONCURRENCY_LEVELS` | `10,50,100` | Scenario B | Comma-separated list of concurrency levels to test |
| `SUSTAINED_DURATION` | `1800` | Scenario C | Duration of sustained test in seconds (1800 = 30 min) |
| `SUSTAINED_CONCURRENCY` | `20` | Scenario C | Number of parallel workers during sustained test |
| `BURST_SIZE` | `200` | Scenario D | Number of simultaneous requests in the burst |
| `CONTEXT_SIZES` | `32000,64000,128000` | Scenario E | Comma-separated token counts for long-context tests |

### Example `.env`

```ini
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxx
PTU_MODEL_ID=qwen3.6-plus-2026-04-02
BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1

CONCURRENCY_LEVELS=10,50,100
SUSTAINED_DURATION=1800
SUSTAINED_CONCURRENCY=20
BURST_SIZE=200
CONTEXT_SIZES=32000,64000,128000
```

---

## CLI Reference

```
ptu-benchmark [options]
```

or equivalently:

```
python -m ptu_benchmark [options]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--version` | — | — | Print version and exit |
| `--env PATH` | string | auto-detect | Path to a `.env` file |
| `--scenarios KEYS...` | list | all (A B C D E) | Space-separated scenario keys to run |
| `--list` | — | — | Print available scenarios and exit |
| `--export` | — | off | Export results to JSON + CSV in `results/` |
| `--output-dir DIR` | string | `results` | Directory for exported files |

---

## Environment Variables

Below is the full list of environment variables recognised by the tool, grouped by category.

### Connection

| Variable | Required | Default |
|----------|----------|---------|
| `DASHSCOPE_API_KEY` | Yes | — |
| `PTU_MODEL_ID` | Yes | — |
| `BASE_URL` | No | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

### Scenario Tuning

| Variable | Required | Default | Used By |
|----------|----------|---------|---------|
| `CONCURRENCY_LEVELS` | No | `10,50,100` | B |
| `SUSTAINED_DURATION` | No | `1800` | C |
| `SUSTAINED_CONCURRENCY` | No | `20` | C |
| `BURST_SIZE` | No | `200` | D |
| `CONTEXT_SIZES` | No | `32000,64000,128000` | E |

---

## Running Benchmarks

### Run Everything

```bash
python -m ptu_benchmark --export
```

Runs scenarios A through E sequentially and writes JSON + CSV results to `results/`.

### Run Specific Scenarios

```bash
# Single scenario
python -m ptu_benchmark --scenarios A

# Multiple scenarios
python -m ptu_benchmark --scenarios A B D

# Quick POC set (skip the 30-min sustained test)
python -m ptu_benchmark --scenarios A B D --export
```

### Using a Custom `.env` File

```bash
python -m ptu_benchmark --env /path/to/customer-poc.env --scenarios A B
```

### Using Make Shortcuts

```bash
make run          # all scenarios + export
make run-a        # Scenario A
make run-b        # Scenario B
make run-c        # Scenario C
make run-d        # Scenario D
make run-e        # Scenario E
make list         # show available scenarios
```

---

## Exporting Results

When `--export` is passed, two files are created in `results/`:

### JSON Export

**File:** `results/benchmark_results_<timestamp>.json`

Contains every individual request result with full timing data:

```json
{
  "timestamp": "2026-06-05T10:30:00+00:00",
  "scenarios": [
    {
      "scenario": "A",
      "label": "Single Request Baseline (TTFT + TPS)",
      "total_requests": 8,
      "successful": 8,
      "failed": 0,
      "rate_limited": 0,
      "results": [
        {
          "request_id": 0,
          "ttft_ms": 312.5,
          "tps": 62.4,
          "tokens": 195,
          "total_seconds": 3.41,
          "error": null
        }
      ]
    }
  ]
}
```

### CSV Summary

**File:** `results/benchmark_summary.csv`

One row per scenario with aggregated statistics:

```csv
scenario,label,total,success,errors,rate_limited,ttft_p50_ms,ttft_p95_ms,ttft_p99_ms,tps_avg,tps_min,tps_max
A,Single Request Baseline (TTFT + TPS),8,8,0,0,305,340,355,63.2,58.7,67.1
B,Concurrent Load (10/50/100 parallel requests),160,158,2,0,420,890,1200,55.3,32.1,68.4
```

---

## Comparing Token API vs PTU

To produce a side-by-side comparison, run the benchmark suite twice — once against the Token API and once against the PTU endpoint — then compare the exported CSV files.

### Step-by-Step

```bash
# 1. Run against Token API (standard model, no PTU)
DASHSCOPE_API_KEY=sk-xxx \
PTU_MODEL_ID=qwen3.6-plus-2026-04-02 \
python -m ptu_benchmark --scenarios A B --export --output-dir results/token-api

# 2. Run against PTU deployment
DASHSCOPE_API_KEY=sk-xxx \
PTU_MODEL_ID=your-ptu-model-id \
python -m ptu_benchmark --scenarios A B --export --output-dir results/ptu

# 3. Compare the two CSV files
diff results/token-api/benchmark_summary.csv results/ptu/benchmark_summary.csv
```

### Key Metrics to Compare

| Metric | Where to Find It |
|--------|------------------|
| TTFT P50 / P99 | CSV columns `ttft_p50_ms`, `ttft_p99_ms` |
| Average TPS | CSV column `tps_avg` |
| Max concurrency without 429s | Scenario B `rate_limited` column |
| Sustained TPM | Scenario C JSON total tokens / duration |

---

## Troubleshooting

### "DASHSCOPE_API_KEY is not set"

The `.env` file is missing or not being loaded. Check:

```bash
# Verify .env exists and has the key
cat .env | grep DASHSCOPE_API_KEY

# Or pass it explicitly
python -m ptu_benchmark --env /full/path/to/.env
```

### "PTU_MODEL_ID is not set"

Same as above — ensure `PTU_MODEL_ID` is in your `.env`.

### HTTP 429 Errors on All Requests

The PTU deployment may not be active, or the model ID is incorrect. Verify in the Model Studio console that:
1. The PTU deployment shows status **Active**
2. The model ID in `.env` matches exactly what the console shows

### High TTFT (>2000ms) on Scenario A

This is unusual for PTU. Possible causes:
- Network distance to the endpoint (check `BASE_URL` region)
- Cold start on a freshly provisioned PTU (run a warm-up request first)
- Incorrect model ID routing to shared pool instead of PTU

### Scenario C Runs Forever

The default duration is 30 minutes. To shorten for testing:

```ini
SUSTAINED_DURATION=120
```

Or override via environment:

```bash
SUSTAINED_DURATION=120 python -m ptu_benchmark --scenarios C
```

### ImportError: No module named 'ptu_benchmark'

The package is not installed. Run:

```bash
pip install -e .
```
