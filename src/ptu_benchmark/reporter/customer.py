"""Customer-facing POC report generation.

Produces a polished, ready-to-send Markdown report by auto-populating
the structure of ``docs/CUSTOMER_REPORT.md`` with computed metrics from
a benchmark run. The output is intended to be hand-finished by the
solution architect (customer name, regional details, narrative copy)
before delivery — editable sections are clearly marked.

The function does not depend on any templating engine; it builds the
report programmatically using the canonical template as a structural
guide.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ptu_benchmark.utils import ScenarioResult

from .utils import _delta, _get_model_display_name, _scenario_metrics


# ── Display name fallbacks for scenario keys ────────────────────────
DISPLAY_NAMES: dict[str, str] = {
    "A": "Latency Baseline",
    "B": "Concurrency Stress Test",
    "C": "Sustained Throughput Test",
    "D": "Peak Burst Resilience",
    "E": "Long Context Performance",
}


# ── Editable-section markers ────────────────────────────────────────
_EDIT_OPEN = "<!-- EDIT BELOW: {hint} -->"
_EDIT_CLOSE = "<!-- END EDIT -->"


def _editable(hint: str, placeholder: str = "") -> list[str]:
    """Wrap a customer-editable placeholder in clear markers."""
    body = placeholder if placeholder else "_(fill in)_"
    return [_EDIT_OPEN.format(hint=hint), body, _EDIT_CLOSE, ""]


def _scenario_display(sr: ScenarioResult) -> str:
    """Return a human-readable scenario heading."""
    return sr.label or DISPLAY_NAMES.get(sr.scenario, f"Scenario {sr.scenario}")


def _quota(config: Any) -> tuple[int, int]:
    """Return (input_tpm, output_tpm) from a config, defaulting to 0."""
    proj = getattr(config, "project", None) if config else None
    if not proj:
        return 0, 0
    return int(getattr(proj, "input_tpm", 0) or 0), int(getattr(proj, "output_tpm", 0) or 0)


def _pricing(config: Any) -> tuple[float, float, float]:
    """Return (hourly_price, input_unit_price, output_unit_price)."""
    proj = getattr(config, "project", None) if config else None
    if not proj:
        return 0.0, 0.0, 0.0
    return (
        float(getattr(proj, "hourly_price", 0.0) or 0.0),
        float(getattr(proj, "input_unit_price", 0.0) or 0.0),
        float(getattr(proj, "output_unit_price", 0.0) or 0.0),
    )


def _per_scenario_tpm(sr: ScenarioResult) -> float:
    """Aggregate TPM achieved by a single scenario."""
    ok = sr.successful
    if not ok:
        return 0.0
    tokens = sum(r.tokens for r in ok)
    max_t = max((r.total_seconds for r in ok), default=0.0)
    return tokens / max_t * 60 if max_t >= 1e-3 else 0.0


def _peak_tpm(results: Sequence[ScenarioResult]) -> tuple[float, str]:
    """Return (peak_tpm, scenario_key) across all scenarios."""
    best = 0.0
    where = ""
    for sr in results:
        tpm = _per_scenario_tpm(sr)
        if tpm > best:
            best = tpm
            where = sr.scenario
    return best, where


def _winner(a: float | None, b: float | None, *, lower_is_better: bool) -> str:
    """Return 'subject', 'baseline', or 'tie' for a single metric."""
    if a is None or b is None:
        return "—"
    if a == b:
        return "tie"
    if lower_is_better:
        return "subject" if b < a else "baseline"
    return "subject" if b > a else "baseline"


# ── Template lookup ─────────────────────────────────────────────────

def _find_template() -> Path | None:
    """Locate ``docs/CUSTOMER_REPORT.md`` relative to package or CWD.

    Walks up from the package directory and also checks the current
    working directory. Returns ``None`` when not found — generation
    proceeds without it (the structure is hard-coded as a guide).
    """
    candidates: list[Path] = []
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidates.append(ancestor / "docs" / "CUSTOMER_REPORT.md")
    candidates.append(Path.cwd() / "docs" / "CUSTOMER_REPORT.md")
    for c in candidates:
        if c.is_file():
            return c
    return None


# ── Section builders ───────────────────────────────────────────────

def _section_header(
    subject_config: Any,
    baseline_config: Any,
    has_baseline: bool,
) -> list[str]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject_name = _get_model_display_name(subject_config, fallback="Subject")
    baseline_name = (
        _get_model_display_name(baseline_config, fallback="Baseline")
        if has_baseline else ""
    )

    lines: list[str] = []
    lines.append("# Customer POC Report")
    lines.append("")
    title_subtitle = (
        f"PTU vs Token API benchmark — {subject_name} vs {baseline_name}"
        if has_baseline
        else f"PTU benchmark — {subject_name}"
    )
    lines.append(f"> {title_subtitle}")
    lines.append("")
    lines.append(f"**Report date:** {now}  ")
    lines.append("**Prepared by:** _(Solution Architect)_  ")
    lines.append("")
    lines.extend(_editable(
        "Customer name, contact, region, POC duration",
        "- **Customer:** _(name)_\n"
        "- **Region:** _(endpoint region, e.g., Singapore)_\n"
        "- **POC Duration:** _(X days)_\n"
        "- **Primary use case:** _(chatbot / RAG / content generation / ...)_",
    ))
    lines.append("---")
    lines.append("")
    return lines


def _section_test_environment(
    subject_config: Any,
    baseline_config: Any,
) -> list[str]:
    s_in, s_out = _quota(subject_config)
    s_proj = getattr(subject_config, "project", None) if subject_config else None
    s_model = _get_model_display_name(subject_config, fallback="Subject")
    s_dep = getattr(s_proj, "deployment_id", "") if s_proj else ""
    s_billing = getattr(s_proj, "billing_method", "") if s_proj else ""

    lines: list[str] = []
    lines.append("## 1. Test Environment")
    lines.append("")
    lines.append("| Setting | Subject (PTU) | Baseline (Token API) |")
    lines.append("|---------|---------------|----------------------|")
    if baseline_config is not None:
        b_in, b_out = _quota(baseline_config)
        b_proj = getattr(baseline_config, "project", None)
        b_model = _get_model_display_name(baseline_config, fallback="Baseline")
        b_dep = getattr(b_proj, "deployment_id", "") if b_proj else ""
        b_billing = getattr(b_proj, "billing_method", "") if b_proj else ""
        lines.append(f"| Model | {s_model} | {b_model} |")
        lines.append(f"| Deployment | {s_dep or '—'} | {b_dep or '—'} |")
        lines.append(f"| Input TPM Quota | {s_in:,} | {b_in:,} |")
        lines.append(f"| Output TPM Quota | {s_out:,} | {b_out:,} |")
        lines.append(f"| Billing | {s_billing or '—'} | {b_billing or '—'} |")
    else:
        lines.append(f"| Model | {s_model} | _n/a_ |")
        lines.append(f"| Deployment | {s_dep or '—'} | _n/a_ |")
        lines.append(f"| Input TPM Quota | {s_in:,} | _n/a_ |")
        lines.append(f"| Output TPM Quota | {s_out:,} | _n/a_ |")
        lines.append(f"| Billing | {s_billing or '—'} | _n/a_ |")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def _section_key_metrics(
    subject_results: Sequence[ScenarioResult],
    baseline_results: Sequence[ScenarioResult] | None,
) -> list[str]:
    lines: list[str] = []
    lines.append("## 2. Key Metrics")
    lines.append("")

    has_baseline = bool(baseline_results)
    if has_baseline:
        headers = (
            "| Scenario | Token API TTFT P50 | PTU TTFT P50 | "
            "Token API TTFT P95 | PTU TTFT P95 | "
            "Token API TPS | PTU TPS | Token API 429s | PTU 429s |"
        )
        sep = "|" + "|".join(["---"] * 9) + "|"
        lines.append(headers)
        lines.append(sep)

        by_b = {sr.scenario: sr for sr in (baseline_results or [])}
        for sr_s in subject_results:
            sr_b = by_b.get(sr_s.scenario)
            ms = _scenario_metrics(sr_s)
            mb = _scenario_metrics(sr_b) if sr_b else {
                "ttft_p50": None, "ttft_p95": None, "tps_avg": None,
                "rate_limited": "—",
            }

            def _fmt(v: float | None, suffix: str) -> str:
                if v is None:
                    return "—"
                if suffix == "ms":
                    return f"{v:.0f} ms"
                return f"{v:.1f}"

            lines.append(
                f"| {sr_s.scenario}: {_scenario_display(sr_s)} "
                f"| {_fmt(mb['ttft_p50'], 'ms')} | {_fmt(ms['ttft_p50'], 'ms')} "
                f"| {_fmt(mb['ttft_p95'], 'ms')} | {_fmt(ms['ttft_p95'], 'ms')} "
                f"| {_fmt(mb['tps_avg'], '')} | {_fmt(ms['tps_avg'], '')} "
                f"| {mb['rate_limited']} | {ms['rate_limited']} |"
            )
    else:
        lines.append("| Scenario | TTFT P50 | TTFT P95 | TPS (avg) | Errors | 429s |")
        lines.append("|----------|----------|----------|-----------|--------|------|")
        for sr in subject_results:
            m = _scenario_metrics(sr)
            ttft50 = "—" if m["ttft_p50"] is None else f"{m['ttft_p50']:.0f} ms"
            ttft95 = "—" if m["ttft_p95"] is None else f"{m['ttft_p95']:.0f} ms"
            tps = "—" if m["tps_avg"] is None else f"{m['tps_avg']:.1f}"
            lines.append(
                f"| {sr.scenario}: {_scenario_display(sr)} "
                f"| {ttft50} | {ttft95} | {tps} "
                f"| {m['errors']} | {m['rate_limited']} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def _section_comparison_summary(
    subject_results: Sequence[ScenarioResult],
    baseline_results: Sequence[ScenarioResult],
) -> tuple[list[str], dict[str, int]]:
    """Comparison deltas + per-scenario winner. Returns (lines, win_counts)."""
    lines: list[str] = []
    lines.append("## 3. Comparison Summary")
    lines.append("")
    lines.append(
        "Δ values are the subject's improvement over the baseline. "
        "Positive = subject is better."
    )
    lines.append("")
    lines.append("| Scenario | Δ TTFT P50 | Δ TTFT P95 | Δ TPS (avg) | Winner |")
    lines.append("|----------|------------|------------|-------------|--------|")

    by_b = {sr.scenario: sr for sr in baseline_results}
    win_counts = {"subject": 0, "baseline": 0, "tie": 0}

    for sr_s in subject_results:
        sr_b = by_b.get(sr_s.scenario)
        if sr_b is None:
            lines.append(
                f"| {sr_s.scenario}: {_scenario_display(sr_s)} "
                f"| — | — | — | _(no baseline)_ |"
            )
            continue
        ms = _scenario_metrics(sr_s)
        mb = _scenario_metrics(sr_b)

        d_ttft50 = _delta(mb["ttft_p50"], ms["ttft_p50"], lower_is_better=True)
        d_ttft95 = _delta(mb["ttft_p95"], ms["ttft_p95"], lower_is_better=True)
        d_tps = _delta(mb["tps_avg"], ms["tps_avg"], lower_is_better=False)

        # Aggregate winner: count signals across the three metrics
        signals = [
            _winner(mb["ttft_p50"], ms["ttft_p50"], lower_is_better=True),
            _winner(mb["ttft_p95"], ms["ttft_p95"], lower_is_better=True),
            _winner(mb["tps_avg"], ms["tps_avg"], lower_is_better=False),
        ]
        subj_wins = signals.count("subject")
        base_wins = signals.count("baseline")
        if subj_wins > base_wins:
            winner = "Subject (PTU)"
            win_counts["subject"] += 1
        elif base_wins > subj_wins:
            winner = "Baseline (Token API)"
            win_counts["baseline"] += 1
        else:
            winner = "Tie"
            win_counts["tie"] += 1

        lines.append(
            f"| {sr_s.scenario}: {_scenario_display(sr_s)} "
            f"| {d_ttft50} | {d_ttft95} | {d_tps} | {winner} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines, win_counts


def _section_quota_utilization(
    subject_results: Sequence[ScenarioResult],
    subject_config: Any,
) -> list[str]:
    _, output_tpm = _quota(subject_config)
    lines: list[str] = []
    lines.append("## 4. Quota Utilization (Subject)")
    lines.append("")
    if not output_tpm:
        lines.append("> _No `output_tpm` configured — utilization analysis skipped._")
        lines.append("")
        lines.append("---")
        lines.append("")
        return lines

    lines.append(
        f"Provisioned **{output_tpm:,} output TPM**. "
        "Utilization = achieved aggregate TPM ÷ quota."
    )
    lines.append("")
    lines.append("| Scenario | Achieved TPM | Quota TPM | Utilization | 429s |")
    lines.append("|----------|--------------|-----------|-------------|------|")
    for sr in subject_results:
        agg = _per_scenario_tpm(sr)
        util = (agg / output_tpm * 100) if output_tpm else 0.0
        lines.append(
            f"| {sr.scenario}: {_scenario_display(sr)} "
            f"| {agg:,.0f} | {output_tpm:,} | {util:.1f}% "
            f"| {len(sr.rate_limited)} |"
        )

    peak, where = _peak_tpm(subject_results)
    if peak:
        lines.append("")
        lines.append(
            f"**Peak observed:** {peak:,.0f} TPM in Scenario {where} "
            f"({peak / output_tpm * 100:.1f}% of quota)."
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def _section_cost_summary(
    subject_results: Sequence[ScenarioResult],
    subject_config: Any,
) -> list[str]:
    hourly, in_unit, out_unit = _pricing(subject_config)
    lines: list[str] = []
    lines.append("## 5. Cost Summary")
    lines.append("")
    if hourly <= 0 and in_unit <= 0 and out_unit <= 0:
        lines.append("> _No pricing data configured for the subject project — "
                      "cost section skipped. Add `hourly_price` (and optionally "
                      "`input_unit_price` / `output_unit_price`) to the project "
                      "YAML to enable this section._")
        lines.append("")
        lines.append("---")
        lines.append("")
        return lines

    if hourly > 0:
        lines.append("**Provisioned cost (fixed):**")
        lines.append("")
        lines.append("| Period | Cost |")
        lines.append("|--------|------|")
        lines.append(f"| Hourly | ${hourly:,.2f} |")
        lines.append(f"| Daily | ${hourly * 24:,.2f} |")
        lines.append(f"| Monthly (30d) | ${hourly * 24 * 30:,.2f} |")
        lines.append(f"| Annual | ${hourly * 24 * 365:,.2f} |")
        lines.append("")

        peak, _ = _peak_tpm(subject_results)
        if peak > 0:
            cost_per_m = hourly / (peak * 60 / 1_000_000)
            lines.append(
                f"**Effective unit cost at peak throughput:** "
                f"~${cost_per_m:,.2f} per M output tokens "
                f"(peak {peak:,.0f} TPM)."
            )
            lines.append("")

    if in_unit > 0 or out_unit > 0:
        lines.append("**Unit prices (informational):**")
        lines.append("")
        lines.append("| Direction | Unit price |")
        lines.append("|-----------|-----------|")
        if in_unit > 0:
            lines.append(f"| Input | ${in_unit:,.4f} per kTPM·hour |")
        if out_unit > 0:
            lines.append(f"| Output | ${out_unit:,.4f} per kTPM·hour |")
        lines.append("")

    lines.extend(_editable(
        "Customer's current Token API spend, projected savings",
        "- **Current monthly spend (Token API):** $_(X)_\n"
        "- **Projected monthly cost (PTU):** $_(Y)_\n"
        "- **Estimated monthly savings:** $_(X − Y)_ (_(Z)_% reduction)\n"
        "- **Annual projected savings:** $_(12 × savings)_",
    ))
    lines.append("---")
    lines.append("")
    return lines


def _section_recommendation(
    subject_results: Sequence[ScenarioResult],
    baseline_results: Sequence[ScenarioResult] | None,
    subject_config: Any,
    win_counts: dict[str, int] | None,
) -> list[str]:
    lines: list[str] = []
    lines.append("## 6. Recommendation")
    lines.append("")

    s_in, s_out = _quota(subject_config)
    subject_name = _get_model_display_name(subject_config, fallback="the subject deployment")

    if win_counts is not None and baseline_results:
        subj = win_counts["subject"]
        base = win_counts["baseline"]
        tie = win_counts["tie"]
        total = subj + base + tie

        if subj > base:
            verdict = (
                f"**Recommend: adopt PTU.** The subject deployment "
                f"won {subj}/{total} scenarios"
                + (f" ({base} to baseline, {tie} tie)" if (base or tie) else "")
                + "."
            )
        elif base > subj:
            verdict = (
                f"**Caution: PTU did not outperform Token API.** Baseline "
                f"won {base}/{total} scenarios"
                + (f" (subject won {subj}, {tie} tie)" if (subj or tie) else "")
                + ". Re-evaluate sizing before commitment."
            )
        else:
            verdict = (
                f"**Mixed results: subject {subj}, baseline {base}, "
                f"tie {tie} of {total}.** Decision should be driven by "
                f"workload-specific priorities (latency vs throughput vs reliability)."
            )
        lines.append(verdict)
        lines.append("")

    # Heuristic capacity / latency commentary
    peak, _ = _peak_tpm(subject_results)
    total_429 = sum(len(sr.rate_limited) for sr in subject_results)
    if total_429 > 0:
        lines.append(
            f"- **Capacity warning:** {total_429} subject requests were rate-limited. "
            "Increase the provisioned TPM tier or reduce concurrency before going live."
        )
    elif s_out and peak:
        util = peak / s_out
        if util < 0.4:
            lines.append(
                f"- **Right-sizing:** peak utilization was only {util*100:.0f}% of "
                f"the {s_out:,} output TPM quota. A smaller tier may improve unit economics."
            )
        elif util > 0.85:
            lines.append(
                f"- **Headroom:** peak utilization reached {util*100:.0f}% of quota. "
                "Plan additional capacity if traffic is expected to grow."
            )
        else:
            lines.append(
                f"- **Sized appropriately:** peak utilization at {util*100:.0f}% of "
                f"the {s_out:,} output TPM quota leaves healthy headroom."
            )

    lines.append("")
    lines.extend(_editable(
        "Tailor the recommended configuration and commercial terms",
        f"- **Recommended configuration:** {s_in:,} input TPM + {s_out:,} output TPM "
        f"on {subject_name}.\n"
        "- **Commitment:** _(daily / monthly / annual)_\n"
        "- **Estimated monthly cost:** $_(X)_\n"
        "- **Projected annual savings:** $_(Y)_\n"
        "- **Alternative configurations** (if traffic grows): _(list scaling options)_",
    ))
    lines.append("---")
    lines.append("")
    return lines


def _section_next_steps() -> list[str]:
    lines: list[str] = []
    lines.append("## 7. Next Steps")
    lines.append("")
    lines.append("1. [ ] Review benchmark results and confirm PTU configuration")
    lines.append("2. [ ] Approve commercial terms (pricing, commitment period)")
    lines.append("3. [ ] Place order via Model Studio console")
    lines.append("4. [ ] Switch application endpoint to PTU model ID")
    lines.append("5. [ ] Monitor first week of production traffic")
    lines.append("6. [ ] Schedule follow-up review (30 days post-launch)")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def _section_footer(template_path: Path | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Appendix")
    lines.append("")
    lines.append("- The full executive report (`executive_report.md`) and the one-page "
                  "Word summary (`business_report.docx`) accompany this customer report "
                  "in the same results bundle. Attach raw JSON for technical reviewers.")
    if template_path is not None:
        try:
            rel = template_path.name
        except Exception:
            rel = str(template_path)
        lines.append(f"- Source template: `docs/{rel}`.")
    lines.append("")
    lines.append("*Auto-generated by PTU Benchmark Suite — review and personalize before sending.*")
    lines.append("")
    return lines


# ── Public entry point ─────────────────────────────────────────────

def generate_customer_report(
    subject_results: list,
    baseline_results: list,
    subject_config: Any,
    baseline_config: Any,
    output_dir: str | Path,
) -> Path:
    """Produce a filled customer-facing POC report.

    Parameters
    ----------
    subject_results
        Scenarios run against the subject (typically PTU) deployment.
    baseline_results
        Scenarios run against the baseline (typically Token API). Pass
        ``None`` or an empty list for a subject-only report.
    subject_config
        ``BenchmarkConfig`` for the subject deployment.
    baseline_config
        ``BenchmarkConfig`` for the baseline deployment, or ``None``.
    output_dir
        Destination folder. The report is written as ``customer_report.md``.

    Returns
    -------
    Path
        The absolute path of the generated Markdown file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "customer_report.md"

    has_baseline = bool(baseline_results)
    template_path = _find_template()

    lines: list[str] = []
    lines.extend(_section_header(subject_config, baseline_config, has_baseline))
    lines.extend(_section_test_environment(subject_config, baseline_config))
    lines.extend(_section_key_metrics(subject_results, baseline_results))

    win_counts: dict[str, int] | None = None
    if has_baseline:
        cmp_lines, win_counts = _section_comparison_summary(
            subject_results, baseline_results,
        )
        lines.extend(cmp_lines)

    lines.extend(_section_quota_utilization(subject_results, subject_config))
    lines.extend(_section_cost_summary(subject_results, subject_config))
    lines.extend(_section_recommendation(
        subject_results, baseline_results, subject_config, win_counts,
    ))
    lines.extend(_section_next_steps())
    lines.extend(_section_footer(template_path))

    out_path.write_text("\n".join(lines))
    return out_path
