"""
Results reporting and export utilities.

Generates console output, JSON exports, comparison tables,
executive reports (long-form Markdown with figures),
and one-page business reports (DOCX).

This package replaces the previous monolithic ``reporter.py`` module.
All public symbols are re-exported here so existing imports such as
``from ptu_benchmark.reporter import export_json`` continue to work.
"""

from __future__ import annotations

# ── Console output ──────────────────────────────────────────────
from .console import (
    BenchmarkProgress,
    LogCapture,
    ProgressBar,
    print_comparison_table,
    print_header,
    print_progress,
    print_project_comparison,
    print_scenario_summary,
    print_single_result,
)

# ── Data export (JSON / CSV) ────────────────────────────────────
from .export import (
    export_comparison_csv,
    export_csv_summary,
    export_json,
)

# ── Chart generation ────────────────────────────────────────────
from .charts import (
    generate_comparison_chart,
    generate_error_rate_chart,
    generate_tps_chart,
    generate_ttft_chart,
)

# ── Executive (long-form Markdown) report ───────────────────────
from .executive import export_executive_report

# ── Business (DOCX) report ──────────────────────────────────────
from .business import export_business_report

# ── Customer-facing POC report ──────────────────────────────────
from .customer import generate_customer_report

# ── Cost comparison calculator ──────────────────────────────────
from .cost import (
    BreakevenResult,
    CostProjection,
    compute_breakeven,
    compute_ptu_cost,
    compute_token_api_cost,
    generate_cost_report,
)

# ── SLA compliance scoring ────────────────────────────────────
from .sla import (
    SLAReport,
    SLAResult,
    SLATarget,
    evaluate_sla,
    parse_sla_targets,
    render_sla_markdown,
)

# ── Shared utilities ────────────────────────────────────────────
from .utils import (
    _CHART_STYLE,
    _delta,
    _get_model_display_name,
    _sanitize_model_name,
    _scenario_display_name,
    _scenario_metrics,
    build_result_folder,
)


__all__ = [
    # Console
    "BenchmarkProgress",
    "LogCapture",
    "ProgressBar",
    "print_comparison_table",
    "print_header",
    "print_progress",
    "print_project_comparison",
    "print_scenario_summary",
    "print_single_result",
    # Export
    "export_comparison_csv",
    "export_csv_summary",
    "export_json",
    # Charts
    "generate_comparison_chart",
    "generate_error_rate_chart",
    "generate_tps_chart",
    "generate_ttft_chart",
    # Reports
    "export_executive_report",
    "export_business_report",
    "generate_customer_report",
    # Cost
    "BreakevenResult",
    "CostProjection",
    "compute_breakeven",
    "compute_ptu_cost",
    "compute_token_api_cost",
    "generate_cost_report",
    # SLA
    "SLAReport",
    "SLAResult",
    "SLATarget",
    "evaluate_sla",
    "parse_sla_targets",
    "render_sla_markdown",
    # Utils
    "build_result_folder",
    # Internal helpers re-exported for backward compatibility
    "_CHART_STYLE",
    "_delta",
    "_get_model_display_name",
    "_sanitize_model_name",
    "_scenario_display_name",
    "_scenario_metrics",
]
