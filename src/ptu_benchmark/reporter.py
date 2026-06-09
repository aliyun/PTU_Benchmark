"""
Results reporting and export utilities.

Generates console output, JSON exports, comparison tables,
executive reports (long-form Markdown with figures),
and one-page business reports (DOCX).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for report generation
import matplotlib.pyplot as plt
import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Inches, Pt, Cm, RGBColor
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
    filename: str = "metrics.csv",
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


# ─────────────────────────────────────────────
# Output folder naming
# ─────────────────────────────────────────────

def _sanitize_model_name(model_name: str) -> str:
    """Sanitize a model name for use in folder names."""
    # Replace spaces and special chars with underscores
    clean = re.sub(r"[^\w\-.]", "_", model_name)
    # Collapse multiple underscores
    clean = re.sub(r"_+", "_", clean)
    return clean.strip("_")


def build_result_folder(
    base_dir: str | Path,
    model_name: str,
    compare_with: str | None = None,
) -> Path:
    """
    Build a dated result folder: ``{base}/{YYYYMMDD}_{model}[_vs_{other}]_{NNN}/results``.

    Auto-increments the 3-digit sequence if the folder already exists.

    Parameters
    ----------
    base_dir:
        Root results directory (e.g. ``results/``).
    model_name:
        Primary model identifier (will be sanitized).
    compare_with:
        Optional second model name for A/B comparisons.

    Returns
    -------
    Path to the ``results/`` subfolder inside the dated bundle.
    """
    base = Path(base_dir)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    primary = _sanitize_model_name(model_name)
    if compare_with:
        secondary = _sanitize_model_name(compare_with)
        prefix = f"{today}_{primary}_vs_{secondary}_"
    else:
        prefix = f"{today}_{primary}_"

    # Find next available sequence number
    seq = 1
    while True:
        folder_name = f"{prefix}{seq:03d}"
        candidate = base / folder_name
        if not candidate.exists():
            break
        seq += 1

    results_dir = candidate / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def _get_model_display_name(config: Any, fallback: str = "") -> str:
    """Extract a human-friendly model display name from a BenchmarkConfig."""
    if config:
        proj = getattr(config, "project", None)
        if proj:
            name = getattr(proj, "model_name", "") or ""
            code = getattr(proj, "model_code", "") or ""
            if name and code:
                return f"{name} ({code})"
            if name:
                return name
            if code:
                return code
        model_id = getattr(config, "model_id", "")
        if model_id:
            return model_id
    return fallback


# ─────────────────────────────────────────────
# Chart generation helpers
# ─────────────────────────────────────────────

_CHART_STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": "#f8f9fa",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 10,
}


def _generate_ttft_chart(
    results: Sequence[ScenarioResult],
    figures_dir: Path,
    filename: str = "ttft_percentiles.png",
) -> Path | None:
    """Generate a TTFT percentiles bar chart across all scenarios."""
    scenarios: list[str] = []
    p50: list[float] = []
    p95: list[float] = []
    p99: list[float] = []

    for sr in results:
        ok = sr.successful
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        if not ttfts:
            continue
        scenarios.append(f"Scenario {sr.scenario}")
        p50.append(float(np.percentile(ttfts, 50)))
        p95.append(float(np.percentile(ttfts, 95)))
        p99.append(float(np.percentile(ttfts, 99)))

    if not scenarios:
        return None

    with plt.rc_context(_CHART_STYLE):
        fig, ax = plt.subplots(figsize=(9, 5))
        x = np.arange(len(scenarios))
        width = 0.25
        ax.bar(x - width, p50, width, label="P50", color="#2196F3")
        ax.bar(x, p95, width, label="P95", color="#FF9800")
        ax.bar(x + width, p99, width, label="P99", color="#F44336")
        ax.set_ylabel("Time to First Token (ms)")
        ax.set_title("TTFT Percentiles by Scenario")
        ax.set_xticks(x)
        ax.set_xticklabels(scenarios)
        ax.legend()
        ax.set_ylim(bottom=0)

        # Add value labels on bars
        for bars in ax.containers:
            ax.bar_label(bars, fmt="%.0f", fontsize=7, padding=2)

        plt.tight_layout()
        out = figures_dir / filename
        fig.savefig(out, dpi=150)
        plt.close(fig)
    return out


def _generate_tps_chart(
    results: Sequence[ScenarioResult],
    figures_dir: Path,
    filename: str = "tps_throughput.png",
) -> Path | None:
    """Generate a TPS average + min/max range chart across all scenarios."""
    scenarios: list[str] = []
    avgs: list[float] = []
    mins: list[float] = []
    maxs: list[float] = []

    for sr in results:
        ok = sr.successful
        tps_vals = [r.tps for r in ok]
        if not tps_vals:
            continue
        scenarios.append(f"Scenario {sr.scenario}")
        avgs.append(float(np.mean(tps_vals)))
        mins.append(float(np.min(tps_vals)))
        maxs.append(float(np.max(tps_vals)))

    if not scenarios:
        return None

    with plt.rc_context(_CHART_STYLE):
        fig, ax = plt.subplots(figsize=(9, 5))
        x = np.arange(len(scenarios))
        ax.bar(x, avgs, 0.5, color="#4CAF50", label="Avg TPS", zorder=2)
        ax.errorbar(
            x, avgs,
            yerr=[np.array(avgs) - np.array(mins), np.array(maxs) - np.array(avgs)],
            fmt="none", ecolor="#333", capsize=5, linewidth=1.5, zorder=3,
        )
        ax.set_ylabel("Tokens Per Second")
        ax.set_title("Throughput (TPS) by Scenario")
        ax.set_xticks(x)
        ax.set_xticklabels(scenarios)
        ax.set_ylim(bottom=0)

        for i, v in enumerate(avgs):
            ax.text(i, v + 2, f"{v:.1f}", ha="center", fontsize=9, fontweight="bold")

        plt.tight_layout()
        out = figures_dir / filename
        fig.savefig(out, dpi=150)
        plt.close(fig)
    return out


def _generate_comparison_chart(
    results_a: Sequence[ScenarioResult],
    results_b: Sequence[ScenarioResult],
    name_a: str,
    name_b: str,
    figures_dir: Path,
    filename: str = "vs_ttft_tps.png",
) -> Path | None:
    """Generate a side-by-side comparison chart for TTFT and TPS."""
    by_a = {r.scenario: r for r in results_a}
    by_b = {r.scenario: r for r in results_b}
    keys = [k for k in by_a if k in by_b]
    if not keys:
        return None

    scenarios: list[str] = []
    ttft_a: list[float] = []
    ttft_b: list[float] = []
    tps_a: list[float] = []
    tps_b: list[float] = []

    for k in keys:
        ma = _scenario_metrics(by_a[k])
        mb = _scenario_metrics(by_b[k])
        if ma["ttft_p50"] is not None and mb["ttft_p50"] is not None:
            scenarios.append(f"Scenario {k}")
            ttft_a.append(ma["ttft_p50"])
            ttft_b.append(mb["ttft_p50"])
            tps_a.append(ma["tps_avg"] or 0)
            tps_b.append(mb["tps_avg"] or 0)

    if not scenarios:
        return None

    with plt.rc_context(_CHART_STYLE):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        x = np.arange(len(scenarios))
        width = 0.35

        # TTFT chart (lower is better)
        ax1.bar(x - width / 2, ttft_a, width, label=name_a, color="#90CAF9")
        ax1.bar(x + width / 2, ttft_b, width, label=name_b, color="#1565C0")
        ax1.set_ylabel("TTFT P50 (ms)")
        ax1.set_title("Time to First Token — Comparison")
        ax1.set_xticks(x)
        ax1.set_xticklabels(scenarios)
        ax1.legend()
        ax1.set_ylim(bottom=0)
        for bars in ax1.containers:
            ax1.bar_label(bars, fmt="%.0f", fontsize=8, padding=2)

        # TPS chart (higher is better)
        ax2.bar(x - width / 2, tps_a, width, label=name_a, color="#A5D6A7")
        ax2.bar(x + width / 2, tps_b, width, label=name_b, color="#2E7D32")
        ax2.set_ylabel("TPS (avg)")
        ax2.set_title("Throughput — Comparison")
        ax2.set_xticks(x)
        ax2.set_xticklabels(scenarios)
        ax2.legend()
        ax2.set_ylim(bottom=0)
        for bars in ax2.containers:
            ax2.bar_label(bars, fmt="%.1f", fontsize=8, padding=2)

        plt.tight_layout()
        out = figures_dir / filename
        fig.savefig(out, dpi=150)
        plt.close(fig)
    return out


def _generate_error_rate_chart(
    results: Sequence[ScenarioResult],
    figures_dir: Path,
    filename: str = "error_rates.png",
) -> Path | None:
    """Generate a stacked bar chart of success / errors / 429s per scenario."""
    scenarios: list[str] = []
    success: list[int] = []
    errors: list[int] = []
    rate_limited: list[int] = []

    for sr in results:
        if not sr.results:
            continue
        scenarios.append(f"Scenario {sr.scenario}")
        success.append(len(sr.successful))
        errors.append(len(sr.failed) - len(sr.rate_limited))
        rate_limited.append(len(sr.rate_limited))

    if not scenarios:
        return None

    with plt.rc_context(_CHART_STYLE):
        fig, ax = plt.subplots(figsize=(9, 5))
        x = np.arange(len(scenarios))
        width = 0.5
        ax.bar(x, success, width, label="Success", color="#4CAF50")
        ax.bar(x, rate_limited, width, bottom=success, label="429 Rate Limited", color="#FF9800")
        ax.bar(x, errors, width, bottom=np.array(success) + np.array(rate_limited),
               label="Other Errors", color="#F44336")
        ax.set_ylabel("Number of Requests")
        ax.set_title("Request Outcomes by Scenario")
        ax.set_xticks(x)
        ax.set_xticklabels(scenarios)
        ax.legend(loc="upper right")

        plt.tight_layout()
        out = figures_dir / filename
        fig.savefig(out, dpi=150)
        plt.close(fig)
    return out


# ─────────────────────────────────────────────
# Executive Report (long-form Markdown + figures)
# ─────────────────────────────────────────────

def _compute_overall_metrics(results: Sequence[ScenarioResult]) -> dict[str, Any]:
    """Aggregate headline metrics across all scenarios for the TL;DR."""
    all_ok = [r for sr in results for r in sr.successful]
    all_ttfts = [r.ttft_ms for r in all_ok if r.ttft_ms is not None]
    all_tps = [r.tps for r in all_ok]
    total_requests = sum(len(sr.results) for sr in results)
    total_429 = sum(len(sr.rate_limited) for sr in results)
    total_errors = sum(len(sr.failed) for sr in results)
    total_tokens = sum(r.tokens for r in all_ok)

    # Peak achieved TPM across scenarios (best per-scenario aggregate)
    peak_tpm = 0.0
    peak_scenario = ""
    for sr in results:
        ok = sr.successful
        if not ok:
            continue
        tokens = sum(r.tokens for r in ok)
        max_t = max((r.total_seconds for r in ok), default=0.0)
        if max_t >= 1e-3:
            tpm = tokens / max_t * 60
            if tpm > peak_tpm:
                peak_tpm = tpm
                peak_scenario = sr.scenario

    return {
        "total_requests": total_requests,
        "total_success": len(all_ok),
        "total_errors": total_errors,
        "total_429": total_429,
        "total_tokens": total_tokens,
        "ttft_p50": float(np.percentile(all_ttfts, 50)) if all_ttfts else None,
        "ttft_p95": float(np.percentile(all_ttfts, 95)) if all_ttfts else None,
        "ttft_p99": float(np.percentile(all_ttfts, 99)) if all_ttfts else None,
        "tps_avg":  float(np.mean(all_tps)) if all_tps else None,
        "tps_p50":  float(np.percentile(all_tps, 50)) if all_tps else None,
        "peak_tpm": peak_tpm,
        "peak_scenario": peak_scenario,
    }


def _verdict(metrics: dict[str, Any], output_tpm: int) -> tuple[str, str, str]:
    """
    Return (status, icon, one-line rationale) based on overall metrics
    and provisioned quota.
    """
    if metrics["total_429"] > 0:
        pct = metrics["total_429"] / max(1, metrics["total_requests"]) * 100
        return ("THROTTLED", "❌",
                f"{metrics['total_429']} of {metrics['total_requests']} "
                f"requests rate-limited ({pct:.0f}%) — capacity exceeded.")

    if metrics["total_requests"] > 0:
        success_rate = metrics["total_success"] / metrics["total_requests"]
        if success_rate < 0.95:
            return ("DEGRADED", "⚠️",
                    f"Only {success_rate*100:.0f}% success rate "
                    f"({metrics['total_success']}/{metrics['total_requests']}).")

    if output_tpm and metrics["peak_tpm"]:
        util = metrics["peak_tpm"] / output_tpm
        if util >= 1.0:
            return ("OVER QUOTA", "❌",
                    f"Peak achieved {metrics['peak_tpm']:,.0f} TPM "
                    f"({util*100:.0f}% of {output_tpm:,} provisioned).")
        if util >= 0.8:
            return ("NEAR QUOTA", "⚠️",
                    f"Peak achieved {metrics['peak_tpm']:,.0f} TPM "
                    f"({util*100:.0f}% of {output_tpm:,} provisioned).")
        return ("PASS", "✅",
                f"All requests served within capacity "
                f"(peak {util*100:.0f}% of {output_tpm:,} TPM).")

    return ("PASS", "✅", "All requests served successfully.")


def _per_scenario_tpm(sr: ScenarioResult) -> float:
    """Compute aggregate TPM achieved by a scenario."""
    ok = sr.successful
    if not ok:
        return 0.0
    tokens = sum(r.tokens for r in ok)
    max_t = max((r.total_seconds for r in ok), default=0.0)
    return tokens / max_t * 60 if max_t >= 1e-3 else 0.0


def export_executive_report(
    results: Sequence[ScenarioResult],
    output_dir: str | Path,
    config: Any = None,
    compare_results: Sequence[ScenarioResult] | None = None,
    compare_config: Any = None,
    compare_name: str = "",
    primary_name: str = "",
    filename: str = "executive_report.md",
    chart_prefix: str = "",
) -> Path:
    """
    Export a detailed executive benchmark report as Markdown with figures.

    Generates matplotlib charts (TTFT percentiles, TPS throughput, error rates,
    and comparison charts when two result sets are provided) and embeds them
    in the Markdown report.

    The ``chart_prefix`` parameter is prepended to all chart filenames so the
    comparison report can coexist with a standalone report in the same folder
    without overwriting each other's PNGs.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    # Create figures subfolder
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures_rel = "figures"  # relative path for markdown references

    # ── Generate all charts ────────────────────────────────────
    # Resolve model display names for comparison
    cmp_model = _get_model_display_name(compare_config, fallback=compare_name) if compare_results else ""
    pri_model = _get_model_display_name(config, fallback=primary_name) if compare_results else ""

    ttft_chart_name = f"{chart_prefix}ttft_percentiles.png"
    tps_chart_name = f"{chart_prefix}tps_throughput.png"
    error_chart_name = f"{chart_prefix}error_rates.png"
    comparison_chart_name = f"{chart_prefix}vs_ttft_tps.png"

    ttft_chart = _generate_ttft_chart(results, figures_dir, filename=ttft_chart_name)
    tps_chart = _generate_tps_chart(results, figures_dir, filename=tps_chart_name)
    error_chart = _generate_error_rate_chart(results, figures_dir, filename=error_chart_name)
    comparison_chart = None
    if compare_results is not None:
        comparison_chart = _generate_comparison_chart(
            compare_results, results, cmp_model, pri_model, figures_dir,
            filename=comparison_chart_name,
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    # Resolve quota / pricing for downstream sections
    proj = getattr(config, "project", None) if config else None
    output_tpm = int(getattr(proj, "output_tpm", 0) or 0) if proj else 0
    input_tpm = int(getattr(proj, "input_tpm", 0) or 0) if proj else 0
    hourly_price = float(getattr(proj, "hourly_price", 0.0) or 0.0) if proj else 0.0

    overall = _compute_overall_metrics(results)
    status, icon, rationale = _verdict(overall, output_tpm)

    # ── Header ──────────────────────────────────────────────────
    lines.append("# PTU Benchmark — Executive Report")
    lines.append("")
    lines.append(f"**Date:** {now}")
    if config:
        if proj:
            lines.append(f"**Service:** {proj.service_name}")
            lines.append(f"**Model:** {proj.model_name} ({proj.model_code})")
            lines.append(f"**Deployment:** {proj.deployment_id}")
            lines.append(f"**Quota:** {proj.input_tpm:,} input TPM / {proj.output_tpm:,} output TPM")
            lines.append(f"**Billing:** {proj.billing_method}")
            if proj.hourly_price > 0:
                lines.append(f"**Hourly Price:** ${proj.hourly_price:.2f}/hour")
        else:
            lines.append(f"**Model ID:** {getattr(config, 'model_id', 'N/A')}")
        lines.append(f"**Base URL:** {getattr(config, 'base_url', 'N/A')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── TL;DR ──────────────────────────────────────────────────
    lines.append("## TL;DR")
    lines.append("")
    lines.append(f"> {icon} **Verdict: {status}** — {rationale}")
    lines.append("")

    tldr_bullets: list[str] = []
    if overall["ttft_p50"] is not None:
        tldr_bullets.append(
            f"**Latency:** TTFT P50 = {overall['ttft_p50']:.0f} ms, "
            f"P95 = {overall['ttft_p95']:.0f} ms, P99 = {overall['ttft_p99']:.0f} ms "
            f"(across {overall['total_success']} successful requests)."
        )
    if overall["tps_avg"] is not None:
        tldr_bullets.append(
            f"**Throughput:** Avg {overall['tps_avg']:.1f} tok/s per request; "
            f"peak aggregate {overall['peak_tpm']:,.0f} TPM "
            f"(in Scenario {overall['peak_scenario']})."
        )
    tldr_bullets.append(
        f"**Reliability:** {overall['total_success']}/{overall['total_requests']} succeeded "
        f"({overall['total_success']/max(1, overall['total_requests'])*100:.0f}%); "
        f"{overall['total_429']} rate-limited (429), "
        f"{overall['total_errors'] - overall['total_429']} other errors."
    )
    if output_tpm and overall["peak_tpm"]:
        util_pct = overall["peak_tpm"] / output_tpm * 100
        headroom = max(0.0, output_tpm - overall["peak_tpm"])
        tldr_bullets.append(
            f"**Quota:** Peak utilization {util_pct:.0f}% of "
            f"{output_tpm:,} provisioned output TPM ({headroom:,.0f} TPM headroom)."
        )
    if hourly_price > 0:
        # Effective $ / M output tokens, based on observed peak throughput
        if overall["peak_tpm"] and overall["peak_tpm"] > 0:
            cost_per_m = hourly_price / (overall["peak_tpm"] * 60 / 1_000_000)
            tldr_bullets.append(
                f"**Cost:** ${hourly_price:.2f}/hour "
                f"(~${hourly_price * 24:.0f}/day, ~${hourly_price * 24 * 30:,.0f}/month); "
                f"effective ~${cost_per_m:,.2f} per M output tokens at peak throughput."
            )
        else:
            tldr_bullets.append(
                f"**Cost:** ${hourly_price:.2f}/hour "
                f"(~${hourly_price * 24:.0f}/day, ~${hourly_price * 24 * 30:,.0f}/month)."
            )
    tldr_bullets.append(
        f"**Total volume:** {overall['total_tokens']:,} tokens generated across "
        f"{len(results)} scenarios."
    )

    for bullet in tldr_bullets:
        lines.append(f"- {bullet}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Summary Table ───────────────────────────────────────────
    lines.append("## 1. Summary")
    lines.append("")

    summary_rows: list[list[str]] = []
    for sr in results:
        ok = sr.successful
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        total_tokens = sum(r.tokens for r in ok)
        max_time = max((r.total_seconds for r in ok), default=0.0)
        est_tpm = total_tokens / max_time * 60 if max_time >= 1e-3 else 0

        label = f"{sr.scenario}: {sr.label}"
        summary_rows.append([
            label,
            str(len(sr.results)),
            str(len(ok)),
            str(len(sr.failed)),
            str(len(sr.rate_limited)),
            f"{np.percentile(ttfts, 50):.0f} ms" if ttfts else "—",
            f"{np.percentile(ttfts, 99):.0f} ms" if ttfts else "—",
            f"{np.mean(tps_vals):.1f}" if tps_vals else "—",
            f"{est_tpm:,.0f}" if est_tpm else "—",
        ])

    summary_headers = [
        "Scenario", "Total", "Success", "Errors", "429s",
        "TTFT P50", "TTFT P99", "TPS Avg", "Est. TPM",
    ]
    lines.append(tabulate(summary_rows, headers=summary_headers, tablefmt="pipe"))
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Figures: Overview Charts ────────────────────────────────
    lines.append("## 2. Performance Overview")
    lines.append("")

    if ttft_chart:
        lines.append("### Time to First Token (TTFT)")
        lines.append("")
        lines.append("TTFT measures perceived responsiveness — how quickly the first token appears. "
                      "Lower is better. P50 represents the median experience; P99 shows worst-case latency.")
        lines.append("")
        lines.append(f"![TTFT Percentiles]({figures_rel}/{ttft_chart_name})")
        lines.append("")

    if tps_chart:
        lines.append("### Throughput (TPS)")
        lines.append("")
        lines.append("Tokens Per Second measures generation speed after the first token arrives. "
                      "Higher is better. Error bars show min/max range across requests.")
        lines.append("")
        lines.append(f"![TPS Throughput]({figures_rel}/{tps_chart_name})")
        lines.append("")

    if error_chart:
        lines.append("### Request Outcomes")
        lines.append("")
        lines.append("Breakdown of successful requests, rate-limited (HTTP 429) responses, "
                      "and other errors per scenario. PTU should show zero 429s within provisioned capacity.")
        lines.append("")
        lines.append(f"![Error Rates]({figures_rel}/{error_chart_name})")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Quota Utilization Analysis ──────────────────────────────
    lines.append("## 3. Quota Utilization Analysis")
    lines.append("")
    if output_tpm:
        lines.append(
            f"This section compares achieved aggregate throughput against the "
            f"provisioned **{output_tpm:,} output TPM** quota for this deployment. "
            f"The status thresholds are: ✅ OK (<80%), ⚠️ NEAR QUOTA (80–100%), "
            f"❌ OVER QUOTA (≥100%), ❌ THROTTLED (any 429 responses)."
        )
        lines.append("")

        util_rows: list[list[str]] = []
        for sr in results:
            ok = sr.successful
            if not ok:
                util_rows.append([
                    f"{sr.scenario}: {sr.label}",
                    "—", f"{output_tpm:,}", "—", str(len(sr.rate_limited)),
                    "❌ NO DATA",
                ])
                continue
            agg_tpm = _per_scenario_tpm(sr)
            util_pct = agg_tpm / output_tpm * 100 if output_tpm else 0.0
            if len(sr.rate_limited) > 0:
                status_cell = "❌ THROTTLED"
            elif util_pct >= 100:
                status_cell = "❌ OVER QUOTA"
            elif util_pct >= 80:
                status_cell = "⚠️ NEAR QUOTA"
            else:
                status_cell = "✅ OK"
            util_rows.append([
                f"{sr.scenario}: {sr.label}",
                f"{agg_tpm:,.0f}",
                f"{output_tpm:,}",
                f"{util_pct:.1f}%",
                str(len(sr.rate_limited)),
                status_cell,
            ])
        util_headers = ["Scenario", "Achieved TPM", "Quota TPM",
                        "Util %", "429s", "Status"]
        lines.append(tabulate(util_rows, headers=util_headers, tablefmt="pipe"))
        lines.append("")

        if overall["peak_tpm"]:
            headroom = max(0.0, output_tpm - overall["peak_tpm"])
            headroom_pct = headroom / output_tpm * 100
            lines.append(f"**Peak observed:** {overall['peak_tpm']:,.0f} TPM "
                          f"in Scenario {overall['peak_scenario']} "
                          f"({overall['peak_tpm']/output_tpm*100:.1f}% of quota).  ")
            lines.append(f"**Headroom:** {headroom:,.0f} TPM ({headroom_pct:.1f}%) "
                          f"unused at peak.")
            lines.append("")
    else:
        lines.append("> _Quota utilization analysis unavailable — no `output_tpm` "
                      "configured on this project._")
        lines.append("")
    lines.append("---")
    lines.append("")

    # ── Per-scenario details ────────────────────────────────────
    lines.append("## 4. Scenario Details")
    lines.append("")

    for sr in results:
        ok = sr.successful
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        durations = [r.total_seconds for r in ok if r.total_seconds > 0]
        token_counts = [r.tokens for r in ok if r.tokens > 0]
        total_tokens = sum(r.tokens for r in ok)
        wall_clock = max(durations, default=0.0)
        agg_tpm = total_tokens / wall_clock * 60 if wall_clock >= 1e-3 else 0

        lines.append(f"### Scenario {sr.scenario}: {sr.label}")
        lines.append("")
        lines.append(f"- **Total requests:** {len(sr.results)}")
        lines.append(f"- **Successful:** {len(ok)} "
                      f"({len(ok)/max(1, len(sr.results))*100:.1f}%)")
        lines.append(f"- **Errors:** {len(sr.failed)}")
        lines.append(f"- **Rate limited (429):** {len(sr.rate_limited)}")
        lines.append(f"- **Total tokens generated:** {total_tokens:,}")
        if wall_clock > 0:
            lines.append(f"- **Wall-clock duration (slowest request):** {wall_clock:.2f} s")
            lines.append(f"- **Aggregate TPM achieved:** {agg_tpm:,.0f}")
            if output_tpm:
                lines.append(f"- **Quota utilization:** "
                              f"{agg_tpm / output_tpm * 100:.1f}% "
                              f"of {output_tpm:,} provisioned output TPM")
        if hourly_price > 0 and total_tokens > 0:
            scenario_cost = hourly_price * (wall_clock / 3600) if wall_clock > 0 else 0.0
            cost_per_m = (scenario_cost / total_tokens * 1_000_000) if total_tokens > 0 and scenario_cost > 0 else 0.0
            lines.append(f"- **Estimated cost (this scenario):** ${scenario_cost:,.4f} "
                          f"(${cost_per_m:,.2f} per M tokens)")
        lines.append("")

        # ── Latency distribution ────────────────────────────────
        if ttfts:
            lines.append("**Time to First Token (TTFT):**")
            lines.append("")
            lines.append("| Percentile | Value |")
            lines.append("|------------|-------|")
            lines.append(f"| Min | {np.min(ttfts):.0f} ms |")
            lines.append(f"| P50 (median) | {np.percentile(ttfts, 50):.0f} ms |")
            lines.append(f"| P75 | {np.percentile(ttfts, 75):.0f} ms |")
            lines.append(f"| P90 | {np.percentile(ttfts, 90):.0f} ms |")
            lines.append(f"| P95 | {np.percentile(ttfts, 95):.0f} ms |")
            lines.append(f"| P99 | {np.percentile(ttfts, 99):.0f} ms |")
            lines.append(f"| Max | {np.max(ttfts):.0f} ms |")
            lines.append(f"| Mean | {np.mean(ttfts):.0f} ms |")
            lines.append(f"| Std Dev | {np.std(ttfts):.0f} ms |")
            lines.append("")

        # ── Throughput distribution ─────────────────────────────
        if tps_vals:
            lines.append("**Throughput (Tokens/Second per request):**")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Min | {np.min(tps_vals):.1f} tok/s |")
            lines.append(f"| Median | {np.median(tps_vals):.1f} tok/s |")
            lines.append(f"| Average | {np.mean(tps_vals):.1f} tok/s |")
            lines.append(f"| P95 | {np.percentile(tps_vals, 95):.1f} tok/s |")
            lines.append(f"| Max | {np.max(tps_vals):.1f} tok/s |")
            lines.append(f"| Std Dev | {np.std(tps_vals):.1f} tok/s |")
            lines.append("")

        # ── Request duration distribution ───────────────────────
        if durations:
            lines.append("**Request Duration (end-to-end):**")
            lines.append("")
            lines.append("| Percentile | Value |")
            lines.append("|------------|-------|")
            lines.append(f"| Min | {np.min(durations):.2f} s |")
            lines.append(f"| P50 | {np.percentile(durations, 50):.2f} s |")
            lines.append(f"| P95 | {np.percentile(durations, 95):.2f} s |")
            lines.append(f"| P99 | {np.percentile(durations, 99):.2f} s |")
            lines.append(f"| Max | {np.max(durations):.2f} s |")
            lines.append(f"| Mean | {np.mean(durations):.2f} s |")
            lines.append("")

        # ── Tokens per request distribution ─────────────────────
        if token_counts:
            lines.append("**Tokens per Request:**")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Min | {np.min(token_counts):,} |")
            lines.append(f"| Median | {np.median(token_counts):,.0f} |")
            lines.append(f"| Mean | {np.mean(token_counts):,.0f} |")
            lines.append(f"| Max | {np.max(token_counts):,} |")
            lines.append("")

        # ── Error breakdown ─────────────────────────────────────
        if sr.failed:
            err_counter: dict[str, int] = {}
            for r in sr.failed:
                key = r.error or "unknown"
                err_counter[key] = err_counter.get(key, 0) + 1
            lines.append("**Error Breakdown:**")
            lines.append("")
            lines.append("| Error type | Count |")
            lines.append("|------------|-------|")
            for err_type, count in sorted(err_counter.items(), key=lambda x: -x[1]):
                lines.append(f"| `{err_type}` | {count} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── A/B comparison section ──────────────────────────────────
    if compare_results is not None:
        section_num = 5

        lines.append(f"## {section_num}. Comparison Analysis")
        lines.append("")
        lines.append(f"**Baseline:** {cmp_model}  ")
        lines.append(f"**Subject:** {pri_model}")
        lines.append("")

        if comparison_chart:
            lines.append("### Visual Comparison")
            lines.append("")
            lines.append("Side-by-side comparison of TTFT (lower is better) and TPS (higher is better). "
                          "The delta column shows percentage improvement of the subject over the baseline.")
            lines.append("")
            lines.append(f"![Comparison Chart]({figures_rel}/{comparison_chart_name})")
            lines.append("")

        by_key_a = {r.scenario: r for r in compare_results}
        by_key_b = {r.scenario: r for r in results}
        keys = [k for k in by_key_a if k in by_key_b]

        for key in keys:
            sr_a, sr_b = by_key_a[key], by_key_b[key]
            ma = _scenario_metrics(sr_a)
            mb = _scenario_metrics(sr_b)

            lines.append(f"### Scenario {key}")
            lines.append("")
            lines.append("| Metric | " + cmp_model + " | " + pri_model + " | Δ |")
            lines.append("|--------|------|------|---|")

            def _cmp_row(metric_label: str, a_val: float | None, b_val: float | None,
                         suffix: str, lower_is_better: bool) -> str:
                a_str = "—" if a_val is None else f"{a_val:.0f}{suffix}" if suffix == "ms" else f"{a_val:,.0f}{suffix}"
                b_str = "—" if b_val is None else f"{b_val:.0f}{suffix}" if suffix == "ms" else f"{b_val:,.0f}{suffix}"
                delta = _delta(a_val, b_val, lower_is_better=lower_is_better)
                return f"| {metric_label} | {a_str} | {b_str} | {delta} |"

            lines.append(_cmp_row("TTFT P50", ma["ttft_p50"], mb["ttft_p50"], "ms", True))
            lines.append(_cmp_row("TTFT P99", ma["ttft_p99"], mb["ttft_p99"], "ms", True))
            lines.append(_cmp_row("TPS Avg", ma["tps_avg"], mb["tps_avg"], " tok/s", False))
            lines.append(_cmp_row("Est. TPM", ma["tpm"], mb["tpm"], "", False))
            lines.append(f"| 429s | {ma['rate_limited']} | {mb['rate_limited']} | |")
            lines.append(f"| Errors | {ma['errors']} | {mb['errors']} | |")
            lines.append("")

        lines.append("---")
        lines.append("")
    else:
        section_num = 4

    # ── Findings ────────────────────────────────────────────────
    lines.append(f"## {section_num + 1}. Key Findings")
    lines.append("")

    for sr in results:
        ok = sr.successful
        if not ok:
            lines.append(f"- **Scenario {sr.scenario}:** All {len(sr.results)} requests failed.")
            continue
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        rate_limited_count = len(sr.rate_limited)
        total = len(sr.results)

        finding = f"- **Scenario {sr.scenario} ({sr.label}):** "
        parts: list[str] = []
        if ttfts:
            parts.append(f"TTFT P50={np.percentile(ttfts, 50):.0f}ms")
        if tps_vals:
            parts.append(f"avg TPS={np.mean(tps_vals):.1f}")
        parts.append(f"{len(ok)}/{total} succeeded")
        if rate_limited_count > 0:
            parts.append(f"{rate_limited_count} rate-limited (429)")
        finding += ", ".join(parts) + "."
        lines.append(finding)

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Cost Analysis ───────────────────────────────────────────
    section_num += 2
    if hourly_price > 0:
        lines.append(f"## {section_num}. Cost Analysis")
        lines.append("")
        lines.append(f"Provisioned cost is fixed at **${hourly_price:.2f}/hour** regardless "
                      "of utilization. Effective per-token cost depends on how fully the "
                      "quota is used — higher utilization yields better unit economics.")
        lines.append("")
        lines.append("**Fixed costs:**")
        lines.append("")
        lines.append("| Period | Cost |")
        lines.append("|--------|------|")
        lines.append(f"| Hourly | ${hourly_price:,.2f} |")
        lines.append(f"| Daily | ${hourly_price * 24:,.2f} |")
        lines.append(f"| Weekly | ${hourly_price * 24 * 7:,.2f} |")
        lines.append(f"| Monthly (30d) | ${hourly_price * 24 * 30:,.2f} |")
        lines.append(f"| Annual | ${hourly_price * 24 * 365:,.2f} |")
        lines.append("")

        # Effective $/M tokens at different utilization levels
        if output_tpm:
            lines.append("**Effective unit cost (output tokens) by utilization:**")
            lines.append("")
            lines.append("| Utilization | Effective TPM | $/hour | $/M tokens |")
            lines.append("|-------------|---------------|--------|------------|")
            for pct in (25, 50, 75, 100):
                eff_tpm = output_tpm * pct / 100
                tokens_per_hour = eff_tpm * 60
                cost_per_m = (hourly_price / tokens_per_hour * 1_000_000) if tokens_per_hour > 0 else 0.0
                lines.append(f"| {pct}% | {eff_tpm:,.0f} | ${hourly_price:.2f} | ${cost_per_m:,.2f} |")
            lines.append("")
            lines.append("> _Lower $/M-tokens = better unit economics. PTU pricing favors "
                          "high-utilization workloads — under-utilization wastes provisioned capacity._")
            lines.append("")

        # Observed effective cost
        if overall["peak_tpm"] and overall["peak_tpm"] > 0:
            observed_cost_per_m = hourly_price / (overall["peak_tpm"] * 60 / 1_000_000)
            lines.append(f"**Observed (this run):** Peak {overall['peak_tpm']:,.0f} TPM "
                          f"⇒ effective **${observed_cost_per_m:,.2f} / M output tokens**.")
            lines.append("")

        lines.append("---")
        lines.append("")
    else:
        section_num -= 1  # no cost section, hold the counter

    # ── Recommendations ─────────────────────────────────────────
    section_num += 1
    lines.append(f"## {section_num}. Recommendations")
    lines.append("")
    recs: list[str] = []

    if overall["total_429"] > 0:
        recs.append(
            f"**Capacity:** {overall['total_429']} requests were rate-limited. "
            "Either reduce concurrency, batch requests more aggressively, or "
            "request a higher TPM quota for this deployment."
        )
    if output_tpm and overall["peak_tpm"]:
        util = overall["peak_tpm"] / output_tpm
        if util < 0.4:
            recs.append(
                f"**Right-sizing:** Peak utilization was only {util*100:.0f}% of "
                f"the {output_tpm:,} output TPM quota. Consider down-sizing the "
                "provisioned tier to improve unit economics, or routing more traffic "
                "to this deployment."
            )
        elif util > 0.85 and overall["total_429"] == 0:
            recs.append(
                f"**Scaling headroom:** Peak utilization reached {util*100:.0f}% of quota. "
                "Plan for additional capacity if traffic is expected to grow."
            )
    if overall["ttft_p99"] and overall["ttft_p50"]:
        ratio = overall["ttft_p99"] / overall["ttft_p50"]
        if ratio > 3.0:
            recs.append(
                f"**Tail latency:** P99/P50 ratio is {ratio:.1f}× — significant tail "
                "latency suggests queueing or contention. Investigate request patterns "
                "during high-percentile windows or consider streaming optimizations."
            )
    if hourly_price > 0 and output_tpm and overall["peak_tpm"]:
        # Threshold: if effective $/M is meaningfully higher than break-even token-API rate
        observed_cost_per_m = hourly_price / (overall["peak_tpm"] * 60 / 1_000_000)
        if observed_cost_per_m > 50:
            recs.append(
                f"**Cost efficiency:** Observed ${observed_cost_per_m:,.2f}/M tokens at "
                "peak. Increasing utilization (more concurrent requests) is the primary "
                "lever to lower unit cost on a fixed PTU contract."
            )

    if not recs:
        recs.append("All metrics within healthy ranges — no immediate action required. "
                    "Continue monitoring tail latency and quota utilization during "
                    "production traffic peaks.")

    for rec in recs:
        lines.append(f"- {rec}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Test Configuration ──────────────────────────────────────
    section_num += 1
    lines.append(f"## {section_num}. Test Configuration")
    lines.append("")
    lines.append("| Setting | Value |")
    lines.append("|---------|-------|")
    if proj:
        lines.append(f"| Service | {proj.service_name} |")
        lines.append(f"| Model | {proj.model_name} |")
        lines.append(f"| Model Code | {proj.model_code} |")
        lines.append(f"| Deployment | {proj.deployment_id} |")
        lines.append(f"| Input TPM Quota | {input_tpm:,} |")
        lines.append(f"| Output TPM Quota | {output_tpm:,} |")
        lines.append(f"| Billing Method | {proj.billing_method} |")
        lines.append(f"| Hourly Price | ${hourly_price:.2f} |")
    if config:
        model_id = getattr(config, "model_id", "")
        if model_id:
            lines.append(f"| Model ID | `{model_id}` |")
        base_url = getattr(config, "base_url", "")
        if base_url:
            lines.append(f"| Base URL | `{base_url}` |")
        for attr, label in [
            ("max_tokens", "Max Tokens"),
            ("temperature", "Temperature"),
            ("concurrent_max_tokens", "Concurrent Max Tokens"),
            ("sustained_duration", "Sustained Duration (s)"),
            ("sustained_concurrency", "Sustained Concurrency"),
            ("burst_size", "Burst Size"),
        ]:
            val = getattr(config, attr, None)
            if val is not None:
                lines.append(f"| {label} | {val} |")
        # Concurrency levels
        levels = getattr(config, "concurrency_levels", None)
        if levels:
            auto = getattr(config, "concurrency_levels_auto_derived", False)
            label = "Concurrency Levels (auto-derived)" if auto else "Concurrency Levels"
            lines.append(f"| {label} | {levels} |")
    lines.append(f"| Report generated | {now} |")
    lines.append(f"| Total scenarios | {len(results)} |")
    lines.append(f"| Total requests | {overall['total_requests']:,} |")
    lines.append(f"| Total tokens | {overall['total_tokens']:,} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by PTU Benchmark Suite.*")

    out_path.write_text("\n".join(lines))
    return out_path


# ─────────────────────────────────────────────
# One-page Business Report (DOCX)
# ─────────────────────────────────────────────

def _add_docx_table(doc: Document, headers: list[str], rows: list[list[str]],
                    col_widths: list[float] | None = None) -> None:
    """Add a formatted table to a DOCX document."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Light Shading Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(8)

    # Data rows
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = str(val)
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.size = Pt(8)

    if col_widths:
        for i, width in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Cm(width)


def _add_explanation(doc: Document, text: str) -> None:
    """Add a small italic explanation paragraph."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)


def export_business_report(
    results: Sequence[ScenarioResult],
    output_dir: str | Path,
    config: Any = None,
    compare_results: Sequence[ScenarioResult] | None = None,
    compare_config: Any = None,
    compare_name: str = "",
    primary_name: str = "",
    filename: str = "business_report.docx",
) -> Path:
    """
    Export a concise one-page business report as DOCX.

    Designed to fit on a single printed page — headline metrics with explanations,
    a compact comparison table, key takeaways, and cost summary.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Build document ──────────────────────────────────────────
    doc = Document()

    # Page margins (narrow for one-page fit)
    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    # ── Title ───────────────────────────────────────────────────
    title = doc.add_heading("PTU Benchmark — Business Summary", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.size = Pt(18)

    # Subtitle with model info
    model_display = ""
    if config:
        proj = getattr(config, "project", None)
        if proj:
            model_display = f"{proj.model_name} ({proj.model_code})"
        else:
            model_display = getattr(config, "model_id", "N/A")

    if compare_results is not None:
        cmp_model = _get_model_display_name(compare_config, fallback=compare_name)
        pri_model = _get_model_display_name(config, fallback=primary_name)
        subtitle_text = f"Date: {now}  |  {pri_model}  vs  {cmp_model}"
    else:
        subtitle_text = f"Date: {now}  |  Model: {model_display}"

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(subtitle_text)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # ── Headline Metrics ────────────────────────────────────────
    doc.add_heading("Headline Metrics", level=2)

    scenario_a = next((r for r in results if r.scenario == "A"), None)
    metric_rows: list[list[str]] = []
    if scenario_a and scenario_a.successful:
        ok = scenario_a.successful
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        total_tokens = sum(r.tokens for r in ok)
        max_time = max((r.total_seconds for r in ok), default=0.0)
        est_tpm = total_tokens / max_time * 60 if max_time >= 1e-3 else 0

        if ttfts:
            metric_rows.append(["Time to First Token (P50)", f"{np.percentile(ttfts, 50):.0f} ms",
                                "Median time until the first word appears"])
            metric_rows.append(["Time to First Token (P99)", f"{np.percentile(ttfts, 99):.0f} ms",
                                "Worst-case first-token latency"])
        if tps_vals:
            metric_rows.append(["Avg Throughput", f"{np.mean(tps_vals):.1f} tok/s",
                                "Average generation speed after first token"])
        metric_rows.append(["Est. TPM", f"{est_tpm:,.0f}",
                            "Estimated tokens processed per minute"])
        metric_rows.append(["Success Rate",
                            f"{len(ok)}/{len(scenario_a.results)} ({len(ok)/len(scenario_a.results)*100:.0f}%)",
                            "Percentage of requests completed without error"])

    _add_docx_table(doc, ["Metric", "Value", "What It Means"], metric_rows)

    _add_explanation(doc,
        "TTFT (Time to First Token) measures perceived responsiveness — how fast the user sees "
        "the first word. TPS (Tokens Per Second) measures generation speed — how fast the full "
        "response is delivered. TPM (Tokens Per Minute) measures sustained processing capacity.")

    # ── Scenario Overview ───────────────────────────────────────
    doc.add_heading("Scenario Overview", level=2)

    overview_rows: list[list[str]] = []
    for sr in results:
        ok = sr.successful
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        overview_rows.append([
            sr.scenario,
            sr.label[:30],
            f"{len(ok)}/{len(sr.results)}",
            str(len(sr.rate_limited)),
            f"{np.percentile(ttfts, 50):.0f}ms" if ttfts else "—",
            f"{np.mean(tps_vals):.0f}" if tps_vals else "—",
        ])

    _add_docx_table(doc, ["#", "Scenario", "Success", "429s", "TTFT P50", "TPS"], overview_rows)

    _add_explanation(doc,
        "Each scenario tests a different aspect: A = single request baseline, "
        "B = concurrent load, C = sustained 30-min throughput, D = peak burst, E = long context. "
        "429s are HTTP rate-limit errors — zero means the system handled all traffic within capacity.")

    # ── Comparison table (if available) ─────────────────────────
    if compare_results is not None:
        cmp_model = _get_model_display_name(compare_config, fallback=compare_name)
        pri_model = _get_model_display_name(config, fallback=primary_name)

        doc.add_heading(f"Comparison: {pri_model} vs {cmp_model}", level=2)

        by_key_a = {r.scenario: r for r in compare_results}
        by_key_b = {r.scenario: r for r in results}
        keys = [k for k in by_key_a if k in by_key_b]

        cmp_rows: list[list[str]] = []
        for key in keys:
            ma = _scenario_metrics(by_key_a[key])
            mb = _scenario_metrics(by_key_b[key])
            cmp_rows.append([
                key,
                "—" if ma["ttft_p50"] is None else f"{ma['ttft_p50']:.0f}ms",
                "—" if mb["ttft_p50"] is None else f"{mb['ttft_p50']:.0f}ms",
                _delta(ma["ttft_p50"], mb["ttft_p50"], lower_is_better=True),
                "—" if ma["tps_avg"] is None else f"{ma['tps_avg']:.0f}",
                "—" if mb["tps_avg"] is None else f"{mb['tps_avg']:.0f}",
                _delta(ma["tps_avg"], mb["tps_avg"], lower_is_better=False),
            ])

        _add_docx_table(doc,
            ["Sc", f"{cmp_model}\nTTFT", f"{pri_model}\nTTFT", "Δ",
             f"{cmp_model}\nTPS", f"{pri_model}\nTPS", "Δ"],
            cmp_rows)

        _add_explanation(doc,
            "Δ (delta) shows percentage improvement. For TTFT, a positive delta means the subject "
            "is faster. For TPS, a positive delta means higher throughput. "
            "These numbers directly translate to user experience and capacity headroom.")

    # ── Key Takeaways ───────────────────────────────────────────
    doc.add_heading("Key Takeaways", level=2)

    total_success = sum(len(r.successful) for r in results)
    total_requests = sum(len(r.results) for r in results)
    total_429 = sum(len(r.rate_limited) for r in results)

    if total_requests > 0:
        success_pct = total_success / total_requests * 100
        p = doc.add_paragraph()
        run = p.add_run("Reliability: ")
        run.bold = True
        run.font.size = Pt(9)
        run = p.add_run(f"{success_pct:.0f}% overall success rate ({total_success}/{total_requests} requests). ")
        run.font.size = Pt(9)
        if total_429 > 0:
            run = p.add_run(f"{total_429} requests were rate-limited (HTTP 429), "
                            "indicating traffic exceeded provisioned capacity.")
        else:
            run = p.add_run("Zero rate-limit errors — all traffic was served within guaranteed capacity.")
        run.font.size = Pt(9)

    if scenario_a and scenario_a.successful:
        ok = scenario_a.successful
        tps_vals = [r.tps for r in ok]
        if tps_vals:
            p = doc.add_paragraph()
            run = p.add_run("Performance: ")
            run.bold = True
            run.font.size = Pt(9)
            run = p.add_run(f"Average generation speed of {np.mean(tps_vals):.1f} tokens/second. "
                            "This determines how fast complete responses are delivered to end users.")
            run.font.size = Pt(9)

    if compare_results is not None:
        cmp_a = next((r for r in compare_results if r.scenario == "A"), None)
        cmp_b = next((r for r in results if r.scenario == "A"), None)
        if cmp_a and cmp_b:
            ma = _scenario_metrics(cmp_a)
            mb = _scenario_metrics(cmp_b)
            if ma["ttft_p50"] and mb["ttft_p50"]:
                improvement = (ma["ttft_p50"] - mb["ttft_p50"]) / ma["ttft_p50"] * 100
                direction = "faster" if improvement > 0 else "slower"
                pri_model = _get_model_display_name(config, fallback=primary_name)
                cmp_model = _get_model_display_name(compare_config, fallback=compare_name)
                p = doc.add_paragraph()
                run = p.add_run("vs Baseline: ")
                run.bold = True
                run.font.size = Pt(9)
                run = p.add_run(f"{pri_model} is {abs(improvement):.0f}% {direction} "
                                f"than {cmp_model} (TTFT P50). "
                                "This is the performance uplift from dedicated provisioned capacity.")
                run.font.size = Pt(9)

    # ── Cost (if available) ─────────────────────────────────────
    if config:
        proj = getattr(config, "project", None)
        if proj and proj.hourly_price > 0:
            doc.add_heading("Cost Summary", level=2)
            cost_rows = [
                ["Hourly", f"${proj.hourly_price:.2f}"],
                ["Daily (est.)", f"${proj.hourly_price * 24:.2f}"],
                ["Monthly (est.)", f"${proj.hourly_price * 24 * 30:,.2f}"],
            ]
            if proj.input_tpm and proj.output_tpm:
                cost_rows.append(["Input TPM Quota", f"{proj.input_tpm:,}"])
                cost_rows.append(["Output TPM Quota", f"{proj.output_tpm:,}"])
            _add_docx_table(doc, ["Period", "Cost"], cost_rows)

    # ── Footer ──────────────────────────────────────────────────
    footer_p = doc.add_paragraph()
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer_p.add_run("PTU Benchmark Suite — Confidential")
    run.font.size = Pt(7)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    run.italic = True

    doc.save(str(out_path))
    return out_path
