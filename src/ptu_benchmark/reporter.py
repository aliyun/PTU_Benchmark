"""
Results reporting and export utilities.

Generates console output, JSON exports, and comparison tables.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from tabulate import tabulate

from ptu_benchmark.utils import ScenarioResult, SingleRequestResult


# ─────────────────────────────────────────────
# Console output
# ─────────────────────────────────────────────

def print_header(title: str, char: str = "=") -> None:
    width = 60
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def print_single_result(result: SingleRequestResult, label: str = "") -> None:
    """Print a single-request result line."""
    tag = f"[{label}] " if label else ""
    if not result.success:
        print(f"{tag}ERROR: {result.error}")
        return
    print(
        f"{tag}TTFT: {result.ttft_ms:.0f}ms | "
        f"TPS: {result.tps:.1f} | "
        f"Total: {result.total_seconds:.2f}s | "
        f"Tokens: {result.tokens}"
    )


def print_scenario_summary(result: ScenarioResult) -> None:
    """Print aggregated statistics for a scenario run."""
    print_header(f"Scenario {result.scenario}: {result.label}")
    ok = result.successful
    errs = result.failed
    rl = result.rate_limited

    print(
        f"  Total: {len(result.results)} | "
        f"Success: {len(ok)} | "
        f"Errors: {len(errs)} | "
        f"429s: {len(rl)}"
    )

    if not ok:
        print("  No successful requests to report.")
        return

    ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
    tps_vals = [r.tps for r in ok]

    if ttfts:
        print(
            f"  TTFT  → P50: {np.percentile(ttfts, 50):.0f}ms | "
            f"P95: {np.percentile(ttfts, 95):.0f}ms | "
            f"P99: {np.percentile(ttfts, 99):.0f}ms"
        )
    if tps_vals:
        print(
            f"  TPS   → Avg: {np.mean(tps_vals):.1f} | "
            f"Min: {np.min(tps_vals):.1f} | "
            f"Max: {np.max(tps_vals):.1f}"
        )

    total_tokens = sum(r.tokens for r in ok)
    # NOTE: For multi-batch scenarios (e.g. Scenario B's aggregated
    # ScenarioResult across multiple concurrency levels), max_time is the
    # slowest single-request duration and `total_tokens / max_time` does
    # NOT represent the true aggregate TPM. Per-batch TPM is printed
    # inside each scenario; this line is an order-of-magnitude estimate.
    max_time = max((r.total_seconds for r in ok), default=0.0)
    if max_time >= 1e-3:
        print(f"  Est. TPM: {total_tokens / max_time * 60:,.0f}")


# ─────────────────────────────────────────────
# Comparison table (Token API vs PTU)
# ─────────────────────────────────────────────

def print_comparison_table(
    token_api: ScenarioResult,
    ptu: ScenarioResult,
) -> None:
    """Print a side-by-side comparison table."""
    print_header("Token API vs PTU Comparison")

    def _stats(sr: ScenarioResult) -> dict[str, Any]:
        ok = sr.successful
        if not ok:
            return {"ttft_p50": "—", "ttft_p99": "—", "tps_avg": "—", "max_concurrent": 0}
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        max_time = max((r.total_seconds for r in ok), default=0.0)
        return {
            "ttft_p50": f"{np.percentile(ttfts, 50):.0f}" if ttfts else "—",
            "ttft_p99": f"{np.percentile(ttfts, 99):.0f}" if ttfts else "—",
            "tps_avg": f"{np.mean(tps_vals):.1f}" if tps_vals else "—",
            "max_concurrent": len(ok),
            "sustained_tpm": (
                sum(r.tokens for r in ok) / max_time * 60
                if max_time >= 1e-3 else 0.0
            ),
        }

    a, b = _stats(token_api), _stats(ptu)

    rows = [
        ["TTFT (P50)", f"{a['ttft_p50']} ms", f"{b['ttft_p50']} ms", ""],
        ["TTFT (P99)", f"{a['ttft_p99']} ms", f"{b['ttft_p99']} ms", ""],
        ["TPS (avg)", f"{a['tps_avg']}", f"{b['tps_avg']}", ""],
        ["Max Concurrent (no 429)", str(a["max_concurrent"]), str(b["max_concurrent"]), ""],
    ]
    print(tabulate(rows, headers=["Metric", "Token API", "PTU", "Improvement"], tablefmt="grid"))


# ─────────────────────────────────────────────
# Project A/B comparison (--compare-with)
# ─────────────────────────────────────────────

def _scenario_metrics(sr: ScenarioResult) -> dict[str, float | None]:
    """Compute the headline metrics used in A/B comparisons."""
    ok = sr.successful
    if not ok:
        return {
            "ttft_p50": None, "ttft_p95": None, "ttft_p99": None,
            "tps_avg": None, "tpm": None,
            "success": 0, "errors": len(sr.failed), "rate_limited": len(sr.rate_limited),
        }
    ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
    tps_vals = [r.tps for r in ok]
    total_tokens = sum(r.tokens for r in ok)
    max_time = max((r.total_seconds for r in ok), default=0.0)
    return {
        "ttft_p50": float(np.percentile(ttfts, 50)) if ttfts else None,
        "ttft_p95": float(np.percentile(ttfts, 95)) if ttfts else None,
        "ttft_p99": float(np.percentile(ttfts, 99)) if ttfts else None,
        "tps_avg":  float(np.mean(tps_vals)) if tps_vals else None,
        "tpm":      total_tokens / max_time * 60 if max_time >= 1e-3 else None,
        "success":  len(ok),
        "errors":   len(sr.failed),
        "rate_limited": len(sr.rate_limited),
    }


def _delta(a: float | None, b: float | None, *, lower_is_better: bool) -> str:
    """Format a percentage change of B relative to A. '+' means B is better."""
    if a is None or b is None or a == 0:
        return "—"
    pct = (a - b) / a * 100 if lower_is_better else (b - a) / a * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def print_project_comparison(
    name_a: str,
    results_a: Sequence[ScenarioResult],
    name_b: str,
    results_b: Sequence[ScenarioResult],
) -> None:
    """
    Print a side-by-side A/B comparison table for two project runs.

    Δ column shows the relative change of *B vs A*; '+' means B is better
    (lower latency / higher throughput).
    """
    print_header(f"A/B Comparison: {name_a}  vs  {name_b}")

    # Index by scenario key so we align rows even if order differs
    by_key_a = {r.scenario: r for r in results_a}
    by_key_b = {r.scenario: r for r in results_b}
    keys = [k for k in by_key_a if k in by_key_b]

    if not keys:
        print("  No overlapping scenarios to compare.")
        return

    rows: list[list[str]] = []
    for key in keys:
        sr_a, sr_b = by_key_a[key], by_key_b[key]
        ma, mb = _scenario_metrics(sr_a), _scenario_metrics(sr_b)

        def _fmt(v: float | None, suffix: str = "") -> str:
            return "—" if v is None else f"{v:.0f}{suffix}" if suffix in ("ms", "") and suffix == "ms" \
                else (f"{v:.1f}{suffix}" if v < 1000 else f"{v:,.0f}{suffix}")

        rows.append([
            f"{key} • TTFT P50",
            "—" if ma["ttft_p50"] is None else f"{ma['ttft_p50']:.0f} ms",
            "—" if mb["ttft_p50"] is None else f"{mb['ttft_p50']:.0f} ms",
            _delta(ma["ttft_p50"], mb["ttft_p50"], lower_is_better=True),
        ])
        rows.append([
            f"{key} • TTFT P99",
            "—" if ma["ttft_p99"] is None else f"{ma['ttft_p99']:.0f} ms",
            "—" if mb["ttft_p99"] is None else f"{mb['ttft_p99']:.0f} ms",
            _delta(ma["ttft_p99"], mb["ttft_p99"], lower_is_better=True),
        ])
        rows.append([
            f"{key} • TPS (avg)",
            "—" if ma["tps_avg"] is None else f"{ma['tps_avg']:.1f}",
            "—" if mb["tps_avg"] is None else f"{mb['tps_avg']:.1f}",
            _delta(ma["tps_avg"], mb["tps_avg"], lower_is_better=False),
        ])
        rows.append([
            f"{key} • Est. TPM",
            "—" if ma["tpm"] is None else f"{ma['tpm']:,.0f}",
            "—" if mb["tpm"] is None else f"{mb['tpm']:,.0f}",
            _delta(ma["tpm"], mb["tpm"], lower_is_better=False),
        ])
        rows.append([
            f"{key} • 429s / errors",
            f"{ma['rate_limited']} / {ma['errors']}",
            f"{mb['rate_limited']} / {mb['errors']}",
            "",
        ])
        rows.append(["", "", "", ""])  # separator

    headers = ["Metric", name_a, name_b, "Δ (B vs A)"]
    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print("\n  Δ legend: '+' means the right column wins "
          "(lower latency / higher throughput).")


def export_comparison_csv(
    name_a: str,
    results_a: Sequence[ScenarioResult],
    name_b: str,
    results_b: Sequence[ScenarioResult],
    output_dir: str | Path = "results",
    filename: str = "comparison.csv",
) -> Path:
    """Export the A/B comparison as a flat CSV (one row per scenario)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    by_key_a = {r.scenario: r for r in results_a}
    by_key_b = {r.scenario: r for r in results_b}
    keys = [k for k in by_key_a if k in by_key_b]

    header = [
        "scenario",
        f"{name_a}_ttft_p50_ms", f"{name_b}_ttft_p50_ms", "ttft_p50_delta_pct",
        f"{name_a}_ttft_p99_ms", f"{name_b}_ttft_p99_ms", "ttft_p99_delta_pct",
        f"{name_a}_tps_avg",    f"{name_b}_tps_avg",    "tps_delta_pct",
        f"{name_a}_tpm",        f"{name_b}_tpm",        "tpm_delta_pct",
        f"{name_a}_429s",       f"{name_b}_429s",
        f"{name_a}_errors",     f"{name_b}_errors",
    ]
    lines = [",".join(header)]

    def _num_delta(a: float | None, b: float | None, *, lower_is_better: bool) -> str:
        if a is None or b is None or a == 0:
            return ""
        pct = (a - b) / a * 100 if lower_is_better else (b - a) / a * 100
        return f"{pct:.2f}"

    for key in keys:
        ma = _scenario_metrics(by_key_a[key])
        mb = _scenario_metrics(by_key_b[key])
        row = [
            key,
            "" if ma["ttft_p50"] is None else f"{ma['ttft_p50']:.0f}",
            "" if mb["ttft_p50"] is None else f"{mb['ttft_p50']:.0f}",
            _num_delta(ma["ttft_p50"], mb["ttft_p50"], lower_is_better=True),
            "" if ma["ttft_p99"] is None else f"{ma['ttft_p99']:.0f}",
            "" if mb["ttft_p99"] is None else f"{mb['ttft_p99']:.0f}",
            _num_delta(ma["ttft_p99"], mb["ttft_p99"], lower_is_better=True),
            "" if ma["tps_avg"] is None else f"{ma['tps_avg']:.2f}",
            "" if mb["tps_avg"] is None else f"{mb['tps_avg']:.2f}",
            _num_delta(ma["tps_avg"], mb["tps_avg"], lower_is_better=False),
            "" if ma["tpm"] is None else f"{ma['tpm']:.0f}",
            "" if mb["tpm"] is None else f"{mb['tpm']:.0f}",
            _num_delta(ma["tpm"], mb["tpm"], lower_is_better=False),
            str(ma["rate_limited"]), str(mb["rate_limited"]),
            str(ma["errors"]),       str(mb["errors"]),
        ]
        lines.append(",".join(row))

    out_path.write_text("\n".join(lines))
    return out_path


