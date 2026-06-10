"""
Cost comparison calculator for PTU vs Token API deployments.

Provides volume-based breakeven analysis — "At X tokens/day, which deployment
is cheaper?" — and generates a standalone ``cost_analysis.md`` report with
projections, breakeven point, and reliability premium.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CostProjection:
    """Cost projection for a deployment at given volume."""

    daily_cost: float
    monthly_cost: float
    annual_cost: float
    cost_per_million_tokens: float


@dataclass
class BreakevenResult:
    """Result of breakeven analysis between PTU and Token API."""

    ptu_monthly: float
    token_api_monthly: float
    monthly_savings: float  # Positive = PTU is cheaper
    annual_savings: float
    breakeven_daily_tokens: float  # Volume where PTU = Token API cost
    recommendation: str  # "PTU" or "Token API" or "Comparable"
    roi_percent: float  # Annual ROI of switching to PTU


# ─────────────────────────────────────────────────────────────────────────────
# Core calculations
# ─────────────────────────────────────────────────────────────────────────────


def compute_ptu_cost(hourly_price: float) -> CostProjection:
    """Compute PTU fixed costs (independent of volume).

    Parameters
    ----------
    hourly_price:
        Total hourly cost for the PTU deployment in cost units.
    """
    daily = hourly_price * 24
    monthly = daily * 30
    annual = daily * 365
    # cost_per_million_tokens is meaningless for fixed cost without volume,
    # but we set it to 0 so callers can distinguish.
    return CostProjection(
        daily_cost=daily,
        monthly_cost=monthly,
        annual_cost=annual,
        cost_per_million_tokens=0.0,
    )


def compute_token_api_cost(
    daily_tokens: int,
    input_ratio: float,
    input_price_per_m: float,
    output_price_per_m: float,
) -> CostProjection:
    """Compute Token API pay-per-use costs at given volume.

    Parameters
    ----------
    daily_tokens:
        Total tokens processed per day (input + output combined).
    input_ratio:
        Fraction of tokens that are input (e.g., 0.3 means 30% input).
    input_price_per_m:
        Price per million input tokens.
    output_price_per_m:
        Price per million output tokens.
    """
    daily_input = daily_tokens * input_ratio
    daily_output = daily_tokens * (1.0 - input_ratio)

    daily_cost = (
        (daily_input / 1_000_000) * input_price_per_m
        + (daily_output / 1_000_000) * output_price_per_m
    )
    monthly_cost = daily_cost * 30
    annual_cost = daily_cost * 365

    # Blended cost per million tokens
    if daily_tokens > 0:
        cost_per_m = daily_cost / (daily_tokens / 1_000_000)
    else:
        cost_per_m = 0.0

    return CostProjection(
        daily_cost=daily_cost,
        monthly_cost=monthly_cost,
        annual_cost=annual_cost,
        cost_per_million_tokens=cost_per_m,
    )


def compute_breakeven(
    ptu_hourly_price: float,
    token_api_input_price_per_m: float,
    token_api_output_price_per_m: float,
    input_ratio: float,
    daily_tokens: int,
) -> BreakevenResult:
    """Compare PTU vs Token API and compute breakeven point.

    Parameters
    ----------
    ptu_hourly_price:
        Fixed hourly cost for the PTU deployment.
    token_api_input_price_per_m:
        Token API price per million input tokens.
    token_api_output_price_per_m:
        Token API price per million output tokens.
    input_ratio:
        Fraction of tokens that are input (e.g., 0.3).
    daily_tokens:
        Current daily total token volume for comparison.
    """
    ptu = compute_ptu_cost(ptu_hourly_price)
    token_api = compute_token_api_cost(
        daily_tokens=daily_tokens,
        input_ratio=input_ratio,
        input_price_per_m=token_api_input_price_per_m,
        output_price_per_m=token_api_output_price_per_m,
    )

    monthly_savings = token_api.monthly_cost - ptu.monthly_cost
    annual_savings = token_api.annual_cost - ptu.annual_cost

    # Breakeven: PTU daily cost == Token API daily cost at volume X
    # PTU daily = hourly_price * 24
    # Token API daily = (X * input_ratio / 1M) * input_price + (X * (1-input_ratio) / 1M) * output_price
    # Solving for X:
    #   hourly_price * 24 = X/1M * (input_ratio * input_price + (1-input_ratio) * output_price)
    blended_rate_per_m = (
        input_ratio * token_api_input_price_per_m
        + (1.0 - input_ratio) * token_api_output_price_per_m
    )
    if blended_rate_per_m > 0:
        breakeven_daily = (ptu.daily_cost / blended_rate_per_m) * 1_000_000
    else:
        breakeven_daily = float("inf")

    # Recommendation
    THRESHOLD_PCT = 5.0  # Within 5% is "Comparable"
    if ptu.monthly_cost == 0 or token_api.monthly_cost == 0:
        recommendation = "Insufficient data"
    elif abs(monthly_savings) / max(ptu.monthly_cost, token_api.monthly_cost) * 100 < THRESHOLD_PCT:
        recommendation = "Comparable"
    elif monthly_savings > 0:
        recommendation = "PTU"
    else:
        recommendation = "Token API"

    # ROI: annual savings / PTU annual cost * 100
    roi = (annual_savings / ptu.annual_cost * 100) if ptu.annual_cost > 0 else 0.0

    return BreakevenResult(
        ptu_monthly=ptu.monthly_cost,
        token_api_monthly=token_api.monthly_cost,
        monthly_savings=monthly_savings,
        annual_savings=annual_savings,
        breakeven_daily_tokens=breakeven_daily,
        recommendation=recommendation,
        roi_percent=roi,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────


def _format_number(n: float) -> str:
    """Format large numbers with commas."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:.0f}"


