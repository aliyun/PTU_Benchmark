"""Tests for the A/B comparison reporter and CLI flag wiring."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from ptu_benchmark.__main__ import build_parser
from ptu_benchmark.reporter import (
    _delta,
    _scenario_metrics,
    export_comparison_csv,
    print_project_comparison,
)
from ptu_benchmark.utils import ScenarioResult, SingleRequestResult


def _make_scenario(
    key: str,
    *,
    ttfts: list[float],
    tps_vals: list[float],
    tokens: int = 100,
    seconds: float = 2.0,
    rate_limited: int = 0,
    errors: int = 0,
) -> ScenarioResult:
    """Build a synthetic ScenarioResult for comparison tests."""
    results: list[SingleRequestResult] = []
    for i, (t, ts) in enumerate(zip(ttfts, tps_vals)):
        results.append(
            SingleRequestResult(
                request_id=i,
                ttft_ms=t,
                tps=ts,
                tokens=tokens,
                total_seconds=seconds,
            )
        )
    for i in range(rate_limited):
        results.append(
            SingleRequestResult(request_id=1000 + i, error="429_rate_limited")
        )
    for i in range(errors):
        results.append(
            SingleRequestResult(request_id=2000 + i, error="boom")
        )
    return ScenarioResult(scenario=key, label=f"Scenario {key}", results=results)


# ── _delta helper ──────────────────────────────────────────────

class TestDelta:
    def test_lower_is_better_b_wins(self):
        # B latency is lower → positive delta
        assert _delta(1000, 500, lower_is_better=True) == "+50.0%"

    def test_lower_is_better_a_wins(self):
        # B latency is higher → negative delta
        assert _delta(500, 1000, lower_is_better=True) == "-100.0%"

    def test_higher_is_better_b_wins(self):
        # B throughput is higher → positive delta
        assert _delta(100, 150, lower_is_better=False) == "+50.0%"

    def test_none_returns_dash(self):
        assert _delta(None, 100, lower_is_better=True) == "—"
        assert _delta(100, None, lower_is_better=False) == "—"

    def test_zero_baseline_returns_dash(self):
        assert _delta(0, 100, lower_is_better=False) == "—"


# ── _scenario_metrics ──────────────────────────────────────────

class TestScenarioMetrics:
    def test_empty_returns_none_metrics(self):
        sr = _make_scenario("A", ttfts=[], tps_vals=[], rate_limited=2, errors=1)
        m = _scenario_metrics(sr)
        assert m["ttft_p50"] is None
        assert m["tps_avg"] is None
        assert m["rate_limited"] == 2
        # `errors` reports total failed requests (incl. 429s): 2 + 1 = 3
        assert m["errors"] == 3

    def test_populated_metrics(self):
        sr = _make_scenario("A", ttfts=[100, 200, 300], tps_vals=[40, 50, 60])
        m = _scenario_metrics(sr)
        assert m["ttft_p50"] == 200
        assert m["tps_avg"] == 50
        assert m["success"] == 3


# ── print_project_comparison ───────────────────────────────────

class TestPrintComparison:
    def test_renders_table_with_winner(self):
        a = _make_scenario("A", ttfts=[1000, 1000, 1000], tps_vals=[20, 20, 20])
        b = _make_scenario("A", ttfts=[500, 500, 500],   tps_vals=[40, 40, 40])

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_project_comparison("token-api", [a], "ptu", [b])
        out = buf.getvalue()

        assert "token-api" in out
        assert "ptu" in out
        assert "A • TTFT P50" in out
        assert "A • TPS (avg)" in out
        # B is twice as fast on TTFT and twice the TPS → both should show "+"
        assert "+50.0%" in out  # TTFT improvement
        assert "+100.0%" in out  # TPS improvement

    def test_no_overlap_prints_message(self):
        a = _make_scenario("A", ttfts=[100], tps_vals=[10])
        b = _make_scenario("B", ttfts=[100], tps_vals=[10])

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_project_comparison("p1", [a], "p2", [b])
        assert "No overlapping scenarios" in buf.getvalue()


# ── export_comparison_csv ──────────────────────────────────────

class TestExportComparisonCSV:
    def test_writes_csv_with_deltas(self, tmp_path: Path):
        a = _make_scenario("A", ttfts=[1000], tps_vals=[20])
        b = _make_scenario("A", ttfts=[500],  tps_vals=[40])

        out = export_comparison_csv(
            "token-api", [a], "ptu", [b],
            output_dir=tmp_path,
        )
        assert out.exists()
        content = out.read_text()
        assert "scenario" in content
        assert "token-api_ttft_p50_ms" in content
        assert "ptu_ttft_p50_ms" in content
        # First data row should be scenario A with deltas
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert lines[1].startswith("A,")
        assert "50.00" in lines[1]   # TTFT improvement %
        assert "100.00" in lines[1]  # TPS improvement %


# ── CLI parser ─────────────────────────────────────────────────

class TestCompareCLI:
    def test_parser_accepts_compare_with(self):
        parser = build_parser()
        args = parser.parse_args([
            "--project", "projects/ptu",
            "--compare-with", "projects/token-api",
            "--scenarios", "A", "B",
        ])
        assert args.project == "projects/ptu"
        assert args.compare_with == "projects/token-api"
        assert args.scenarios == ["A", "B"]

    def test_compare_with_alone_parses(self):
        # Parser shouldn't reject --compare-with by itself; the runtime check does.
        parser = build_parser()
        args = parser.parse_args(["--compare-with", "projects/token-api"])
        assert args.compare_with == "projects/token-api"
        assert args.project is None
