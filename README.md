# PTU Benchmark Suite

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

> Performance benchmarking toolkit for **Alibaba Cloud Model Studio PTU** (Provisioned Throughput Unit) — designed for customer POCs and sales engagements.

---

## Purpose

This tool provides a structured, repeatable way to demonstrate PTU performance advantages over the shared Token API during customer evaluations. It measures the metrics customers care about most:

| Metric | What It Tells the Customer |
|--------|--------------------------|
| **TTFT** (Time To First Token) | How fast the first word appears — perceived responsiveness |
| **TPS** (Tokens Per Second) | Generation speed — how fast the full response is delivered |
| **Concurrent throughput** | How many users can be served simultaneously without degradation |
| **Sustained TPM** | Whether guaranteed throughput holds over time (not just bursts) |
| **429 error rate** | Whether traffic spikes cause service interruptions |

---

## Project Structure

```
PTU-Benchmark/
├── src/ptu_benchmark/          # Core package
│   ├── __main__.py             # CLI entry point
│   ├── config.py               # Environment & configuration loader
│   ├── utils.py                # Prompts, data classes, helpers
│   ├── reporter.py             # Console output, JSON/CSV export
│   └── scenarios/              # One module per benchmark scenario
│       ├── base.py             # Shared async streaming infrastructure
│       ├── scenario_a.py       # A — Single Request Baseline
│       ├── scenario_b.py       # B — Concurrent Load (10/50/100)
│       ├── scenario_c.py       # C — Sustained Throughput (30 min)
│       ├── scenario_d.py       # D — Peak Burst Test
│       └── scenario_e.py       # E — Long Context (32K–128K)
├── tests/                      # Unit tests
├── results/                    # Exported JSON/CSV benchmark results
├── docs/                       # Extended documentation
│   ├── USAGE.md                # CLI reference & configuration guide
│   ├── SCENARIOS.md            # Detailed scenario descriptions
│   └── CUSTOMER_REPORT.md      # Customer-facing POC report template
├── benchmark-prompt.md         # Original reference prompts (standalone scripts)
├── pyproject.toml              # Python packaging configuration
├── requirements.txt            # Pinned dependencies
├── Makefile                    # Convenience commands
├── .env.example                # Configuration template
└── .gitignore
```

---

## Quick Start

### 1. Prerequisites

- **Python 3.9+**
- An active **Model Studio API Key** (from Alibaba Cloud console)
- A **PTU deployment** with a model endpoint ready

### 2. Installation

```bash
# Clone the repository
git clone <repo-url> PTU-Benchmark
cd PTU-Benchmark

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package (editable mode) + dev dependencies
pip install -e ".[dev]"
```

Or using Make:

```bash
make install-dev
```

### 3. Configuration

```bash
# Copy the template
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

### 4. Run Benchmarks

```bash
# List available scenarios
python -m ptu_benchmark --list

# Run all scenarios and export results
python -m ptu_benchmark --export

# Run specific scenarios
python -m ptu_benchmark --scenarios A B D

# Or use Make shortcuts
make run          # all + export
make run-a        # Scenario A only
make run-b        # Scenario B only
```

---

## Benchmark Scenarios at a Glance

| Scenario | Name | What It Measures | Duration |
|----------|------|------------------|----------|
| **A** | Single Request Baseline | TTFT and TPS with zero contention | ~2 min |
| **B** | Concurrent Load | Performance at 10 / 50 / 100 parallel requests | ~5 min |
| **C** | Sustained Throughput | Max TPM maintained over 30 minutes | 30 min |
| **D** | Peak Burst | Behaviour under sudden traffic spike (200 req) | ~2 min |
| **E** | Long Context | TTFT/TPS with 32K, 64K, 128K token inputs | ~5 min |

See [docs/SCENARIOS.md](docs/SCENARIOS.md) for a deep-dive into each scenario.

---

## CLI Reference

```
usage: ptu-benchmark [-h] [--version] [--env ENV]
                     [--scenarios {A,B,C,D,E} ...]
                     [--list] [--export]
                     [--output-dir OUTPUT_DIR]

