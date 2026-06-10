"""Executive (long-form Markdown + figures) report generation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from tabulate import tabulate

from ptu_benchmark.utils import ScenarioResult

from .charts import (
    generate_comparison_chart,
    generate_error_rate_chart,
    generate_tps_chart,
    generate_ttft_chart,
)
from .utils import _delta, _get_model_display_name, _scenario_metrics


# Fallback display names used when ScenarioResult.display_name is not present.
DISPLAY_NAMES = {
    "A": "Latency Baseline",
    "B": "Concurrency Stress Test",
    "C": "Sustained Throughput Test",
    "D": "Peak Burst Resilience",
    "E": "Long Context Performance",
}


def _scenario_display_name(sr: ScenarioResult) -> str:
    """Return a human-readable scenario label, falling back to a static map."""
    dn = getattr(sr, "display_name", None)
    if dn:
        return str(dn)
    # Prefer the live class attribute from the SCENARIOS registry
    try:
        from ptu_benchmark.scenarios import SCENARIOS
        cls = SCENARIOS.get(sr.scenario)
        if cls is not None:
            cls_dn = getattr(cls, "display_name", "") or ""
            if cls_dn:
                return cls_dn
    except Exception:
        pass
    return DISPLAY_NAMES.get(sr.scenario, sr.label or sr.scenario)


def _error_rate_pct(sr: ScenarioResult) -> float:
    """Return the failure rate (errors + 429s) as a percentage of total requests."""
    total = len(sr.results)
    if total == 0:
        return 0.0
    return len(sr.failed) / total * 100.0


def _verdict_dashboard_rows(
    subject_results: Sequence[ScenarioResult],
    baseline_results: Sequence[ScenarioResult],
) -> tuple[list[list[str]], int, int, int, bool]:
    """
    Build verdict-by-scenario table rows for the executive dashboard.

    Returns
    -------
    (rows, subject_wins, baseline_wins, mixed, capacity_warn)
        - rows: list of [scenario, latency_cell, throughput_cell, reliability_cell,
                         winner_cell] strings.
        - subject_wins / baseline_wins / mixed: per-scenario tally counts.
        - capacity_warn: True if any subject scenario shows >10% error rate.
    """
    by_subj = {sr.scenario: sr for sr in subject_results}
    by_base = {sr.scenario: sr for sr in baseline_results}
    keys = [k for k in by_subj if k in by_base]

    rows: list[list[str]] = []
    subj_wins = base_wins = mixed = 0
    capacity_warn = False

    for key in keys:
        sr_s = by_subj[key]
        sr_b = by_base[key]
        ms = _scenario_metrics(sr_s)
        mb = _scenario_metrics(sr_b)

        # ── Latency (TTFT P50, lower is better) ────────────────
        s_ttft = ms["ttft_p50"]
        b_ttft = mb["ttft_p50"]
        if s_ttft is None or b_ttft is None:
            lat_cell, lat_winner = "—", None
        elif abs(s_ttft - b_ttft) < 1e-6:
            lat_cell = f"Tie ({s_ttft:.0f} ms)"
            lat_winner = "tie"
        elif s_ttft < b_ttft:
            pct = (s_ttft - b_ttft) / b_ttft * 100  # negative → improvement
            lat_cell = f"Subject ({pct:+.0f}% TTFT)"
            lat_winner = "subject"
        else:
            pct = (b_ttft - s_ttft) / s_ttft * 100  # negative → improvement
            lat_cell = f"Baseline ({pct:+.0f}% TTFT)"
            lat_winner = "baseline"

        # ── Throughput (TPS avg, higher is better) ─────────────
        s_tps = ms["tps_avg"]
        b_tps = mb["tps_avg"]
        if s_tps is None or b_tps is None:
            thr_cell, thr_winner = "—", None
        elif abs(s_tps - b_tps) < 1e-6:
            thr_cell = f"Tie ({s_tps:.1f} tok/s)"
            thr_winner = "tie"
        elif s_tps > b_tps:
            pct = (s_tps - b_tps) / b_tps * 100  # positive → improvement
            thr_cell = f"Subject ({pct:+.0f}% TPS)"
            thr_winner = "subject"
        else:
            pct = (b_tps - s_tps) / s_tps * 100  # positive → improvement
            thr_cell = f"Baseline ({pct:+.0f}% TPS)"
            thr_winner = "baseline"

        # ── Reliability (error rate, lower is better) ──────────
        s_err = _error_rate_pct(sr_s)
        b_err = _error_rate_pct(sr_b)
        if abs(s_err - b_err) < 1e-6:
            rel_cell = f"Tie ({s_err:.0f}% vs {b_err:.0f}%)"
            rel_winner = "tie"
        elif s_err < b_err:
            rel_cell = f"Subject ({s_err:.0f}% vs {b_err:.0f}%)"
            rel_winner = "subject"
        else:
            rel_cell = f"Baseline ({b_err:.0f}% vs {s_err:.0f}%)"
            rel_winner = "baseline"

        # Capacity advisory: subject error rate > 10% implies quota undersizing
        if s_err > 10.0:
            capacity_warn = True

        # ── Majority winner across the three criteria ──────────
        winners = [w for w in (lat_winner, thr_winner, rel_winner)
                   if w in ("subject", "baseline")]
        s_count = winners.count("subject")
        b_count = winners.count("baseline")
        if s_count > b_count:
            winner_cell = "**Subject**"
            subj_wins += 1
        elif b_count > s_count:
            winner_cell = "**Baseline**"
            base_wins += 1
        else:
            winner_cell = "**Mixed**"
            mixed += 1

        scenario_label = f"{key} — {_scenario_display_name(sr_s)}"
        rows.append([scenario_label, lat_cell, thr_cell, rel_cell, winner_cell])

    return rows, subj_wins, base_wins, mixed, capacity_warn


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

    ttft_chart = generate_ttft_chart(results, figures_dir, filename=ttft_chart_name)
    tps_chart = generate_tps_chart(results, figures_dir, filename=tps_chart_name)
    error_chart = generate_error_rate_chart(results, figures_dir, filename=error_chart_name)
    comparison_chart = None
    if compare_results is not None:
        comparison_chart = generate_comparison_chart(
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

    # ── Verdict by Scenario (A/B mode only) ─────────────────────
    if compare_results is not None:
        v_rows, subj_wins, base_wins, mixed, capacity_warn = _verdict_dashboard_rows(
            results, compare_results,
        )
        if v_rows:
            lines.append("## Verdict by Scenario")
            lines.append("")
            lines.append(
                "Per-scenario winner determination using a simple-majority "
                "heuristic across three criteria — **Latency** (lower TTFT P50 wins), "
                "**Throughput** (higher avg TPS wins), and **Reliability** "
                "(lower error rate wins). No statistical significance testing applied."
            )
            lines.append("")
            v_headers = ["Scenario", "Latency (TTFT)", "Throughput (TPS)",
                         "Reliability", "Winner"]
            lines.append(tabulate(v_rows, headers=v_headers, tablefmt="pipe"))
            lines.append("")

            total = subj_wins + base_wins + mixed
            subject_label = pri_model or primary_name or "Subject"
            baseline_label = cmp_model or compare_name or "Baseline"
            if subj_wins > base_wins:
                lines.append(
                    f"**OVERALL**: {subject_label} (Subject) recommended — "
                    f"wins in {subj_wins}/{total} scenarios."
                )
            elif base_wins > subj_wins:
                lines.append(
                    f"**OVERALL**: {baseline_label} (Baseline) recommended — "
                    f"wins in {base_wins}/{total} scenarios."
                )
            else:
                lines.append(
                    f"**OVERALL**: Mixed result — Subject {subj_wins}/{total}, "
                    f"Baseline {base_wins}/{total}, Mixed {mixed}/{total}. "
                    "No clear winner across scenarios."
                )
            lines.append("")

            if capacity_warn:
                lines.append(
                    "> **Configuration Advisory**: One or more scenarios show "
                    ">10% error rate on the Subject deployment. This may indicate "
                    "quota undersizing rather than a product limitation. Consider "
                    "increasing TPM allocation or reducing concurrency levels."
                )
                lines.append("")

            lines.append("---")
            lines.append("")

    # ── Summary Table ───────────────────────────────────────────
    # ── SLA Compliance (only if sla_targets configured) ──────────
    if config and hasattr(config, 'project') and config.project and config.project.sla_targets:
        from .sla import parse_sla_targets, evaluate_sla, render_sla_markdown
        sla_targets = parse_sla_targets(config.project.sla_targets)
        if sla_targets:
            sla_report = evaluate_sla(results, sla_targets)
            lines.append(render_sla_markdown(sla_report, model_name=primary_name))
            lines.append("")
            lines.append("---")
            lines.append("")

    # ── Summary Table (continued) ────────────────────────────────
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

        label = f"{sr.scenario} — {_scenario_display_name(sr)}: {sr.label}"
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
                    f"{sr.scenario} — {_scenario_display_name(sr)}: {sr.label}",
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
                f"{sr.scenario} — {_scenario_display_name(sr)}: {sr.label}",
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

        lines.append(f"### Scenario {sr.scenario} — {_scenario_display_name(sr)}: {sr.label}")
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

            lines.append(f"### Scenario {key} — {_scenario_display_name(sr_b)}")
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
            lines.append(f"- **Scenario {sr.scenario} — {_scenario_display_name(sr)}:** All {len(sr.results)} requests failed.")
            continue
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        rate_limited_count = len(sr.rate_limited)
        total = len(sr.results)

        finding = f"- **Scenario {sr.scenario} — {_scenario_display_name(sr)} ({sr.label}):** "
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
