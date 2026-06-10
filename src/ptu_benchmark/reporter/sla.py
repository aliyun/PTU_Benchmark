"""SLA compliance scoring for benchmark results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from ptu_benchmark.utils import ScenarioResult


@dataclass
class SLATarget:
    """A single SLA threshold definition."""

    name: str               # Human-readable name (e.g., "Availability")
    metric: str             # Internal metric key
    threshold: float        # Target value
    direction: str          # "min" (value must be >= threshold) or "max" (value must be <= threshold)
    unit: str = ""          # Display unit (ms, %, tps)


@dataclass
class SLAResult:
    """Result of evaluating one SLA target against observed data."""

    target: SLATarget
    observed: float
    passed: bool
    margin_pct: float       # Positive = headroom, negative = violation
    scenario: str = ""      # Which scenario this applies to (or "Overall")


@dataclass
class SLAReport:
    """Complete SLA compliance report."""

    results: list[SLAResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def compliant(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def summary(self) -> str:
        if self.total_count == 0:
            return "No SLA targets defined"
        if self.compliant:
            return "COMPLIANT"
        ratio = self.passed_count / self.total_count
        if ratio >= 0.5:
            return "PARTIALLY COMPLIANT"
        return "NON-COMPLIANT"


# ─── Mapping from YAML keys to SLATarget definitions ────────────────────

_TARGET_DEFINITIONS: dict[str, dict[str, str]] = {
    "availability": {
        "name": "Availability",
        "direction": "min",
        "unit": "%",
    },
    "ttft_p95_ms": {
        "name": "TTFT P95",
        "direction": "max",
        "unit": "ms",
    },
    "ttft_p99_ms": {
        "name": "TTFT P99",
        "direction": "max",
        "unit": "ms",
    },
    "tps_minimum": {
        "name": "Min TPS",
        "direction": "min",
        "unit": "tps",
    },
    "error_budget_pct": {
        "name": "Error Budget",
        "direction": "max",
        "unit": "%",
    },
}


def parse_sla_targets(sla_config: dict) -> list[SLATarget]:
    """Parse sla_targets from project.yaml into SLATarget objects.

    Expected YAML structure:
        sla_targets:
            availability: 0.999          # 99.9% success rate minimum
            ttft_p95_ms: 500             # P95 TTFT must be under 500ms
            ttft_p99_ms: 2000            # P99 TTFT must be under 2s
            tps_minimum: 50              # Minimum sustained TPS
            error_budget_pct: 0.1        # Max 0.1% errors allowed
    """
    targets: list[SLATarget] = []
    for key, value in sla_config.items():
        defn = _TARGET_DEFINITIONS.get(key)
        if defn is None:
            continue
        targets.append(SLATarget(
            name=defn["name"],
            metric=key,
            threshold=float(value),
            direction=defn["direction"],
            unit=defn["unit"],
        ))
    return targets


def _evaluate_single_target(
    target: SLATarget,
    all_results: Sequence[ScenarioResult],
    scenario_label: str = "Overall",
) -> SLAResult:
    """Evaluate a single SLA target against a set of scenario results."""
    total_requests = sum(len(sr.results) for sr in all_results)
    all_ok = [r for sr in all_results for r in sr.successful]
    total_success = len(all_ok)

    observed: float

    if target.metric == "availability":
        # Availability as a ratio (e.g., 0.999)
        observed = total_success / max(1, total_requests)
        threshold = target.threshold
        passed = observed >= threshold
        if threshold > 0:
            margin_pct = (observed - threshold) / threshold * 100
        else:
            margin_pct = 100.0

    elif target.metric == "ttft_p95_ms":
        ttfts = [r.ttft_ms for r in all_ok if r.ttft_ms is not None]
        if ttfts:
            observed = float(np.percentile(ttfts, 95))
        else:
            observed = 0.0
        threshold = target.threshold
        passed = observed <= threshold
        if observed > 0:
            margin_pct = (threshold - observed) / threshold * 100
        else:
            margin_pct = 100.0

    elif target.metric == "ttft_p99_ms":
        ttfts = [r.ttft_ms for r in all_ok if r.ttft_ms is not None]
        if ttfts:
            observed = float(np.percentile(ttfts, 99))
        else:
            observed = 0.0
        threshold = target.threshold
        passed = observed <= threshold
        if observed > 0:
            margin_pct = (threshold - observed) / threshold * 100
        else:
            margin_pct = 100.0

    elif target.metric == "tps_minimum":
        # Minimum average TPS across scenarios
        scenario_avgs = []
        for sr in all_results:
            ok = sr.successful
            if ok:
                tps_vals = [r.tps for r in ok]
                scenario_avgs.append(float(np.mean(tps_vals)))
        observed = min(scenario_avgs) if scenario_avgs else 0.0
        threshold = target.threshold
        passed = observed >= threshold
        if threshold > 0:
            margin_pct = (observed - threshold) / threshold * 100
        else:
            margin_pct = 100.0

    elif target.metric == "error_budget_pct":
        # Error rate as percentage
        total_failed = sum(len(sr.failed) for sr in all_results)
        observed = total_failed / max(1, total_requests) * 100.0
        threshold = target.threshold
        passed = observed <= threshold
        if threshold > 0:
            margin_pct = (threshold - observed) / threshold * 100
        else:
            margin_pct = 100.0 if observed == 0 else -100.0

    else:
        # Unknown metric — mark as passed with 0 margin
        observed = 0.0
        passed = True
        margin_pct = 0.0

    return SLAResult(
        target=target,
        observed=observed,
        passed=passed,
        margin_pct=margin_pct,
        scenario=scenario_label,
    )


def evaluate_sla(
    results: Sequence[Any],         # Sequence[ScenarioResult]
    sla_targets: list[SLATarget],
) -> SLAReport:
    """Evaluate benchmark results against SLA targets.

    For each target:
    - availability: (successful_requests / total_requests) across all scenarios
    - ttft_p95_ms: P95 TTFT across all successful requests
    - ttft_p99_ms: P99 TTFT across all successful requests
    - tps_minimum: Minimum average TPS observed across scenarios
    - error_budget_pct: (failed_requests / total_requests * 100) across all scenarios

    Compute overall compliance assessment.
    """
    report = SLAReport()

    for target in sla_targets:
        result = _evaluate_single_target(target, results, scenario_label="Overall")
        report.results.append(result)

    return report


def _format_threshold(target: SLATarget) -> str:
    """Format threshold for display based on metric type."""
    if target.metric == "availability":
        return f"{target.threshold * 100:.1f}%"
    elif target.unit == "ms":
        return f"{target.threshold:.0f}ms"
    elif target.unit == "tps":
        return f"{target.threshold:.0f} tps"
    elif target.unit == "%":
        return f"{target.threshold:.1f}%"
    return f"{target.threshold}"


def _format_observed(target: SLATarget, observed: float) -> str:
    """Format observed value for display based on metric type."""
    if target.metric == "availability":
        return f"{observed * 100:.1f}%"
    elif target.unit == "ms":
        return f"{observed:.0f}ms"
    elif target.unit == "tps":
        return f"{observed:.1f} tps"
    elif target.unit == "%":
        return f"{observed:.2f}%"
    return f"{observed}"


def _format_direction(target: SLATarget) -> str:
    """Return direction symbol."""
    return "\u2265" if target.direction == "min" else "\u2264"


def _recommendation_for(result: SLAResult) -> str:
    """Generate specific advice for a failed SLA target."""
    metric = result.target.metric
    if metric == "availability":
        return (
            "Investigate error patterns — consider increasing provisioned "
            "capacity or implementing retry logic for transient failures."
        )
    elif metric in ("ttft_p95_ms", "ttft_p99_ms"):
        return (
            "High tail latency often indicates queueing under load. "
            "Reduce concurrency, increase TPM quota, or enable request "
            "prioritization to bring latency within SLA bounds."
        )
    elif metric == "tps_minimum":
        return (
            "Throughput below target suggests the deployment is under-provisioned "
            "for sustained workloads. Consider increasing output TPM allocation "
            "or reducing max_tokens to allow more concurrent generation."
        )
    elif metric == "error_budget_pct":
        return (
            "Error rate exceeds budget. Review error breakdown for root causes — "
            "common fixes include increasing TPM quota (for 429s) or adding "
            "request-level timeouts and retries."
        )
    return "Review deployment configuration and consider scaling resources."


def render_sla_markdown(report: SLAReport, model_name: str = "") -> str:
    """Render SLA compliance report as markdown section.

    Output includes a table of all targets with pass/fail status and margin,
    an overall compliance verdict, and recommendations for any failed targets.
    """
    lines: list[str] = []

    title = "## SLA Compliance Assessment"
    if model_name:
        title += f" — {model_name}"
    lines.append(title)
    lines.append("")

    if not report.results:
        lines.append("> _No SLA targets configured._")
        return "\n".join(lines)

    # ── Results table ────────────────────────────────────────
    lines.append("| SLA Target | Threshold | Observed | Status | Margin |")
    lines.append("|------------|-----------|----------|--------|--------|")

    for r in report.results:
        direction = _format_direction(r.target)
        name_col = f"{r.target.name} ({direction}{_format_threshold(r.target)})"
        threshold_col = _format_threshold(r.target)
        observed_col = _format_observed(r.target, r.observed)
        status_col = "**PASS**" if r.passed else "**FAIL**"
        if r.passed:
            margin_col = f"+{r.margin_pct:.1f}% headroom"
        else:
            margin_col = f"{r.margin_pct:.1f}%"
        lines.append(
            f"| {name_col} | {threshold_col} | {observed_col} "
            f"| {status_col} | {margin_col} |"
        )

    lines.append("")

    # ── Overall verdict ──────────────────────────────────────
    lines.append(
        f"**OVERALL: {report.passed_count}/{report.total_count} targets met "
        f"— {report.summary}**"
    )
    lines.append("")

    # ── Recommendations for failures ─────────────────────────
    failed = [r for r in report.results if not r.passed]
    if failed:
        lines.append("> **Recommendations:**")
        lines.append(">")
        for r in failed:
            advice = _recommendation_for(r)
            lines.append(f"> - **{r.target.name}**: {advice}")
        lines.append("")

    return "\n".join(lines)
