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
| **SLA compliance** | Optional pass/fail assessment against defined targets (availability, TTFT P95/P99, minimum TPS, error budget) |

Each benchmark run automatically generates customer-ready reports:

| Report | Format | Description |
|--------|--------|-------------|
| **Executive Report** | Markdown + figures | Deep technical analysis with a **Verdict by Scenario** dashboard, per-scenario breakdowns, statistical tables, matplotlib charts (TTFT percentiles, TPS throughput, error rates), and comparison deltas |
| **Business Report** | DOCX (Word) | Concise one-page summary with headline metrics, explanations, scenario overview, key takeaways, and cost — ready for customer delivery |
| **Customer POC Report** | Markdown | Auto-populated, fill-in-the-blank POC deliverable derived directly from the benchmark results (A/B mode; suppress with `--no-customer-report`) |
| **Cost Analysis** | Markdown | Breakeven analysis and 12-month cost projection comparing PTU vs Token API (suppress with `--no-cost-report`) |

All reports use **human-readable scenario names** (e.g. *Latency Baseline*, *Concurrency Stress Test*) alongside the single-letter keys.

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
│   ├── reporter/                   # Reporting subpackage
│   │   ├── console.py              # Banner / per-scenario console output
│   │   ├── charts.py               # Matplotlib charts (TTFT, TPS, errors)
│   │   ├── export.py               # JSON / CSV / dated-folder export
│   │   ├── executive.py            # Executive Markdown report (with verdict dashboard)
│   │   ├── business.py             # One-page DOCX business report
│   │   ├── customer.py             # Auto-populated customer POC report
│   │   ├── cost.py                 # Breakeven analysis & cost projection
│   │   ├── sla.py                  # SLA compliance scoring (when sla_targets defined)
│   │   └── utils.py                # Shared formatting helpers
│   └── scenarios/                  # One module per benchmark scenario
│       ├── base.py                 # Shared async streaming + display_name infrastructure
│       ├── scenario_a.py           # A — Latency Baseline
│       ├── scenario_b.py           # B — Concurrency Stress Test (auto-derived levels)
│       ├── scenario_c.py           # C — Sustained Throughput Test (30 min)
│       ├── scenario_d.py           # D — Peak Burst Resilience
│       └── scenario_e.py           # E — Long Context Performance (32K–128K)
├── tests/                          # Unit + integration tests
│   ├── conftest.py                 # Shared pytest fixtures
│   ├── fixtures/                   # Recorded streaming response fixtures
│   ├── test_config.py              # Unit — config loader
│   ├── test_utils.py               # Unit — helpers / prompt builders
│   ├── test_compare.py             # Unit — comparison reporter
│   ├── test_scenarios_integration.py   # Integration — scenarios end-to-end
│   └── test_workflow_integration.py    # Integration — CLI workflow
├── reports/                        # Dated export bundles (auto-created)
│   └── 20260605_ModelName_001/     # {date}_{model}_{NNN}
│       ├── PTU/                    # raw subject data (A/B mode)
│       │   ├── benchmark_results_*.json
│       │   └── benchmark_summary.csv
│       ├── Token_API/              # raw baseline data (A/B mode)
│       ├── figures/
│       ├── executive_report.md     ← ⭐ flagship report (A/B or standalone)
│       └── business_report.docx    ← one-page business summary (Word)
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

> **Tip — request timeout**: a per-request HTTP timeout (default `120s`) is applied to every async request to prevent a hung upstream from stalling the benchmark. Override per project with `request_timeout: <seconds>` in `project.yaml`, or globally via the `PTU_REQUEST_TIMEOUT` environment variable.

> **Tip — SLA compliance scoring**: Optional SLA targets (availability, TTFT P95/P99, minimum TPS, error budget) can be defined in `project.yaml` under `sla_targets`. When configured, the executive report includes a compliance assessment with pass/fail per target and headroom analysis.

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

