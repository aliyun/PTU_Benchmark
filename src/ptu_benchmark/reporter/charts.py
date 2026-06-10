"""Matplotlib chart generation for benchmark reports."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for report generation
import matplotlib.pyplot as plt
import numpy as np

from ptu_benchmark.utils import ScenarioResult

from .utils import _CHART_STYLE, _scenario_metrics


def generate_ttft_chart(
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


def generate_tps_chart(
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


def generate_comparison_chart(
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


def generate_error_rate_chart(
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