options:
  --version              Show version and exit
  --env ENV              Path to a .env file (default: auto-detect)
  --scenarios A B D      Run specific scenarios (default: all)
  --list                 List available scenarios and exit
  --export               Save results to JSON + CSV in results/
  --output-dir DIR       Directory for exports (default: results/)
```

See [docs/USAGE.md](docs/USAGE.md) for full configuration details.

---

## Example Output

```
============================================================
  PTU Benchmark Suite v1.0.0
============================================================
  Model:    qwen3.6-plus-2026-04-02
  Base URL: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
  Running:  A, B, C, D, E

------------------------------------------------------------
  Scenario A: Single Request Baseline (TTFT + TPS)
------------------------------------------------------------
--- Short prompt (5 runs) ---
[Short Run 1] TTFT: 312ms | TPS: 62.4 | Total: 3.41s | Tokens: 195
[Short Run 2] TTFT: 298ms | TPS: 64.1 | Total: 3.28s | Tokens: 190
...

============================================================
  Scenario A: Single Request Baseline (TTFT + TPS)
============================================================
  Total: 8 | Success: 8 | Errors: 0 | 429s: 0
  TTFT  → P50: 305ms | P95: 340ms | P99: 355ms
  TPS   → Avg: 63.2 | Min: 58.7 | Max: 67.1
  Est. TPM: 11,376
```

---

## Exporting Results

Add `--export` to any run to save results automatically:

```bash
python -m ptu_benchmark --export
```

Two files are written to `results/`:

| File | Format | Contents |
|------|--------|----------|
| `benchmark_results_<timestamp>.json` | JSON | Full per-request data for every scenario |
| `benchmark_summary.csv` | CSV | Aggregated statistics (P50/P95/P99, TPS, error rates) |

These files feed directly into the customer report template at [docs/CUSTOMER_REPORT.md](docs/CUSTOMER_REPORT.md).

---

## Running Tests

```bash
make test
# or
python -m pytest tests/ -v
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/USAGE.md](docs/USAGE.md) | CLI reference, environment variables, configuration tuning |
| [docs/SCENARIOS.md](docs/SCENARIOS.md) | Detailed description of each scenario, expected results, tuning tips |
| [docs/CUSTOMER_REPORT.md](docs/CUSTOMER_REPORT.md) | Fill-in-the-blank POC report template for customer delivery |
| [benchmark-prompt.md](benchmark-prompt.md) | Original standalone Python scripts (reference) |

---

## Typical POC Workflow

```
1. Deploy PTU endpoint on Model Studio console
          │
2. Configure .env with API key + model ID
          │
3. Run Scenario A on Token API  ──►  baseline numbers
          │
4. Run Scenario A on PTU        ──►  PTU numbers
          │
5. Run Scenarios B–E on PTU     ──►  stress-test results
          │
6. Export results (--export)    ──►  JSON + CSV
          │
7. Fill in Customer Report      ──►  docs/CUSTOMER_REPORT.md
          │
8. Deliver POC report to customer
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `openai` | Streaming chat completions via OpenAI-compatible API |
| `aiohttp` | Async HTTP for concurrent and sustained load tests |
| `numpy` | Statistical aggregations (percentiles, mean) |
| `python-dotenv` | Load configuration from `.env` files |
| `tabulate` | Pretty-print comparison tables |

---

## Make Commands

```bash
make help          # Show all available commands
make install       # Install production dependencies
make install-dev   # Install dev dependencies (+ pytest)
make setup         # Create .env from template
make test          # Run unit tests
make run           # Run all scenarios + export
make run-a         # Scenario A only
make run-b         # Scenario B only
make run-c         # Scenario C only
make run-d         # Scenario D only
make run-e         # Scenario E only
make list          # List available scenarios
make clean         # Remove caches and generated files
```

---

## License

MIT — see individual file headers for details.
