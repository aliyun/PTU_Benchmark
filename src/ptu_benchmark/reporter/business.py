"""One-page Business Report (DOCX) generation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Cm, Pt, RGBColor

from ptu_benchmark.utils import ScenarioResult

from .utils import _delta, _get_model_display_name, _scenario_display_name, _scenario_metrics


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
    scenario_a_display = _scenario_display_name("A")
    if scenario_a_display:
        doc.add_heading(f"Headline Metrics — Scenario A ({scenario_a_display})", level=2)
    else:
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
        # Prefer the human-readable display name; fall back to the
        # scenario.label so older runs without display_name still render.
        display = _scenario_display_name(sr.scenario) or sr.label
        overview_rows.append([
            sr.scenario,
            display[:30],
            f"{len(ok)}/{len(sr.results)}",
            str(len(sr.rate_limited)),
            f"{np.percentile(ttfts, 50):.0f}ms" if ttfts else "—",
            f"{np.mean(tps_vals):.0f}" if tps_vals else "—",
        ])

    _add_docx_table(doc, ["#", "Scenario", "Success", "429s", "TTFT P50", "TPS"], overview_rows)

    _add_explanation(doc,
        "Each scenario tests a different aspect: A = Latency Baseline, "
        "B = Concurrency Stress Test, C = Sustained Throughput Test, "
        "D = Peak Burst Resilience, E = Long Context Performance. "
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
