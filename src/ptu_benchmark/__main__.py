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
    build_result_folder,
    export_business_report,
    export_comparison_csv,
    export_csv_summary,
    export_executive_report,
    export_json,
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
        default="results",
        help="Directory for exported result files (default: results/)",
    )
    return parser


def list_scenarios() -> None:
    """Print all available scenarios."""
    print_header("Available Benchmark Scenarios")
    for key, cls in SCENARIOS.items():
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
        Override the rendered report filenames. Defaults to
        ``executive_report.md`` / ``business_report.docx``. In an A/B
        run, the subject's standalone reports are written under
        ``subject_only_*`` names so the canonical filenames belong to
        the flagship A/B comparison report instead.
    """
    keys = scenario_keys or list(SCENARIOS.keys())
    all_results: list[ScenarioResult] = []

    print_header(f"PTU Benchmark Suite v{__version__}")
    _print_project_banner(config)
    print(f"  Running:    {', '.join(keys)}")

    for key in keys:
        scenario_cls = SCENARIOS[key]
        print_header(f"Scenario {key}: {scenario_cls.description}", char="-")
        scenario = scenario_cls(config)
        result = scenario.run()
        print_scenario_summary(result)
        all_results.append(result)

    if export and all_results:
        json_path = export_json(all_results, output_dir=output_dir)
        csv_path = export_csv_summary(all_results, output_dir=output_dir)

        print(f"\n  Results exported:")
        print(f"    JSON              → {json_path}")
        print(f"    CSV               → {csv_path}")

        if generate_reports:
            target = report_dir if report_dir is not None else output_dir
            # Generate executive (long-form) and one-page business reports
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
) -> None:
    """
    Run the same scenarios against two projects and emit reports.

    Layout (A = ``--project`` = subject, B = ``--compare-with`` = baseline):

        results/<bundle>/results/
        └── <subject_model_code>/                ← model report folder
            ├── executive_report.md             (flagship A/B comparison)
            ├── business_report.docx            (flagship A/B DOCX)
            ├── metrics.csv                     (side-by-side raw numbers)
            ├── subject_only_executive_report.md  (PTU-only deep dive)
            ├── subject_only_business_report.docx (PTU-only DOCX)
            ├── figures/                        (own + comparison-prefixed)
            ├── <dir_a.name>/                   ← raw subject data only
            └── <dir_b.name>/                   ← raw baseline data only
    """
    keys = scenario_keys or list(SCENARIOS.keys())
    bundle = Path(output_dir)
    bundle.mkdir(parents=True, exist_ok=True)

    # Use results/ subfolder if it exists (dated bundle layout)
    results_sub = bundle / "results"
    if results_sub.exists():
        base = results_sub
    else:
        base = bundle

    # ── Model folder name (subject's model_code) ──────────────────
    # Both projects often run on the same underlying model; group all
    # rendered reports under the subject's model_code so the dated
    # bundle is organized by model rather than by quota tier.
    subject_model_code = (
        (config_a.project.model_code if config_a.project else "")
        or config_a.model_id
        or dir_a.name
    )
    model_dir = base / subject_model_code
    model_dir.mkdir(parents=True, exist_ok=True)

    # Raw-data subfolders live under the model folder.
    sub_a = model_dir / dir_a.name  # subject (PTU) raw data
    sub_b = model_dir / dir_b.name  # baseline (Token API) raw data

    print_header(f"A/B Run — {dir_a.name}  vs  {dir_b.name}")
    print(f"  Scenarios:    {', '.join(keys)}")
    print(f"  Bundle:       {bundle}")
    print(f"  Model folder: {model_dir}")

    # ── Run A (subject) — raw data → sub_a, reports → model_dir ──
    # Use subject_only_* filenames so the canonical names remain free
    # for the flagship A/B comparison reports.
    print_header(f"[A] {dir_a.name}", char="-")
    results_a = run_benchmarks(
        config=config_a,
        scenario_keys=keys,
        export=True,
        output_dir=str(sub_a),
        report_dir=str(model_dir),
        executive_filename="subject_only_executive_report.md",
        business_filename="subject_only_business_report.docx",
    )

    # ── Run B (baseline) — raw data only, no standalone reports ──
    print_header(f"[B] {dir_b.name}", char="-")
    results_b = run_benchmarks(
        config=config_b,
        scenario_keys=keys,
        export=True,
        output_dir=str(sub_b),
        generate_reports=False,
    )

    name_a = _project_label(config_a, dir_a)
    name_b = _project_label(config_b, dir_b)
    print_project_comparison(name_a, results_a, name_b, results_b)

    # ── Export comparison files into the model folder ────────────
    # Subject = A (PTU/--project), Baseline = B (Token API/--compare-with).
    # The "comparison_" chart prefix avoids PNG name collisions with
    # the subject's standalone charts in the same figures/ folder.
    # These are the CANONICAL reports — they get the unprefixed filenames.
    cmp_path = export_comparison_csv(
        name_b, results_b, name_a, results_a,
        output_dir=model_dir,
        filename="metrics.csv",
    )

    # Executive comparison report (long-form) — THE flagship deliverable
    exec_cmp_path = export_executive_report(
        results=results_a,
        output_dir=model_dir,
        config=config_a,
        compare_results=results_b,
        compare_config=config_b,
        compare_name=name_b,
        primary_name=name_a,
        filename="executive_report.md",
        chart_prefix="comparison_",
    )

    # One-page business comparison report
    biz_cmp_path = export_business_report(
        results=results_a,
        output_dir=model_dir,
        config=config_a,
        compare_results=results_b,
        compare_config=config_b,
        compare_name=name_b,
        primary_name=name_a,
        filename="business_report.docx",
    )

    # ── Final summary ──────────────────────────────────────────
    print_header("Reports", char="=")
    print(f"  Model folder                     → {model_dir}/")
    print()
    print(f"  ⭐ Executive Report (A/B full)   → {exec_cmp_path}")
    print(f"  ⭐ Business Report  (A/B full)   → {biz_cmp_path}")
    print(f"     Metrics CSV                   → {cmp_path}")
    print()
    print(f"     Subject-only deep dive        → {model_dir}/subject_only_executive_report.md")
    print(f"     Subject-only DOCX             → {model_dir}/subject_only_business_report.docx")
    print()
    print(f"  Raw data:")
    print(f"     A — {name_a:<28} → {sub_a}/")
    print(f"     B — {name_b:<28} → {sub_b}/")


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

        # Build dated result folder: {date}_{modelA}_vs_{modelB}_{NNN}/results
        if args.output_dir == "results":
            model_a_name = (config_a.project.model_name if config_a.project
                            else config_a.model_id or dir_a.name)
            model_b_name = (config_b.project.model_name if config_b.project
                            else config_b.model_id or dir_b.name)
            results_dir = build_result_folder(
                "results", model_a_name, compare_with=model_b_name,
            )
            args.output_dir = str(results_dir.parent)  # bundle dir (parent of results/)
        else:
            # User-specified dir: create results/ inside it
            results_sub = Path(args.output_dir) / "results"
            results_sub.mkdir(parents=True, exist_ok=True)
            args.output_dir = str(results_sub.parent)

        run_compare(
            config_a=config_a, dir_a=dir_a,
            config_b=config_b, dir_b=dir_b,
            scenario_keys=args.scenarios,
            output_dir=args.output_dir,
        )
        return

    # ── Single-project / .env mode ────────────────────────────────────
    if args.project:
        config, project_dir = _load_project_config(args.project)
        if args.output_dir == "results":
            model_name = (config.project.model_name if config.project
                          else config.model_id or project_dir.name)
            results_dir = build_result_folder(
                project_dir / "results", model_name,
            )
            args.output_dir = str(results_dir)
        else:
            # User-specified: create results/ subfolder inside
            results_sub = Path(args.output_dir) / "results"
            results_sub.mkdir(parents=True, exist_ok=True)
            args.output_dir = str(results_sub)
    else:
        config = BenchmarkConfig.from_env(args.env)
        if args.output_dir == "results":
            model_name = config.model_id or "benchmark"
            results_dir = build_result_folder("results", model_name)
            args.output_dir = str(results_dir)
        else:
            results_sub = Path(args.output_dir) / "results"
            results_sub.mkdir(parents=True, exist_ok=True)
            args.output_dir = str(results_sub)

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

    run_benchmarks(
        config=config,
        scenario_keys=args.scenarios,
        export=True,  # always export reports
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