| Scenario | Display Name | What It Measures | Duration |
|----------|--------------|------------------|----------|
| **A** | Latency Baseline | TTFT and TPS with zero contention | ~2 min |
| **B** | Concurrency Stress Test | Performance at N parallel requests (auto-derived from `output_tpm` if not set) + TPM utilization vs quota | ~5 min |
| **C** | Sustained Throughput Test | Max TPM maintained over 30 minutes | 30 min |
| **D** | Peak Burst Resilience | Behaviour under sudden traffic spike (200 req) | ~2 min |
| **E** | Long Context Performance | TTFT/TPS with 32K, 64K, 128K token inputs | ~5 min |

See [docs/SCENARIOS.md](docs/SCENARIOS.md) for a deep-dive into each scenario.

---

## CLI Reference

```
usage: ptu-benchmark [-h] [--version] [--project PATH | --env PATH]
                     [--compare-with PATH] [--no-compare]
                     [--no-customer-report]
                     [--scenarios {A,B,C,D,E} ...]
                     [--list] [--export]
                     [--output-dir OUTPUT_DIR]

options:
  --version              Show version and exit
  --project PATH         Project folder containing project.yaml
  --env PATH             Path to a .env file (legacy flat-config mode)
  --compare-with PATH    Second project folder for A/B comparison
  --no-compare           Disable the implicit Token API baseline auto-applied with --project
  --no-customer-report   Skip auto-generation of the customer POC report
  --scenarios A B D      Run specific scenarios (default: all)
  --list                 List available scenarios and exit
  --export               Export results (always on in project mode)
  --output-dir DIR       Directory for exports (default: reports/)
  --daily-volume TOKENS  Daily token volume for cost projection (overrides project.yaml)
  --growth-rate RATE     Monthly growth rate as decimal (e.g., 0.1 for 10%)
  --no-cost-report       Skip standalone cost analysis report generation
```

See [docs/USAGE.md](docs/USAGE.md) for full configuration details.

---

## Result Output Structure

Every run creates a **dated, auto-incremented report folder**:

```
reports/
  20260605_Qwen3.6-Plus-2026-04-02_001/
    data/                                      ← raw benchmark artefacts
      benchmark_results_20260605T120000Z.json
      benchmark_summary.csv
    figures/                                   ← matplotlib charts
      ttft_percentiles.png
      tps_throughput.png
      error_rates.png
    executive_report.md                        ← detailed long-form report
    business_report.docx                       ← one-page business summary (Word)
```

For **A/B comparisons**, the bundle uses role-based subfolders:

```
reports/
  20260605_Qwen3.6-Plus-2026-04-02_001/
    PTU/                                    ← raw subject data
      benchmark_results_*.json
      benchmark_summary.csv
    Token_API/                              ← raw baseline data
      benchmark_results_*.json
      benchmark_summary.csv
    figures/                                ← all charts (standalone + comparison)
      ttft_percentiles.png
      tps_throughput.png
      error_rates.png
      comparison_ttft_percentiles.png
      comparison_tps_throughput.png
      comparison_error_rates.png
      comparison_vs_ttft_tps.png
    executive_report.md                     ← ⭐ flagship A/B comparison
    business_report.docx                    ← ⭐ DOCX twin
    customer_report.md                      ← customer-facing POC report
    cost_analysis.md                        ← breakeven & cost projection
    metrics.csv                             ← side-by-side numbers
```

### Report Types

| File | Format | Audience | Description |
|------|--------|----------|-------------|
| `executive_report.md` | Markdown + PNG | Technical teams | In A/B mode: flagship full comparison with per-scenario breakdowns, TTFT percentile tables, throughput statistics, matplotlib charts, comparison deltas, and auto-generated findings for **both** arms. In single-project mode: equivalent depth for one project. |
| `business_report.docx` | DOCX (Word) | Decision makers | Professional one-page summary with headline metrics, explanations of what each metric means, scenario overview, key takeaways, and cost summary |
| `metrics.csv` | CSV | Data analysts | Flat side-by-side metrics for spreadsheet pivots and further analysis |
| `customer_report.md` | Markdown | Customers | Customer-facing POC report with editable sections for personalization |
| `cost_analysis.md` | Markdown | Decision makers | Breakeven analysis and cost projection (PTU vs Token API). Suppress with `--no-cost-report`. |
| `figures/*.png` | PNG images | Both | Matplotlib-generated charts: TTFT percentiles, TPS throughput, error rates, and comparison charts |
| `benchmark_results_*.json` | JSON | Engineers | Raw per-request timing data for custom analysis |
| `benchmark_summary.csv` | CSV | Analysts | Aggregated statistics (P50/P95/P99, TPS, error rates) |

