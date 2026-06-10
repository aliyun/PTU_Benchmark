"""Shared helpers used across reporter sub-modules."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ptu_benchmark.utils import ScenarioResult


_CHART_STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": "#f8f9fa",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 10,
}


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
    Build a dated report folder: ``{base}/{YYYYMMDD}_{model}_{NNN}/``.

    Auto-increments the 3-digit sequence if the folder already exists.
    The folder is returned directly (no nested ``results/`` subfolder).

    Parameters
    ----------
    base_dir:
        Root reports directory (e.g. ``reports/``).
    model_name:
        Primary model identifier (will be sanitized).
    compare_with:
        Optional second model name — accepted for API compatibility but
        no longer included in the folder name.

    Returns
    -------
    Path to the dated bundle folder.
    """
    base = Path(base_dir)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    primary = _sanitize_model_name(model_name)
    prefix = f"{today}_{primary}_"

    # Find next available sequence number
    seq = 1
    while True:
        folder_name = f"{prefix}{seq:03d}"
        candidate = base / folder_name
        if not candidate.exists():
            break
        seq += 1

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _scenario_display_name(scenario_key: str) -> str:
    """
    Look up the human-readable ``display_name`` for a scenario key
    (e.g. ``"A"`` → ``"Latency Baseline"``).

    Returns an empty string when the scenario is unknown or when the
    class has no ``display_name`` defined. Importing lazily avoids a
    circular import between the reporter and the scenarios package.
    """
    try:
        from ptu_benchmark.scenarios import SCENARIOS  # local import
    except Exception:
        return ""
    cls = SCENARIOS.get(scenario_key)
    if cls is None:
        return ""
    return getattr(cls, "display_name", "") or ""


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
