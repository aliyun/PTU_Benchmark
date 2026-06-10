"""
CLI entry point for PTU Benchmark.

Usage examples:
    # Default workflow — PTU project vs Token API, side-by-side comparison
    # (auto-uses projects/token-api as the comparison baseline)
    python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_500K_100K

    # Run a single project only (skip the implicit Token API comparison)
    python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_500K_100K --no-compare

    # Project + specific scenarios + export
    python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_500K_100K --scenarios A B D --export

    # Explicit A/B compare two projects (override the default Token API baseline)
    python -m ptu_benchmark --project projects/ptu --compare-with projects/other-baseline --scenarios A B

    # List available scenarios
    python -m ptu_benchmark --list

    # Use a specific .env file (legacy mode — no auto comparison)
    python -m ptu_benchmark --env /path/to/.env
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ptu_benchmark import __version__
from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import (
    ProgressBar,
    build_result_folder,
    export_business_report,
    export_comparison_csv,
    export_csv_summary,
    export_executive_report,
    export_json,
    generate_cost_report,
    generate_customer_report,
    print_header,
    print_project_comparison,
    print_scenario_summary,
)
from ptu_benchmark.scenarios import SCENARIOS
from ptu_benchmark.utils import ScenarioResult

# Default A/B comparison baseline auto-applied when --project is used
# without an explicit --compare-with. Disable with --no-compare.
DEFAULT_COMPARE_TARGET = "projects/token-api"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptu-benchmark",
        description="PTU Benchmark Suite — Alibaba Cloud Model Studio",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # ── Configuration source (mutually exclusive) ─────────────────

    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--project",
        type=str,
        default=None,
        metavar="PATH",
        help="Project folder containing project.yaml (per-use-case mode)",
    )
    config_group.add_argument(
        "--env",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to a .env file (legacy flat-config mode)",
    )

    # ── A/B compare (pairs with --project) ────────────────────────

    parser.add_argument(
        "--compare-with",
        type=str,
        default=None,
        metavar="PATH",
        help="Second project folder for A/B comparison (requires --project). "
             "Runs the same scenarios against both and emits 3 reports "
             "(A, B, comparison) into a single bundle directory. Export is implicit. "
             f"If --project is used and this flag is omitted, "
             f"'{DEFAULT_COMPARE_TARGET}' is auto-applied as the baseline "
             "(disable with --no-compare).",
    )
    parser.add_argument(
        "--no-compare",
        action="store_true",
        help=f"Disable the implicit '--compare-with {DEFAULT_COMPARE_TARGET}' "
             "that is auto-applied when --project is used. Use this to benchmark "
             "a single project without an A/B baseline.",
    )
    parser.add_argument(
        "--no-customer-report",
        action="store_true",
        help="Skip auto-generation of the customer-facing POC report "
             "(customer_report.md). Enabled by default in compare mode.",
    )

    # ── Run control ──────────────────────────────────────────────

    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=list(SCENARIOS.keys()),
        default=None,
        help="Scenarios to run (default: all). Example: --scenarios A B D",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scenarios and exit",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export results to JSON and CSV",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Directory for exported result files (default: reports/)",
    )

    # ── Cost analysis options ──────────────────────────────────────

    parser.add_argument(
        "--daily-volume",
        type=int,
        default=None,
        metavar="TOKENS",
        help="Daily token volume for cost projection (overrides project.yaml)",
    )
    parser.add_argument(
        "--growth-rate",
        type=float,
        default=None,
        metavar="RATE",
        help="Monthly growth rate as decimal (e.g., 0.1 for 10%%)",
    )
    parser.add_argument(
        "--no-cost-report",
        action="store_true",
        help="Skip standalone cost analysis report generation",
    )

    return parser


def list_scenarios() -> None:
    """Print all available scenarios."""
    print_header("Available Benchmark Scenarios")
    for key, cls in SCENARIOS.items():
        display = getattr(cls, "display_name", "") or ""
        if display:
            print(f"  {key}  {display} — {cls.description}")
        else:
            print(f"  {key}  {cls.description}")


def _load_project_config(path_str: str) -> tuple[BenchmarkConfig, Path]:
    """Load a BenchmarkConfig from a project folder, exiting on error.

    Accepts either a full path (e.g. ``projects/token-api``) or a bare
    project name (e.g. ``token-api``). Bare names are resolved against
    the ``projects/`` directory next to the current working directory.
    """
    project_dir = Path(path_str)
    if not project_dir.is_dir():
        # Try resolving as a bare project name under projects/
        fallback = Path("projects") / path_str
        if fallback.is_dir():
            project_dir = fallback
        else:
            print(f"Error: project directory not found — {path_str}")
            print(f"  Tried: {Path(path_str)} and {fallback}")
            sys.exit(1)
    if not (project_dir / "project.yaml").exists():
        print(f"Error: project.yaml not found in {project_dir}")
        print(f"  Copy from the template: cp -r projects/template {project_dir}")
        sys.exit(1)
    return BenchmarkConfig.from_project(project_dir), project_dir


def _print_project_banner(config: BenchmarkConfig) -> None:
    """Print the project / connection banner."""
    proj = config.project
    if proj and proj.service_name:
        print(f"  Project:    {proj.service_name}")
        print(f"  Model:      {proj.model_name} ({proj.model_code})")
        print(f"  Deployment: {proj.deployment_id}")
        print(f"  Quota:      {proj.input_tpm:,} input TPM  /  {proj.output_tpm:,} output TPM")
        print(f"  Price:      ${proj.hourly_price:.2f}/hour")
    else:
        print(f"  Model:      {config.model_id}")
    print(f"  Base URL:   {config.base_url}")


def run_benchmarks(
    config: BenchmarkConfig,
    scenario_keys: list[str] | None,
    export: bool,
    output_dir: str,
    report_dir: str | None = None,
    generate_reports: bool = True,
    executive_filename: str = "executive_report.md",
    business_filename: str = "business_report.docx",
    progress: ProgressBar | None = None,
    log_file=None,
) -> list[ScenarioResult]:
    """Run the selected scenarios for one config and optionally export results.

    Parameters
    ----------
    output_dir
        Where raw artefacts (JSON, summary CSV) are written.
    report_dir
        Where the executive/business reports are written. Defaults to
        ``output_dir`` when ``None``. Pass a different directory to keep
        raw data separate from rendered reports.
    generate_reports
        When False, skip the executive/business report generation
        (useful for the baseline arm of an A/B run where only raw data
        is needed alongside the comparison report).
    executive_filename, business_filename
        Override the rendered report filenames.
    progress
        Optional :class:`ProgressBar` shared with the caller. When
        provided, scenario steps advance this bar; otherwise a
        local one is constructed (and finished at the end).
    log_file
        Optional open file handle. When provided, every ``print()``
        emitted during scenario execution is redirected to it so the
        terminal only shows the live progress bar.
    """
    keys = scenario_keys or list(SCENARIOS.keys())
    all_results: list[ScenarioResult] = []

    own_progress = progress is None
    if progress is None:
        progress = ProgressBar(total_steps=len(keys), log_file=log_file)

    # Banner — written to log only (terminal is reserved for the bar).
    with progress.capture_stdout():
        print_header(f"PTU Benchmark Suite v{__version__}")
        _print_project_banner(config)
        print(f"  Running:    {', '.join(keys)}")

    for key in keys:
        scenario_cls = SCENARIOS[key]
        display = getattr(scenario_cls, "display_name", "") or ""
        label = f"Scenario {key} ({display})" if display else f"Scenario {key}"

        progress.start_step(label)
        success = False
        try:
            with progress.capture_stdout():
                header = (
                    f"Scenario {key} — {display}: {scenario_cls.description}"
                    if display
                    else f"Scenario {key}: {scenario_cls.description}"
                )
                print_header(header, char="-")
                scenario = scenario_cls(config)
                result = scenario.run()
                print_scenario_summary(result)
                all_results.append(result)
            success = True
        finally:
            progress.end_step(success=success, label=label)

    if export and all_results:
        with progress.capture_stdout():
            json_path = export_json(all_results, output_dir=output_dir)
            csv_path = export_csv_summary(all_results, output_dir=output_dir)
            print(f"\n  Results exported:")
            print(f"    JSON              → {json_path}")
            print(f"    CSV               → {csv_path}")

            if generate_reports:
                target = report_dir if report_dir is not None else output_dir
                exec_path = export_executive_report(
                    all_results, output_dir=target, config=config,
                    filename=executive_filename,
                )
                biz_path = export_business_report(
                    all_results, output_dir=target, config=config,
                    filename=business_filename,
                )
                print(f"    Executive Report  → {exec_path}")
                print(f"    Business Report   → {biz_path}")

    if own_progress:
        progress.finish()

    return all_results


def _project_label(config: BenchmarkConfig, fallback: Path) -> str:
    """Pick a short, table-friendly label for a project run."""
    if config.project and config.project.service_name:
        return config.project.service_name
    return fallback.name


def run_compare(
    config_a: BenchmarkConfig,
    dir_a: Path,
    config_b: BenchmarkConfig,
    dir_b: Path,
    scenario_keys: list[str] | None,
    output_dir: str,
    customer_report: bool = True,
    cost_report: bool = True,
    daily_volume: int | None = None,
    growth_rate: float | None = None,
    log_file=None,
) -> None:
    """
    Run the same scenarios against two projects and emit reports.

    Layout (A = ``--project`` = subject, B = ``--compare-with`` = baseline):

        reports/<bundle>/
        ├── PTU/                        ← raw subject data
        │   ├── benchmark_results_*.json
        │   └── benchmark_summary.csv
        ├── Token_API/                  ← raw baseline data
        │   ├── benchmark_results_*.json
        │   └── benchmark_summary.csv
        ├── figures/                    ← all charts
        ├── executive_report.md         ← flagship A/B comparison
        ├── business_report.docx        ← flagship A/B DOCX
        ├── customer_report.md          ← customer-facing report
        ├── cost_analysis.md            ← cost analysis
        ├── metrics.csv                 ← side-by-side raw numbers
        └── benchmark.log               ← full verbose execution log
    """
    keys = scenario_keys or list(SCENARIOS.keys())
    bundle = Path(output_dir)
    bundle.mkdir(parents=True, exist_ok=True)

    # Role-based subfolders for raw data
    ptu_dir = bundle / "PTU"
    token_dir = bundle / "Token_API"

    print_header(f"A/B Run — {dir_a.name}  vs  {dir_b.name}")
    print(f"  Scenarios:    {', '.join(keys)}")
    print(f"  Bundle:       {bundle}")
    if log_file is not None:
        log_path = getattr(log_file, "name", "")
        if log_path:
            print(f"  Log file:     {log_path}")
    print()

    # Shared progress bar covering both arms (A then B).
    progress = ProgressBar(
        total_steps=len(keys) * 2,
        log_file=log_file,
    )

    # ── Run A (subject) — raw data → PTU/ ─────────────────────────
    progress.log(f"\n=== [A] {dir_a.name} ===")
    results_a = run_benchmarks(
        config=config_a,
        scenario_keys=keys,
        export=True,
        output_dir=str(ptu_dir),
        report_dir=str(bundle),
        generate_reports=False,
        progress=progress,
        log_file=log_file,
    )

    # ── Run B (baseline) — raw data → Token_API/ ─────────────────
    progress.log(f"\n=== [B] {dir_b.name} ===")
    results_b = run_benchmarks(
        config=config_b,
        scenario_keys=keys,
        export=True,
        output_dir=str(token_dir),
        generate_reports=False,
        progress=progress,
        log_file=log_file,
    )

    # All scenarios complete — commit a final bar line in scrollback.
    progress.finish()

    name_a = _project_label(config_a, dir_a)
    name_b = _project_label(config_b, dir_b)

    # Comparison table goes to log (terminal already shows progress
    # bar history); summary lines below give the user the final view.
    with progress.capture_stdout():
        print_project_comparison(name_a, results_a, name_b, results_b)

    # ── Report generation phase ──────────────────────────────────
    progress.info("Generating reports...")

    with progress.capture_stdout():
        cmp_path = export_comparison_csv(
            name_b, results_b, name_a, results_a,
            output_dir=bundle,
            filename="metrics.csv",
        )
    progress.info(f"  ✓ Metrics CSV       → {cmp_path}")

    with progress.capture_stdout():
        exec_cmp_path = export_executive_report(
            results=results_a,
            output_dir=bundle,
            config=config_a,
            compare_results=results_b,
            compare_config=config_b,
            compare_name=name_b,
            primary_name=name_a,
            filename="executive_report.md",
            chart_prefix="comparison_",
        )
    progress.info(f"  ✓ Executive Report  → {exec_cmp_path}")

    with progress.capture_stdout():
        biz_cmp_path = export_business_report(
            results=results_a,
            output_dir=bundle,
            config=config_a,
            compare_results=results_b,
            compare_config=config_b,
            compare_name=name_b,
            primary_name=name_a,
            filename="business_report.docx",
        )
    progress.info(f"  ✓ Business Report   → {biz_cmp_path}")

    customer_path: Path | None = None
    if customer_report:
        with progress.capture_stdout():
            customer_path = generate_customer_report(
                subject_results=results_a,
                baseline_results=results_b,
                subject_config=config_a,
                baseline_config=config_b,
                output_dir=bundle,
            )
        progress.info(f"  ✓ Customer Report   → {customer_path}")

    cost_path: Path | None = None
    if cost_report:
        vol = daily_volume or config_a.daily_volume
        if vol and vol > 0:
            gr = growth_rate if growth_rate is not None else config_a.growth_rate
            ir = config_a.input_ratio
            with progress.capture_stdout():
                cost_path = generate_cost_report(
                    subject_config=config_a,
                    baseline_config=config_b,
                    daily_volume=vol,
                    output_dir=bundle,
                    growth_rate=gr,
                    input_ratio=ir,
                    baseline_results=results_b,
                )
            progress.info(f"  ✓ Cost Analysis     → {cost_path}")

    # ── Final terminal summary ──────────────────────────────────
    print_header("Reports", char="=")
    print(f"  Bundle                           → {bundle}/")
    print()
    print(f"  ⭐ Executive Report (A/B full)   → {exec_cmp_path}")
    print(f"  ⭐ Business Report  (A/B full)   → {biz_cmp_path}")
    if customer_path is not None:
        print(f"  ⭐ Customer POC Report           → {customer_path}")
    if cost_path is not None:
        print(f"  ⭐ Cost Analysis                 → {cost_path}")
    print(f"     Metrics CSV                   → {cmp_path}")
    print()
    print(f"  Raw data:")
    print(f"     A — {name_a:<28} → {ptu_dir}/")
    print(f"     B — {name_b:<28} → {token_dir}/")
    if log_file is not None:
        log_path = getattr(log_file, "name", "")
        if log_path:
            print(f"\n  Full execution log               → {log_path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return

    # ── Auto-apply default A/B baseline (Token API) ──────────────────
    # When the user passes --project without --compare-with, default to
    # comparing against projects/token-api so the standard POC workflow
    # (PTU vs Token API) is the one-command experience. Opt out via
    # --no-compare, or override with an explicit --compare-with.
    if (
        args.project
        and not args.compare_with
        and not args.no_compare
    ):
        default_target = Path(DEFAULT_COMPARE_TARGET)
        project_path = Path(args.project)
        # Skip auto-compare if the project IS the default baseline
        # (avoids self-comparison) or if the baseline folder is missing.
        same_as_default = (
            project_path.resolve() == default_target.resolve()
            if default_target.exists() else False
        )
        if default_target.is_dir() and not same_as_default:
            args.compare_with = DEFAULT_COMPARE_TARGET
            print(
                f"  Note: auto-comparing against '{DEFAULT_COMPARE_TARGET}' "
                f"(disable with --no-compare).\n"
            )
        elif not default_target.is_dir():
            print(
                f"  Note: default baseline '{DEFAULT_COMPARE_TARGET}' not found "
                f"— running single-project mode.\n"
            )

    # ── Validate --compare-with usage ─────────────────────────────────
    if args.compare_with and not args.project:
        print("Error: --compare-with requires --project (the baseline project).")
        sys.exit(1)

    # ── A/B compare mode ──────────────────────────────────────────────
    if args.compare_with:
        config_a, dir_a = _load_project_config(args.project)
        config_b, dir_b = _load_project_config(args.compare_with)

        for label, cfg in (("A (--project)", config_a), ("B (--compare-with)", config_b)):
            errors = cfg.validate()
            if errors:
                print(f"Configuration errors for {label}:")
                for err in errors:
                    print(f"  - {err}")
                sys.exit(1)

        # Build dated report folder: {date}_{model}_{NNN}
        if args.output_dir == "reports":
            model_a_name = (config_a.project.model_name if config_a.project
                            else config_a.model_id or dir_a.name)
            bundle_dir = build_result_folder(
                "reports", model_a_name,
            )
            args.output_dir = str(bundle_dir)
        else:
            # User-specified dir: use it directly
            Path(args.output_dir).mkdir(parents=True, exist_ok=True)

        log_path = Path(args.output_dir) / "benchmark.log"
        with open(log_path, "w", encoding="utf-8") as log_handle:
            run_compare(
                config_a=config_a, dir_a=dir_a,
                config_b=config_b, dir_b=dir_b,
                scenario_keys=args.scenarios,
                output_dir=args.output_dir,
                customer_report=not args.no_customer_report,
                cost_report=not args.no_cost_report,
                daily_volume=args.daily_volume,
                growth_rate=args.growth_rate,
                log_file=log_handle,
            )
        return

    # ── Single-project / .env mode ────────────────────────────────────
    if args.project:
        config, project_dir = _load_project_config(args.project)
        if args.output_dir == "reports":
            model_name = (config.project.model_name if config.project
                          else config.model_id or project_dir.name)
            bundle_dir = build_result_folder("reports", model_name)
            args.output_dir = str(bundle_dir)
        else:
            # User-specified: use it directly
            Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    else:
        config = BenchmarkConfig.from_env(args.env)
        if args.output_dir == "reports":
            model_name = config.model_id or "benchmark"
            bundle_dir = build_result_folder("reports", model_name)
            args.output_dir = str(bundle_dir)
        else:
            Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for err in errors:
            print(f"  - {err}")
        print("\nCopy .env.example to .env and fill in your values:")
        print("  cp .env.example .env")
        if not args.project:
            print("\nOr use project-based configuration:")
            print("  python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_500K_100K")
        sys.exit(1)

    keys = args.scenarios or list(SCENARIOS.keys())
    log_path = Path(args.output_dir) / "benchmark.log"
    with open(log_path, "w", encoding="utf-8") as log_handle:
        progress = ProgressBar(total_steps=len(keys), log_file=log_handle)
        print_header(f"PTU Benchmark Suite v{__version__}")
        _print_project_banner(config)
        print(f"  Scenarios:  {', '.join(keys)}")
        print(f"  Bundle:     {args.output_dir}")
        print(f"  Log file:   {log_path}\n")

        run_benchmarks(
            config=config,
            scenario_keys=keys,
            export=True,  # always export reports
            output_dir=str(Path(args.output_dir) / "data"),
            report_dir=args.output_dir,
            progress=progress,
            log_file=log_handle,
        )
        progress.finish()
        print(f"\n  Bundle: {args.output_dir}/")
        print(f"  Log:    {log_path}")


if __name__ == "__main__":
    main()
