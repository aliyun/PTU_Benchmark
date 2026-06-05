# Benchmark Scenarios

> Detailed description of each scenario: purpose, methodology, expected results, and tuning guidance.

---

## Table of Contents

1. [Scenario A — Single Request Baseline](#scenario-a--single-request-baseline)
2. [Scenario B — Concurrent Load](#scenario-b--concurrent-load)
3. [Scenario C — Sustained Throughput](#scenario-c--sustained-throughput)
4. [Scenario D — Peak Burst Test](#scenario-d--peak-burst-test)
5. [Scenario E — Long Context Test](#scenario-e--long-context-test)
6. [Recommended Run Order](#recommended-run-order)

---

## Scenario A — Single Request Baseline

**Module:** `scenario_a.py`
**Run:** `python -m ptu_benchmark --scenarios A` or `make run-a`
**Duration:** ~2 minutes

### Purpose

Establish the **best-case latency and throughput** for a single request with zero contention. This is the reference point that all other scenarios are compared against.

### Methodology

1. Sends a **short prompt** (~10 tokens) 5 times — measures TTFT primarily
2. Sends a **long prompt** (~60 tokens, requesting 2000-word output) 3 times — measures sustained generation speed (TPS)
3. Uses the **OpenAI SDK** (synchronous streaming) for precise timing

### Metrics Collected

| Metric | Description |
|--------|-------------|
| TTFT (ms) | Wall-clock time from request start to first output token |
| TPS | Tokens generated per second (excluding TTFT) |
| Total time | Full request duration |
| Token count | Number of output chunks received |

### Expected Results (PTU)

| Metric | Typical Range |
|--------|---------------|
| TTFT (short prompt) | 200–500 ms |
| TTFT (long prompt) | 250–600 ms |
| TPS | 50–80 tokens/sec |

### What to Look For

- **Consistency:** TTFT should be stable across runs (low variance). High variance suggests contention or cold-start issues.
- **PTU vs Token API:** PTU TTFT is typically 30–50% lower because requests are routed to reserved capacity, not a shared queue.

### Tuning

No configuration needed. Scenario A uses `default_max_tokens=2048` from config.

---

## Scenario B — Concurrent Load

**Module:** `scenario_b.py`
**Run:** `python -m ptu_benchmark --scenarios B` or `make run-b`
**Duration:** ~5 minutes (depends on concurrency levels)

### Purpose

Measure **how performance degrades** as the number of simultaneous requests increases. PTU should maintain near-baseline performance; Token API will degrade noticeably.

### Methodology

1. Fires **N requests simultaneously** (where N = each value in `CONCURRENCY_LEVELS`)
2. All requests use **async streaming** via `aiohttp`
3. Each concurrency level runs as a separate batch with a pause between

### Metrics Collected

All metrics from Scenario A, plus:

| Metric | Description |
|--------|-------------|
| Per-level P50/P95/P99 TTFT | Latency percentiles at each concurrency level |
| Per-level average TPS | Mean tokens/sec across all concurrent requests |
| Estimated TPM | Total tokens / max request duration * 60 |
| Error rate | Percentage of failed or 429 responses |

### Expected Results (PTU)

| Concurrency | TTFT P50 | TTFT P99 | Avg TPS | 429 Errors |
|-------------|----------|----------|---------|------------|
| 10 | ~300ms | ~500ms | ~55 | 0 |
| 50 | ~400ms | ~800ms | ~50 | 0 |
| 100 | ~500ms | ~1200ms | ~45 | 0 |

### What to Look For

- **Graceful degradation:** TTFT increases somewhat at high concurrency, but TPS should remain stable.
- **429 errors at high concurrency:** On Token API, expect 429s at 50+. PTU should have zero 429s up to its provisioned capacity.
- **The "knee" point:** The concurrency level where Token API starts returning 429s — this is the key selling point.

### Tuning

```ini
# .env
CONCURRENCY_LEVELS=10,50,100     # add more levels: 10,25,50,75,100,150
```

### POC Tip

> Run Scenario B on **both** Token API and PTU. The divergence at concurrency=50 is the most compelling visual for customers.

---

## Scenario C — Sustained Throughput

**Module:** `scenario_c.py`
**Run:** `python -m ptu_benchmark --scenarios C` or `make run-c`
**Duration:** 30 minutes (configurable)

### Purpose

Prove that PTU can **maintain its guaranteed TPM over a long period**, not just in short bursts. This is the most important scenario for enterprise customers who need predictable throughput.

### Methodology

1. Maintains a **constant pool of concurrent workers** (`SUSTAINED_CONCURRENCY`)
2. Workers fire streaming requests back-to-back for the full duration
3. Progress is reported **every minute** with running TPM and error counts
4. Final summary shows average TPM, total tokens, and 429 error rate

### Metrics Collected

| Metric | Description |
|--------|-------------|
| Running TPM | Tokens per minute, updated every minute |
| Total requests | Cumulative successful requests |
| Total tokens | Sum of all output tokens |
| Average TPM | Total tokens / elapsed minutes |
| 429 error count | Total rate-limited requests |
| 429 error % | Percentage of requests that were rate-limited |

### Expected Results (PTU)

| Metric | Expected |
|--------|----------|
| TPM stability | Within ±10% of rated capacity across all 30 minutes |
| 429 errors | 0% (or near 0% if at capacity limit) |
| Total requests | Hundreds to thousands depending on concurrency |

### What to Look For

- **Flat TPM line:** If you plot TPM over time, it should be nearly flat — no degradation over the 30 minutes.
- **Zero 429s:** PTU guarantees throughput. Any 429s indicate the test is exceeding purchased capacity.
- **TPM vs purchased capacity:** Compare measured TPM to the PTU contract value. It should match or slightly exceed it.

### Tuning

```ini
# .env
SUSTAINED_DURATION=1800        # 30 minutes (use 120 for quick tests)
SUSTAINED_CONCURRENCY=20       # increase for higher-capacity PTUs
```

### POC Tip

> For a quick validation during a live demo, set `SUSTAINED_DURATION=120` (2 minutes). Run the full 30-minute test overnight for the formal report.

---

## Scenario D — Peak Burst Test

**Module:** `scenario_d.py`
**Run:** `python -m ptu_benchmark --scenarios D` or `make run-d`
**Duration:** ~2 minutes

### Purpose

Verify how the system handles a **sudden spike of traffic** — all requests arrive simultaneously with no ramp-up. This simulates real-world burst events (e.g., marketing campaign launch, end-of-day batch processing).

### Methodology

1. Sends `BURST_SIZE` requests **all at once** (no stagger, no warm-up)
2. Uses async streaming via `aiohttp`
3. Reports success rate, 429 rate, and other error rates

### Metrics Collected

| Metric | Description |
|--------|-------------|
| Success count / rate | Requests completed successfully |
| 429 count | Requests that were rate-limited |
| Other errors | Network timeouts, HTTP 5xx, etc. |
| PASS/FAIL verdict | Zero 429s = PASS |

### Expected Results

| Outcome | PTU | Token API |
|---------|-----|-----------|
| Success rate | 95–100% | 60–80% |
| 429 errors | 0–5% | 20–40% |
| Verdict | PASS | FAIL |

### What to Look For

- **PTU absorbs the burst:** Zero or very few 429s within provisioned capacity.
- **Token API crumbles:** The shared pool rate-limits aggressively under burst — this is the key contrast.
- **Auto-fallback:** If 429s do occur on PTU, they indicate excess traffic that auto-falls back to PAYG billing — no service interruption for the end user.

### Tuning

```ini
# .env
BURST_SIZE=200     # increase to 500 for stress-testing large PTUs
```

### POC Tip

> Run Scenario D on Token API first (watch the 429s pile up), then immediately run on PTU (zero 429s). The contrast is immediate and compelling.

---

## Scenario E — Long Context Test

**Module:** `scenario_e.py`
**Run:** `python -m ptu_benchmark --scenarios E` or `make run-e`
**Duration:** ~5 minutes

### Purpose

Measure performance with **large input contexts** — relevant for customers doing RAG (Retrieval-Augmented Generation), document processing, or any workload that sends long prompts.

### Methodology

1. Generates synthetic text of approximately **32K, 64K, and 128K tokens**
2. Prepends the context to a summarisation prompt
3. Runs 3 iterations per context size
4. Measures TTFT (time to process input + first output token) and TPS

### Metrics Collected

Same as Scenario A, broken down by context size:

| Metric | Description |
|--------|-------------|
| TTFT per context size | Longer inputs = longer prefill time |
| TPS per context size | Generation speed after prefill |
| Token count | Output tokens generated |

### Expected Results (PTU)

| Context Size | TTFT | TPS |
|-------------|------|-----|
| 32K | 800–2000ms | ~50 |
| 64K | 1500–3500ms | ~48 |
| 128K | 3000–6000ms | ~45 |

### What to Look For

- **TTFT scales with input size** — this is expected (prefill time). The key is that **TPS remains stable** regardless of input size.
- **PTU vs Token API:** Token API may time out or throttle on very long contexts; PTU processes them at full speed.
- **Use case mapping:** If the customer does RAG with ~10K token contexts, the 32K results are most relevant.

### Tuning

```ini
# .env
CONTEXT_SIZES=32000,64000,128000   # add/remove sizes as needed
```

### POC Tip

> Ask the customer for their typical context size and max_tokens before running. Customise `CONTEXT_SIZES` to match their actual workload.

---

## Recommended Run Order

For a standard POC engagement, run scenarios in this order:

```
1. Scenario A   →  baseline (quick, 2 min)
2. Scenario B   →  concurrency (5 min, most impactful)
3. Scenario D   →  burst (2 min, dramatic contrast)
4. Scenario E   →  long context (5 min, if applicable)
5. Scenario C   →  sustained (30 min, run last or overnight)
```

### Quick Demo Set (~10 minutes)

```bash
python -m ptu_benchmark --scenarios A B D --export
```

### Full POC Set (~45 minutes)

```bash
python -m ptu_benchmark --export
```
