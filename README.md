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

Each benchmark run automatically generates two customer-ready reports:

| Report | Format | Description |
|--------|--------|-------------|
| **Executive Report** | Markdown + figures | Deep technical analysis with per-scenario breakdowns, statistical tables, matplotlib charts (TTFT percentiles, TPS throughput, error rates), and comparison deltas |
| **Business Report** | DOCX (Word) | Concise one-page summary with headline metrics, explanations, scenario overview, key takeaways, and cost — ready for customer delivery |

---

## Project Structure

```
PTU-Benchmark/
├── projects/                       # Per-use-case project folders
│   ├── template/                   # Copy this to create new projects
│   │   ├── project.yaml            # Model, quota, pricing configuration
│   │   └── .env.example            # API credentials template
│   ├── qwen3.6-plus-2026-04-02_500K_100K/  # Example PTU project
│   └── token-api/                  # Example Token API baseline project
├── src/ptu_benchmark/              # Core package
│   ├── __main__.py                 # CLI entry point
│   ├── config.py                   # Environment & configuration loader
│   ├── utils.py                    # Prompts, data classes, helpers
│   ├── reporter.py                 # Console output, JSON/CSV/report/chart export
│   └── scenarios/                  # One module per benchmark scenario
│       ├── base.py                 # Shared async streaming infrastructure
│       ├── scenario_a.py           # A — Single Request Baseline
│       ├── scenario_b.py           # B — Concurrent Load (10/50/100)
│       ├── scenario_c.py           # C — Sustained Throughput (30 min)
│       ├── scenario_d.py           # D — Peak Burst Test
│       └── scenario_e.py           # E — Long Context (32K–128K)
├── tests/                          # Unit tests
├── results/                        # Dated export bundles (auto-created)
│   └── 20260605_ModelName_001/     # {date}_{model}_{NNN}
│       └── results/
│           ├── benchmark_results_*.json
│           ├── benchmark_summary.csv
│           ├── executive_report.md       ← ⭐ flagship report (A/B or standalone)
│           └── business_report.docx     ← one-page business summary (Word)
├── docs/                           # Extended documentation
│   ├── USAGE.md                    # CLI reference & configuration guide
│   ├── SCENARIOS.md                # Detailed scenario descriptions
│   └── CUSTOMER_REPORT.md          # Customer-facing POC report template
├── benchmark-prompt.md             # Original reference prompts (standalone scripts)
├── pyproject.toml                  # Python packaging configuration
├── requirements.txt                # Pinned dependencies
├── Makefile                        # Convenience commands
├── .env.example                    # Configuration template
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

### 3. Create a Project

Each benchmark target (PTU deployment or Token API baseline) gets its own project folder:

```bash
# Copy the template
cp -r projects/template projects/my-ptu

# Edit project.yaml with your deployment details
# Edit .env with your API key
```

See [projects/template/project.yaml](projects/template/project.yaml) for all available fields.

### 4. Run Benchmarks

```bash
# Default workflow — runs ALL scenarios on BOTH the PTU project AND
# projects/token-api, then emits side-by-side comparison reports.
# (The Token API baseline is auto-applied; no flag needed.)
python -m ptu_benchmark --project projects/my-ptu

# Single project only — skip the implicit Token API baseline
python -m ptu_benchmark --project projects/my-ptu --no-compare

# Override the default baseline with a different project
python -m ptu_benchmark --project projects/my-ptu --compare-with projects/other-baseline

# Run specific scenarios (still auto-compares with Token API)
python -m ptu_benchmark --project projects/my-ptu --scenarios A B D

# Or use Make shortcuts
make run                    # ⭐ A/B comparison (PTU vs Token API), scenarios A B
make run SCN="A B C D E"   # all scenarios with compare
make run-a                  # Scenario A only (with compare)
```

---

## Benchmark Scenarios at a Glance

| Scenario | Name | What It Measures | Duration |
|----------|------|------------------|----------|
| **A** | Single Request Baseline | TTFT and TPS with zero contention | ~2 min |
| **B** | Concurrent Load | Performance at N parallel requests (auto-derived from `output_tpm` if not set) + TPM utilization vs quota | ~5 min |
| **C** | Sustained Throughput | Max TPM maintained over 30 minutes | 30 min |
| **D** | Peak Burst | Behaviour under sudden traffic spike (200 req) | ~2 min |
| **E** | Long Context | TTFT/TPS with 32K, 64K, 128K token inputs | ~5 min |

See [docs/SCENARIOS.md](docs/SCENARIOS.md) for a deep-dive into each scenario.

---

## CLI Reference

```
usage: ptu-benchmark [-h] [--version] [--project PATH | --env PATH]
                     [--compare-with PATH]
                     [--scenarios {A,B,C,D,E} ...]
                     [--list] [--export]
                     [--output-dir OUTPUT_DIR]

options:
  --version              Show version and exit
  --project PATH         Project folder containing project.yaml
  --env PATH             Path to a .env file (legacy flat-config mode)
  --compare-with PATH    Second project folder for A/B comparison
  --scenarios A B D      Run specific scenarios (default: all)
  --list                 List available scenarios and exit
  --export               Export results (always on in project mode)
  --output-dir DIR       Directory for exports (default: auto-named)
