"""
CLI entry point for PTU Benchmark.

Usage examples:
    # Run all scenarios (uses root .env)
    python -m ptu_benchmark

    # Run against a specific project folder
    python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K

    # Project + specific scenarios + export
    python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --scenarios A B D --export

    # A/B compare two projects (e.g. PTU vs Token-API) — emits 3 reports
    python -m ptu_benchmark --project projects/ptu --compare-with projects/token-api --scenarios A B

    # List available scenarios
    python -m ptu_benchmark --list

    # Use a specific .env file (legacy mode)
    python -m ptu_benchmark --env /path/to/.env
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ptu_benchmark import __version__
from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import (
    export_comparison_csv,
    export_csv_summary,
    export_json,
    print_header,
    print_project_comparison,
    print_scenario_summary,
)
from ptu_benchmark.scenarios import SCENARIOS
from ptu_benchmark.utils import ScenarioResult


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
             "(A, B, comparison) into a single bundle directory. Export is implicit.",
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
    """Load a BenchmarkConfig from a project folder, exiting on error."""
    project_dir = Path(path_str)
    if not project_dir.is_dir():
        print(f"Error: project directory not found — {project_dir}")
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
) -> list[ScenarioResult]:
    """Run the selected scenarios for one config and optionally export results."""
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
        print(f"    JSON → {json_path}")
        print(f"    CSV  → {csv_path}")

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
    Run the same scenarios against two projects and emit three reports
    (A, B, A-vs-B) into a single bundle directory.
    """
    keys = scenario_keys or list(SCENARIOS.keys())
    bundle = Path(output_dir)
    bundle.mkdir(parents=True, exist_ok=True)
    sub_a = bundle / dir_a.name
    sub_b = bundle / dir_b.name

    print_header(f"A/B Run — {dir_a.name}  vs  {dir_b.name}")
    print(f"  Scenarios: {', '.join(keys)}")
    print(f"  Bundle:    {bundle}")

    print_header(f"[A] {dir_a.name}", char="-")
    results_a = run_benchmarks(
        config=config_a,
        scenario_keys=keys,
        export=True,
        output_dir=str(sub_a),
    )

    print_header(f"[B] {dir_b.name}", char="-")
    results_b = run_benchmarks(
        config=config_b,
        scenario_keys=keys,
        export=True,
        output_dir=str(sub_b),
    )

    name_a = _project_label(config_a, dir_a)
    name_b = _project_label(config_b, dir_b)
    print_project_comparison(name_a, results_a, name_b, results_b)

    cmp_path = export_comparison_csv(
        name_a, results_a, name_b, results_b,
        output_dir=bundle,
    )

    # ── Final 3-report summary ─────────────────────────────────────
    print_header("Reports", char="=")
    print(f"  A — {name_a:<30} → {sub_a}/")
    print(f"  B — {name_b:<30} → {sub_b}/")
    print(f"  Δ — comparison                  → {cmp_path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return

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

        # Default the comparison output dir to a top-level results/comparisons/ folder
        if args.output_dir == "results":
            args.output_dir = str(Path("results") / f"{dir_a.name}_vs_{dir_b.name}")

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
            args.output_dir = str(project_dir / "results")
    else:
        config = BenchmarkConfig.from_env(args.env)

    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for err in errors:
            print(f"  - {err}")
        print("\nCopy .env.example to .env and fill in your values:")
        print("  cp .env.example .env")
        if not args.project:
            print("\nOr use project-based configuration:")
            print("  python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K")
        sys.exit(1)

    run_benchmarks(
        config=config,
        scenario_keys=args.scenarios,
        export=args.export,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