---

## Example Output

The CLI shows a real-time, single-line progress bar while scenarios run.
All verbose per-request logs and summaries are written to `benchmark.log`
inside the report bundle.

### TTY mode (interactive terminal)

The active scenario rewrites a single line via `\r`; once it finishes,
the line is committed to scrollback so you can review history.

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
  Scenarios:  A, B, C, D, E
  Bundle:     reports/20260610_Qwen3.6-Plus_001
  Log file:   reports/20260610_Qwen3.6-Plus_001/benchmark.log

[09:22:29] |███░░░░░░░░░░░░░░░░░░░░░░░░░░░|   5% [ 1/ 5] Scenario A (Latency Baseline)...
[09:22:59] |██████░░░░░░░░░░░░░░░░░░░░░░░░|  20% [ 1/ 5] Scenario A (Latency Baseline) — Success (30.4s)
[09:23:00] |████████░░░░░░░░░░░░░░░░░░░░░░|  25% [ 2/ 5] Scenario B (Concurrency Stress Test)...
[09:24:42] |████████████░░░░░░░░░░░░░░░░░░|  40% [ 2/ 5] Scenario B (Concurrency Stress Test) — Success (102.1s)
…
[09:31:18] |██████████████████████████████| 100% [ 5/ 5] Complete ✓ (total: 528.7s)

  Bundle: reports/20260610_Qwen3.6-Plus_001/
  Log:    reports/20260610_Qwen3.6-Plus_001/benchmark.log
```

### Piped / non-TTY mode

When stdout is redirected (e.g. `python -m ptu_benchmark … | tee run.txt`),
the bar collapses to plain line-by-line output — no `\r`, no block chars,
no in-place rewriting:

```
[09:22:59]  20% [ 1/ 5] Scenario A (Latency Baseline) — Success (30.4s)
[09:24:42]  40% [ 2/ 5] Scenario B (Concurrency Stress Test) — Success (102.1s)
[09:27:08]  60% [ 3/ 5] Scenario C (Sustained Throughput) — Success (146.2s)
[09:29:31]  80% [ 4/ 5] Scenario D (Burst Test) — Success (143.0s)
[09:31:18] 100% [ 5/ 5] Scenario E (Long Context) — Success (107.0s)
[09:31:18] 100% Complete ✓ (total: 528.7s)
```

### benchmark.log

The full verbose execution trace — banner, scenario headers, every
per-request line, scenario summaries, and report-export details — is
captured in `reports/<bundle>/benchmark.log` so the terminal stays clean
during the run.

---

## Running Tests

```bash
make test               # unit tests only (fast)
make test-integration   # integration tests (scenarios + workflow)

# or directly:
python -m pytest tests/ -v -m "not integration"
python -m pytest tests/ -m integration -v
```

## Code Quality

The project uses **ruff** (lint + format) and **mypy** (type checking). All three are configured in `pyproject.toml`:

```bash
make lint        # ruff check src/ tests/
make format      # ruff format src/ tests/
make typecheck   # mypy src/ptu_benchmark/
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
make help              # Show all available commands
make install           # Install production dependencies
make install-dev       # Install dev dependencies (+ pytest)
make setup             # Create .env from template
make test              # Run unit tests (excludes integration)
make test-integration  # Run integration tests (scenarios + workflow)
make lint              # Run ruff linter
make format            # Format code with ruff
make typecheck         # Run mypy type checking
make run               # ⭐ Run all scenarios with A/B comparison (PTU vs Token API)
make run-a             # Scenario A only (with compare)
make run-b             # Scenario B only (with compare)
make run-c             # Scenario C only (with compare)
make run-d             # Scenario D only (with compare)
make run-e             # Scenario E only (with compare)
make compare           # Alias for 'run' (A/B comparison)
make poc               # Alias for 'run' (A/B comparison)
make list              # List available scenarios
make clean             # Remove caches and generated files
```

---

## License

MIT — see individual file headers for details.
MIT — see individual file headers for details.