```

See [docs/USAGE.md](docs/USAGE.md) for full configuration details.

---

## Result Output Structure

Every run creates a **dated, auto-incremented result folder**:

```
results/
  20260605_Qwen3.6-Plus-2026-04-02_001/
    results/
      benchmark_results_20260605T120000Z.json   ← full per-request data
      benchmark_summary.csv                      ← aggregated statistics
      executive_report.md                        ← detailed long-form report
      figures/                                   ← matplotlib charts
        ttft_percentiles.png
        tps_throughput.png
        error_rates.png
      business_report.docx                       ← one-page business summary (Word)
```

For **A/B comparisons**, the bundle is organized under the subject model's code:

```
results/
  20260605_PtuModel_vs_TokenApi_001/
    results/
      qwen3.6-plus-2026-04-02/               ← model report folder
        executive_report.md                   ← ⭐ flagship A/B comparison
        business_report.docx                  ← ⭐ DOCX twin
        metrics.csv                           ← side-by-side numbers
        subject_only_executive_report.md      ← PTU-only deep dive
        subject_only_business_report.docx     ← PTU-only DOCX
        figures/
          ttft_percentiles.png                ← subject-only charts
          comparison_ttft_percentiles.png     ← A/B comparison charts
          comparison_vs_ttft_tps.png
        qwen3.6-plus-2026-04-02_500K_100K/   ← PTU raw data
        token-api/                            ← baseline raw data
```

### Report Types

| File | Format | Audience | Description |
|------|--------|----------|-------------|
| `executive_report.md` | Markdown + PNG | Technical teams | In A/B mode: flagship full comparison with per-scenario breakdowns, TTFT percentile tables, throughput statistics, matplotlib charts, comparison deltas, and auto-generated findings for **both** arms. In single-project mode: equivalent depth for one project. |
| `business_report.docx` | DOCX (Word) | Decision makers | Professional one-page summary with headline metrics, explanations of what each metric means, scenario overview, key takeaways, and cost summary |
| `metrics.csv` | CSV | Data analysts | Flat side-by-side metrics for spreadsheet pivots and further analysis |
| `subject_only_executive_report.md` | Markdown + PNG | Technical teams | PTU-only deep dive (generated alongside the A/B report for reference) |
| `figures/*.png` | PNG images | Both | Matplotlib-generated charts: TTFT percentiles, TPS throughput, error rates, and comparison charts |
| `benchmark_results_*.json` | JSON | Engineers | Raw per-request timing data for custom analysis |
| `benchmark_summary.csv` | CSV | Analysts | Aggregated statistics (P50/P95/P99, TPS, error rates) |

---

## Example Output

```
============================================================
  PTU Benchmark Suite v1.0.0
============================================================
  Project:    Qwen3.6-Plus (PTU)
  Model:      Qwen3.6-Plus-2026-04-02 (qwen3.6-plus-2026-04-02)
  Deployment: qwen3.6-plus-2026-04-02-d1839645ee95
  Quota:      100,000 input TPM  /  10,000 output TPM
  Price:      $19.20/hour
  Base URL:   https://dashscope-intl.aliyuncs.com/compatible-mode/v1
  Running:    A, B, C, D, E

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

  Results exported:
    JSON              → results/20260605_Qwen3.6-Plus_001/results/benchmark_results_*.json
    CSV               → results/20260605_Qwen3.6-Plus_001/results/benchmark_summary.csv
    Executive Report  → results/20260605_Qwen3.6-Plus_001/results/executive_report.md
    Figures           → results/20260605_Qwen3.6-Plus_001/results/figures/ (3 charts)
    Business Report   → results/20260605_Qwen3.6-Plus_001/results/business_report.docx
```

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
2. Create project folder (cp -r projects/template projects/my-ptu)
          │
3. Run Scenario A on Token API  ──►  baseline numbers
   python -m ptu_benchmark --project projects/token-api --scenarios A
          │
4. Run Scenario A on PTU        ──►  PTU numbers
   python -m ptu_benchmark --project projects/my-ptu --scenarios A
          │
5. Run Scenarios B–E on PTU     ──►  stress-test results
          │
6. A/B compare                  ──►  side-by-side reports
   python -m ptu_benchmark --project projects/my-ptu --compare-with projects/token-api
          │
7. Deliver reports to customer  ──►  executive_report.md + business_report.docx
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `openai` | Streaming chat completions via OpenAI-compatible API |
| `aiohttp` | Async HTTP for concurrent and sustained load tests |
| `numpy` | Statistical aggregations (percentiles, mean) |
| `python-dotenv` | Load configuration from `.env` files |
| `pyyaml` | Parse project.yaml configuration |
| `tabulate` | Pretty-print comparison tables |
| `matplotlib` | Generate charts (TTFT, TPS, error rates) for executive report |
| `python-docx` | Generate professional DOCX business reports |

---

## Make Commands

```bash
make help          # Show all available commands
make install       # Install production dependencies
make install-dev   # Install dev dependencies (+ pytest)
make setup         # Create .env from template
make test          # Run unit tests
make run           # ⭐ Run all scenarios with A/B comparison (PTU vs Token API)
make run-a         # Scenario A only (with compare)
make run-b         # Scenario B only (with compare)
make run-c         # Scenario C only (with compare)
make run-d         # Scenario D only (with compare)
make run-e         # Scenario E only (with compare)
make compare       # Alias for 'run' (A/B comparison)
make poc           # Alias for 'run' (A/B comparison)
make list          # List available scenarios
make clean         # Remove caches and generated files
```

---

## License

MIT — see individual file headers for details.
