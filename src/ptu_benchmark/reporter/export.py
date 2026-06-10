"""JSON and CSV export helpers for benchmark results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from ptu_benchmark.utils import ScenarioResult

from .utils import _scenario_metrics


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