def _compute_error_rate(results: Sequence[Any]) -> float:
    """Extract aggregate error rate from benchmark results."""
    total_requests = 0
    total_errors = 0
    for r in results:
        metrics = r.metrics if hasattr(r, "metrics") else {}
        total_requests += metrics.get("total_requests", 0)
        total_errors += metrics.get("errors", 0)
    if total_requests > 0:
        return total_errors / total_requests
    return 0.0


def generate_cost_report(
    subject_config: Any,
    baseline_config: Any,
    daily_volume: int,
    output_dir: str | Path,
    growth_rate: float = 0.0,
    input_ratio: float = 0.3,
    months: int = 12,
    baseline_results: Sequence[Any] | None = None,
) -> Path:
    """Generate standalone cost_analysis.md with breakeven and projections.

    Parameters
    ----------
    subject_config:
        BenchmarkConfig for the PTU (subject) deployment.
    baseline_config:
        BenchmarkConfig for the Token API (baseline) deployment.
    daily_volume:
        Daily total tokens for cost projection.
    output_dir:
        Directory where ``cost_analysis.md`` will be written.
    growth_rate:
        Monthly growth rate as decimal (e.g., 0.1 for 10%).
    input_ratio:
        Fraction of tokens that are input (default 0.3 = 30% input / 70% output).
    months:
        Projection horizon in months (default 12).
    baseline_results:
        Optional benchmark results for the baseline to compute reliability premium.

    Returns
    -------
    Path
        Path to the generated ``cost_analysis.md`` file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract pricing from configs
    ptu_project = subject_config.project if hasattr(subject_config, "project") else None
    baseline_project = baseline_config.project if hasattr(baseline_config, "project") else None

    ptu_hourly = ptu_project.hourly_price if ptu_project else 0.0
    token_input_price = getattr(baseline_project, "token_input_price_per_m", 0.0) or 0.0
    token_output_price = getattr(baseline_project, "token_output_price_per_m", 0.0) or 0.0

    # If Token API pricing is available on subject config (fallback)
    if token_input_price == 0.0 and token_output_price == 0.0:
        token_input_price = getattr(ptu_project, "token_input_price_per_m", 0.0) or 0.0
        token_output_price = getattr(ptu_project, "token_output_price_per_m", 0.0) or 0.0

    lines: list[str] = []
    lines.append("# Cost Analysis: PTU vs Token API")
    lines.append("")

    # PTU info
    ptu_name = ptu_project.service_name if ptu_project else "PTU"
    baseline_name = baseline_project.service_name if baseline_project else "Token API"

    lines.append(f"**Subject (PTU):** {ptu_name}  ")
    lines.append(f"**Baseline (Token API):** {baseline_name}  ")
    lines.append(f"**Daily volume:** {_format_number(daily_volume)} tokens/day  ")
    lines.append(f"**Input/Output ratio:** {input_ratio * 100:.0f}% input / {(1 - input_ratio) * 100:.0f}% output  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 1: Executive Summary ─────────────────────────────────────
    can_compare = ptu_hourly > 0 and (token_input_price > 0 or token_output_price > 0)

    if can_compare:
        result = compute_breakeven(
            ptu_hourly_price=ptu_hourly,
            token_api_input_price_per_m=token_input_price,
            token_api_output_price_per_m=token_output_price,
            input_ratio=input_ratio,
            daily_tokens=daily_volume,
        )

        lines.append("## 1. Executive Summary")
        lines.append("")
        if result.recommendation == "PTU":
            lines.append(
                f"> **Recommendation: PTU** — saves "
                f"**{result.monthly_savings:,.0f}/month** "
                f"({result.annual_savings:,.0f}/year) at your current volume. "
                f"ROI: {result.roi_percent:+.1f}%."
            )
        elif result.recommendation == "Token API":
            lines.append(
                f"> **Recommendation: Token API** — saves "
                f"**{abs(result.monthly_savings):,.0f}/month** "
                f"({abs(result.annual_savings):,.0f}/year) at your current volume. "
                f"PTU becomes cost-effective above "
                f"{_format_number(result.breakeven_daily_tokens)} tokens/day."
            )
        else:
            lines.append(
                f"> **Recommendation: Comparable** — costs differ by less than 5%. "
                f"Decision should be based on performance and reliability needs."
            )
        lines.append("")

        # ── Section 2: Fixed vs Variable Cost Table ──────────────────────
        ptu_proj = compute_ptu_cost(ptu_hourly)
        token_proj = compute_token_api_cost(
            daily_tokens=daily_volume,
            input_ratio=input_ratio,
            input_price_per_m=token_input_price,
            output_price_per_m=token_output_price,
        )

        lines.append("## 2. Fixed vs Variable Cost Comparison")
        lines.append("")
        lines.append("| Metric | PTU (Fixed) | Token API (Pay-per-use) | Delta |")
        lines.append("|--------|-------------|------------------------|-------|")
        lines.append(
            f"| Daily cost | {ptu_proj.daily_cost:,.2f} | "
            f"{token_proj.daily_cost:,.2f} | "
            f"{ptu_proj.daily_cost - token_proj.daily_cost:+,.2f} |"
        )
        lines.append(
            f"| Monthly cost | {ptu_proj.monthly_cost:,.2f} | "
            f"{token_proj.monthly_cost:,.2f} | "
            f"{ptu_proj.monthly_cost - token_proj.monthly_cost:+,.2f} |"
        )
        lines.append(
            f"| Annual cost | {ptu_proj.annual_cost:,.2f} | "
            f"{token_proj.annual_cost:,.2f} | "
            f"{ptu_proj.annual_cost - token_proj.annual_cost:+,.2f} |"
        )
        lines.append(
            f"| Cost/M tokens | "
            f"{ptu_proj.daily_cost / (daily_volume / 1_000_000):,.2f} | "
            f"{token_proj.cost_per_million_tokens:,.2f} | "
            f"{ptu_proj.daily_cost / (daily_volume / 1_000_000) - token_proj.cost_per_million_tokens:+,.2f} |"
            if daily_volume > 0
            else "| Cost/M tokens | N/A | N/A | N/A |"
        )
        lines.append("")

        # ── Section 3: Breakeven Analysis ────────────────────────────────
        lines.append("## 3. Breakeven Analysis")
        lines.append("")
        lines.append(
            f"PTU becomes cheaper than Token API at "
            f"**{_format_number(result.breakeven_daily_tokens)} tokens/day**."
        )
        lines.append("")

        if daily_volume > 0 and result.breakeven_daily_tokens < float("inf"):
            ratio = daily_volume / result.breakeven_daily_tokens
            if ratio > 1.0:
                pct_above = (ratio - 1.0) * 100
                lines.append(
                    f"Your current volume ({_format_number(daily_volume)} tokens/day) is "
                    f"**{pct_above:.0f}% above breakeven** — PTU is recommended."
                )
            else:
                pct_below = (1.0 - ratio) * 100
                lines.append(
                    f"Your current volume ({_format_number(daily_volume)} tokens/day) is "
                    f"**{pct_below:.0f}% below breakeven** — "
                    f"Token API is more cost-effective at this volume."
                )
        lines.append("")

        # Show breakeven at different input ratios
        lines.append("**Breakeven sensitivity (by input/output ratio):**")
        lines.append("")
        lines.append("| Input Ratio | Breakeven (tokens/day) | Blended Cost/M |")
        lines.append("|-------------|----------------------|----------------|")
        for ratio_pct in (20, 30, 40, 50):
            r = ratio_pct / 100.0
            blended = r * token_input_price + (1.0 - r) * token_output_price
            if blended > 0:
                be = (ptu_proj.daily_cost / blended) * 1_000_000
                lines.append(
                    f"| {ratio_pct}% | {_format_number(be)} | {blended:,.2f} |"
                )
        lines.append("")

        # ── Section 4: Volume Projection (if growth_rate > 0) ────────────
        if growth_rate > 0:
            lines.append("## 4. Volume Growth Projection")
            lines.append("")
            lines.append(
                f"Projected costs assuming **{growth_rate * 100:.0f}% monthly growth** "
                f"over {months} months:"
            )
            lines.append("")
            lines.append("| Month | Daily Volume | Token API Monthly | PTU Monthly | Monthly Savings |")
            lines.append("|-------|-------------|-------------------|------------|----------------|")

            cumulative_token_api = 0.0
            cumulative_ptu = 0.0
            for m in range(1, months + 1):
                vol = int(daily_volume * ((1 + growth_rate) ** (m - 1)))
                ta_cost = compute_token_api_cost(
                    daily_tokens=vol,
                    input_ratio=input_ratio,
                    input_price_per_m=token_input_price,
                    output_price_per_m=token_output_price,
                )
                ptu_monthly = ptu_proj.monthly_cost
                savings = ta_cost.monthly_cost - ptu_monthly
                cumulative_token_api += ta_cost.monthly_cost
                cumulative_ptu += ptu_monthly
                lines.append(
                    f"| {m} | {_format_number(vol)} | "
                    f"{ta_cost.monthly_cost:,.0f} | "
                    f"{ptu_monthly:,.0f} | "
                    f"{savings:+,.0f} |"
                )
            lines.append("")
            lines.append(
                f"**Cumulative ({months}-month):** Token API = "
                f"{cumulative_token_api:,.0f} | PTU = {cumulative_ptu:,.0f} | "
                f"Difference = {cumulative_token_api - cumulative_ptu:+,.0f}"
            )
            lines.append("")
        else:
            lines.append("## 4. Volume Growth Projection")
            lines.append("")
            lines.append(
                "_No growth rate specified. Add `growth_rate` to project.yaml "
                "or use `--growth-rate 0.1` for 10% monthly growth projections._"
            )
            lines.append("")

        # ── Section 5: Reliability Premium ───────────────────────────────
        lines.append("## 5. Reliability Premium")
        lines.append("")
        if baseline_results:
            error_rate = _compute_error_rate(baseline_results)
            if error_rate > 0:
                # Estimate retry cost: each failed request costs ~50% of the
                # blended per-request cost (partial processing + retry overhead)
                blended_rate = (
                    input_ratio * token_input_price
                    + (1.0 - input_ratio) * token_output_price
                )
                # Average request size assumption: daily_volume / estimated_daily_requests
                # Use a reasonable default of 1000 tokens per request average
                avg_tokens_per_request = 1000
                cost_per_request = (avg_tokens_per_request / 1_000_000) * blended_rate
                retry_cost_per_request = cost_per_request * 0.5

                daily_requests_est = daily_volume / avg_tokens_per_request if daily_volume > 0 else 0
                daily_retries = daily_requests_est * error_rate
                monthly_retry_cost = daily_retries * retry_cost_per_request * 30

                lines.append(
                    f"Token API incurred **{error_rate * 100:.1f}% error rate** "
                    f"(rate-limiting / failures) during benchmarks."
                )
                lines.append("")
                lines.append(
                    f"- Estimated daily retries: {daily_retries:,.0f} requests  "
                )
                lines.append(
                    f"- Estimated retry cost: {monthly_retry_cost:,.2f}/month  "
                )
                lines.append(
                    f"- **Hidden reliability cost adds ~{monthly_retry_cost:,.2f}/month** "
                    f"to Token API TCO"
                )
            else:
                lines.append(
                    "No errors observed in Token API benchmark — "
                    "reliability premium is negligible at tested load levels."
                )
        else:
            lines.append(
                "_No baseline benchmark results available for reliability analysis. "
                "Run a full A/B comparison to include error-rate-based retry cost estimates._"
            )
        lines.append("")

    else:
        # Cannot perform full comparison — show what we can
        lines.append("## 1. Executive Summary")
        lines.append("")
        if ptu_hourly > 0 and (token_input_price == 0 and token_output_price == 0):
            lines.append(
                "> **Incomplete pricing data.** Token API per-token pricing not configured. "
                "Add `token_input_price_per_m` and `token_output_price_per_m` to the "
                "Token API project.yaml to enable breakeven analysis."
            )
            lines.append("")
            lines.append("## 2. PTU Fixed Costs (available)")
            lines.append("")
            ptu_proj = compute_ptu_cost(ptu_hourly)
            lines.append("| Period | Cost |")
            lines.append("|--------|------|")
            lines.append(f"| Daily | {ptu_proj.daily_cost:,.2f} |")
            lines.append(f"| Monthly | {ptu_proj.monthly_cost:,.2f} |")
            lines.append(f"| Annual | {ptu_proj.annual_cost:,.2f} |")
            lines.append("")
        else:
            lines.append(
                "> **Insufficient pricing data.** PTU hourly price and/or Token API "
                "per-token pricing are not configured. Update project.yaml files to "
                "enable cost comparison."
            )
        lines.append("")

    # ── Footer ───────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append(
        "_Generated by PTU Benchmark Suite. Costs are in the units "
        "specified in project.yaml (not necessarily USD). "
        "Actual costs may vary based on billing cycles and discounts._"
    )
    lines.append("")

    report_path = output_dir / "cost_analysis.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