# ─────────────────────────────────────────────
# JSON / file export
# ─────────────────────────────────────────────

def export_json(
    results: Sequence[ScenarioResult],
    output_dir: str | Path = "results",
    filename: str | None = None,
) -> Path:
    """
    Export all scenario results to a JSON file.

    Returns the path to the written file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"benchmark_results_{ts}.json"

    out_path = output_dir / filename
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenarios": [r.to_dict() for r in results],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def export_csv_summary(
    results: Sequence[ScenarioResult],
    output_dir: str | Path = "results",
    filename: str = "benchmark_summary.csv",
) -> Path:
    """Export a CSV summary of aggregated results."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    rows = []
    for sr in results:
        ok = sr.successful
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        rows.append({
            "scenario": sr.scenario,
            "label": sr.label,
            "total": len(sr.results),
            "success": len(ok),
            "errors": len(sr.failed),
            "rate_limited": len(sr.rate_limited),
            "ttft_p50_ms": f"{np.percentile(ttfts, 50):.0f}" if ttfts else "",
            "ttft_p95_ms": f"{np.percentile(ttfts, 95):.0f}" if ttfts else "",
            "ttft_p99_ms": f"{np.percentile(ttfts, 99):.0f}" if ttfts else "",
            "tps_avg": f"{np.mean(tps_vals):.1f}" if tps_vals else "",
            "tps_min": f"{np.min(tps_vals):.1f}" if tps_vals else "",
            "tps_max": f"{np.max(tps_vals):.1f}" if tps_vals else "",
        })

    if rows:
        header = list(rows[0].keys())
        lines = [",".join(header)]
        for row in rows:
            lines.append(",".join(str(row[k]) for k in header))
        out_path.write_text("\n".join(lines))

    return out_path
