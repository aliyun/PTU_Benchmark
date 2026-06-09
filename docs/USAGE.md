# Usage Guide

> CLI reference, environment configuration, and tuning parameters for the PTU Benchmark Suite.

---

## Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Project Configuration](#project-configuration)
4. [CLI Reference](#cli-reference)
5. [Environment Variables](#environment-variables)
6. [Running Benchmarks](#running-benchmarks)
7. [Result Output & Reports](#result-output--reports)
8. [Comparing Token API vs PTU](#comparing-token-api-vs-ptu)
9. [Troubleshooting](#troubleshooting)

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

The tool supports two configuration modes:

1. **Project mode** (recommended) — per-use-case folder with `project.yaml` + `.env`
2. **Legacy mode** — flat `.env` file at the repository root

### Project Mode (Recommended)

Each benchmark target (PTU deployment, Token API baseline) gets its own project folder:

```bash
# Copy the template
cp -r projects/template projects/my-ptu

# Edit project.yaml with deployment details
# Edit .env with API credentials
```

### Legacy Mode

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```ini
# Required
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxx
PTU_MODEL_ID=your-ptu-deployment-model-id
BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1

# Optional tuning (uncomment to customise)
# CONCURRENCY_LEVELS=10,50,100
# SUSTAINED_DURATION=1800
# SUSTAINED_CONCURRENCY=20
# BURST_SIZE=200
# CONTEXT_SIZES=32000,64000,128000
```

---

## Project Configuration

### project.yaml

Each project folder contains a `project.yaml` with deployment metadata:

| Field | Description | Example |
|-------|-------------|---------|
| `service_name` | Human-readable label | `"Qwen3.6 PTU 100K"` |
| `model_name` | Display name | `"Qwen3.6-Plus-2026-04-02"` |
| `model_code` | API identifier (used as `PTU_MODEL_ID`) | `"qwen3.6-plus-2026-04-02"` |
| `deployment_id` | Unique deployment ID | `"qwen3.6-plus-2026-04-02-d18396"` |
| `billing_method` | Billing type | `"PTU / Pay-as-you-go"` |
| `input_tpm` | Input token quota | `100000` |
| `output_tpm` | Output token quota | `10000` |
| `input_unit_price` | USD per kTPM*hour (input) | `0.12` |
| `output_unit_price` | USD per kTPM*hour (output) | `0.72` |
| `hourly_price` | Total USD per hour | `19.20` |

### Benchmark Tuning in project.yaml

Scenario parameters can also be set in `project.yaml` (overrides `.env`):

```yaml
concurrency_levels:           # OPTIONAL — see "Auto-derived concurrency" below
  - 10
  - 50
  - 100
# tps_estimate: 150           # optional; tunes the auto-derive heuristic

sustained_duration: 1800       # seconds
sustained_concurrency: 20
burst_size: 200

context_sizes:
  "32K":  32000
  "64K":  64000
  "128K": 128000
```

#### Auto-derived concurrency levels

If `concurrency_levels` is **omitted** from `project.yaml` and the project
defines `output_tpm`, the suite automatically derives a quota-aligned 3-point
sweep:

```
capacity ≈ output_tpm / (tps_estimate * 60)
levels   = [½·capacity, capacity, 2·capacity]    # under-load, at-capacity, stress
```

| `output_tpm` | Auto-derived levels (default `tps_estimate=150`) |
|--------------|--------------------------------------------------|
| 10,000       | `[1, 2]`                                         |
| 50,000       | `[3, 6, 12]`                                     |
| 100,000      | `[5, 11, 22]`                                    |
| 500,000      | `[28, 56, 112]`                                  |
| 1,000,000    | `[55, 111, 222]`                                 |

A console note is printed at startup when this happens, e.g.:

```
Note: concurrency_levels not set in project.yaml; auto-derived from
output_tpm=10,000 @ ~150 TPS → [1, 2]
```

Override the heuristic by setting `tps_estimate:` in `project.yaml`
(e.g. `200` for blazing-fast PTU deployments, `80` for slower /
quantised models) or by providing an explicit `concurrency_levels`
list, which always takes precedence.

**If you see 429 throttling at the top concurrency level**, your
`tps_estimate` is set lower than the model's actual per-request TPS.
Run Scenario A first to measure observed TPS, then pin `tps_estimate`
to that value (or slightly above) so the auto-derived sweep stays
inside the TPM quota.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DASHSCOPE_API_KEY` | Model Studio API key from Alibaba Cloud console | `sk-abc123...` |
| `PTU_MODEL_ID` | Model ID of your active PTU deployment | `qwen3.6-plus-2026-04-02` |
| `BASE_URL` | API endpoint URL | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

### Optional Tuning Variables

| Variable | Default | Applies To | Description |
|----------|---------|------------|-------------|
| `CONCURRENCY_LEVELS` | `10,50,100` (or auto-derived from `output_tpm` in project mode) | Scenario B | Comma-separated list of concurrency levels to test |
| `SUSTAINED_DURATION` | `1800` | Scenario C | Duration of sustained test in seconds (1800 = 30 min) |
| `SUSTAINED_CONCURRENCY` | `20` | Scenario C | Number of parallel workers during sustained test |
| `BURST_SIZE` | `200` | Scenario D | Number of simultaneous requests in the burst |
| `CONTEXT_SIZES` | `32000,64000,128000` | Scenario E | Comma-separated token counts for long-context tests |

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
| `--project PATH` | string | — | Project folder containing `project.yaml` (recommended) |
| `--env PATH` | string | auto-detect | Path to a `.env` file (legacy mode) |
| `--compare-with PATH` | string | — | Second project folder for A/B comparison |
| `--scenarios KEYS...` | list | all (A B C D E) | Space-separated scenario keys to run |
| `--list` | — | — | Print available scenarios and exit |
| `--export` | — | always on | Export results (implicit in project mode) |
| `--output-dir DIR` | string | auto-named | Directory for exported files |

### Output Directory Naming

When `--output-dir` is not specified, results are written to a **dated, auto-incremented folder**:

```
{base}/results/{YYYYMMDD}_{model_name}_{NNN}/results/
```

- `YYYYMMDD` — current UTC date
- `model_name` — from `project.yaml` or `PTU_MODEL_ID`
- `NNN` — 3-digit sequence number (auto-increments if folder exists)

Example: `results/20260605_Qwen3.6-Plus-2026-04-02_001/results/`

For A/B comparisons: `results/20260605_ModelA_vs_ModelB_001/results/`

---

## Environment Variables

Below is the full list of environment variables recognised by the tool, grouped by category.

### Connection

| Variable | Required | Default |
|----------|----------|---------|
| `DASHSCOPE_API_KEY` | Yes | — |
| `PTU_MODEL_ID` | Yes (or set in `project.yaml` `model_code`) | — |
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

### Project Mode (Recommended)

```bash
# Run all scenarios — reports auto-generated
python -m ptu_benchmark --project projects/my-ptu

# Run specific scenarios
python -m ptu_benchmark --project projects/my-ptu --scenarios A B D

# Quick POC set (skip the 30-min sustained test)
python -m ptu_benchmark --project projects/my-ptu --scenarios A B D
```

### Legacy Mode (.env only)

```bash
python -m ptu_benchmark --env /path/to/.env --scenarios A B --export
```

### Using Make Shortcuts

```bash
make run          # all scenarios (reports auto-generated)
make run-a        # Scenario A
make run-b        # Scenario B
make run-c        # Scenario C
make run-d        # Scenario D
make run-e        # Scenario E
make compare      # A/B comparison (PTU vs Token API)
make list         # show available scenarios
```

---

## Result Output & Reports

Every benchmark run produces a **dated result bundle** containing four types of output:

### Folder Structure

```
results/
  20260605_Qwen3.6-Plus-2026-04-02_001/
    results/
      benchmark_results_20260605T120000Z.json
      benchmark_summary.csv
      executive_report.md
      figures/
        ttft_percentiles.png
        tps_throughput.png
        error_rates.png
      business_report.docx
```

### Files

| File | Format | Audience | Description |
|------|--------|----------|-------------|
| `benchmark_results_*.json` | JSON | Engineers | Full per-request timing data for every scenario |
| `benchmark_summary.csv` | CSV | Analysts | Aggregated statistics (P50/P95/P99, TPS, error rates) |
| `executive_report.md` | Markdown + PNG | Technical teams | Deep technical report with per-scenario breakdowns, statistical tables, matplotlib charts (TTFT percentiles, TPS throughput, error rates), comparison deltas, and auto-generated findings |
| `figures/*.png` | PNG images | Both | Matplotlib-generated charts embedded in the executive report |
| `business_report.docx` | DOCX (Word) | Decision makers | Professional one-page summary with headline metrics, explanations of what each metric means, scenario overview, key takeaways, and cost |

### JSON Export

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

One row per scenario with aggregated statistics:

```csv
scenario,label,total,success,errors,rate_limited,ttft_p50_ms,ttft_p95_ms,ttft_p99_ms,tps_avg,tps_min,tps_max
A,Single Request Baseline (TTFT + TPS),8,8,0,0,305,340,355,63.2,58.7,67.1
B,Concurrent Load (10/50/100 parallel requests),160,158,2,0,420,890,1200,55.3,32.1,68.4
```

### Executive Report

The deep technical report (`executive_report.md`) includes:

- **Summary table** — all scenarios at a glance with key metrics
- **Performance overview charts** — matplotlib-generated TTFT percentile bars, TPS throughput with error bars, and request outcome breakdowns
- **Per-scenario details** — TTFT percentile tables (P50/P90/P95/P99/min/max), throughput statistics (avg/median/min/max/std dev), token counts
- **Comparison analysis** — side-by-side deltas and comparison charts when comparing two projects
- **Key findings** — auto-generated observations from the data

### Business Report

The one-page business report (`business_report.docx`) is a professionally formatted Word document:

- **Headline metrics** — TTFT, TPS, TPM, success rate, each with a plain-English explanation of what it means
- **Scenario overview** — compact table of all scenarios with brief context
- **Comparison table** — when A/B comparing two projects, with delta percentages
- **Key takeaways** — reliability, rate limiting, performance, vs-baseline — with explanations
- **Cost summary** — hourly/daily/monthly pricing (from `project.yaml`)

---

## Comparing Token API vs PTU

### A/B Compare Mode (Recommended)

Run the same scenarios against two projects and get side-by-side reports:

```bash
python -m ptu_benchmark \
  --project projects/my-ptu \
  --compare-with projects/token-api \
  --scenarios A B D
```

This produces a dated comparison bundle under the subject model's code:

```
results/
  20260605_PtuModel_vs_TokenApi_001/
    results/
      model-code/                              ← model report folder
        executive_report.md                    ← ⭐ flagship A/B comparison
        business_report.docx                   ← ⭐ DOCX twin
        metrics.csv                            ← side-by-side numbers
        subject_only_executive_report.md       ← PTU-only deep dive
        subject_only_business_report.docx      ← PTU-only DOCX
        figures/
          comparison_vs_ttft_tps.png           ← side-by-side comparison charts
        my-ptu/                                ← subject raw data
        token-api/                             ← baseline raw data
```

Or using Make:

```bash
# Override projects at the command line
make compare A=projects/my-ptu B=projects/token-api SCN="A B D"
```

### Key Metrics to Compare

| Metric | Where to Find It |
|--------|------------------|
| TTFT P50 / P99 | CSV columns, executive report comparison table |
| Average TPS | CSV column, business report overview |
| Max concurrency without 429s | Scenario B `rate_limited` column |
| Sustained TPM | Scenario C JSON total tokens / duration |
| Δ (improvement %) | Comparison reports delta column |

---

## Troubleshooting

### "DASHSCOPE_API_KEY is not set"

The `.env` file is missing or not being loaded. Check:

```bash
# Verify .env exists in the project folder
cat projects/my-ptu/.env | grep DASHSCOPE_API_KEY

# Or pass it explicitly
python -m ptu_benchmark --env /full/path/to/.env
```

### "PTU_MODEL_ID is not set"

Ensure `model_code` is set in `project.yaml`, or `PTU_MODEL_ID` is in your `.env`.

### HTTP 429 Errors on All Requests

The PTU deployment may not be active, or the model ID is incorrect. Verify in the Model Studio console that:
1. The PTU deployment shows status **Active**
2. The model ID matches exactly what the console shows

### High TTFT (>2000ms) on Scenario A

This is unusual for PTU. Possible causes:
- Network distance to the endpoint (check `BASE_URL` region)
- Cold start on a freshly provisioned PTU (run a warm-up request first)
- Incorrect model ID routing to shared pool instead of PTU

### Scenario C Runs Forever

The default duration is 30 minutes. To shorten for testing:

```yaml
# In project.yaml
sustained_duration: 120
```

Or override via environment:

```bash
SUSTAINED_DURATION=120 python -m ptu_benchmark --project projects/my-ptu --scenarios C
```

### ImportError: No module named 'ptu_benchmark'

The package is not installed. Run:

```bash
pip install -e .
```

### Results Folder Keeps Growing

Each run creates a new dated folder with an auto-incrementing sequence number. Old runs are never overwritten. To clean up:

```bash
# Remove all results older than 30 days
find results/ -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
```
