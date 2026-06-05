# Project: token-api (baseline)

Baseline **shared-tenant Token API** project used for A/B comparisons against
a dedicated PTU deployment.

## When to use

Pair this project with any PTU deployment via `--compare-with` to produce
side-by-side A/B numbers during a POC call:

```bash
make compare A=projects/qwen3.6-plus-2026-04-02_100K_10K B=projects/token-api SCN="A B"
# ── or directly ──
python -m ptu_benchmark \
  --project projects/qwen3.6-plus-2026-04-02_100K_10K \
  --compare-with projects/token-api \
  --scenarios A B --export
```

## Output

- A unified table per scenario (TTFT P50/P99, TPS, TPM, 429s/errors)
- A `results/<ptu>_vs_<token-api>/comparison.csv` summary with `delta_pct` columns
- '+' in the Δ column = the right-hand project wins (lower latency / higher throughput)

## Notes

- TPM quota and pricing fields are zeroed out — Token API is shared-tenant.
- Keep `concurrency_levels`, `sustained_*`, `burst_size`, and `context_sizes`
  identical between the two projects so the A/B comparison is meaningful.
- API credentials come from the project's own `.env` if present, otherwise the
  repository-root `.env` is used as a fallback.
