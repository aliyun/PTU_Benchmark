"""
Higher-level workflow integration tests.

Verifies that running scenarios with mocked APIs produces the expected
on-disk artefacts (JSON results, CSV summary). All file I/O happens in
``tmp_path`` so the test never pollutes the repo.
"""

from __future__ import annotations

import csv
import json
from unittest.mock import MagicMock, patch

import pytest

from ptu_benchmark.reporter import export_csv_summary, export_json
from ptu_benchmark.scenarios.scenario_a import ScenarioA
from ptu_benchmark.scenarios.scenario_b import ScenarioB
from ptu_benchmark.utils import SingleRequestResult

from tests.conftest import make_success_stream


pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# Workflow: run scenarios → export artefacts
# ─────────────────────────────────────────────────────────────────

class TestWorkflowIntegration:
    def test_export_files_structure(self, benchmark_config, tmp_path):
        """End-to-end: mocked scenarios A+B produce JSON and CSV outputs."""
        # ── Scenario A: mock the OpenAI SDK ─────────────────────────
        client = MagicMock()
        client.chat.completions.create.side_effect = (
            lambda *a, **kw: make_success_stream(
                num_content_chunks=3, completion_tokens=40
            )
        )

        # ── Scenario B: mock the aiohttp helper ─────────────────────
        async def _fake_concurrent(config, prompt, concurrency, max_tokens):
            return [
                SingleRequestResult(
                    request_id=i,
                    ttft_ms=110.0 + i,
                    tps=42.0,
                    tokens=64,
                    total_seconds=1.4,
                )
                for i in range(concurrency)
            ]

        with patch.object(ScenarioA, "SHORT_RUNS", 1), \
             patch.object(ScenarioA, "LONG_RUNS", 1), \
             patch("ptu_benchmark.scenarios.scenario_a.openai.OpenAI",
                   return_value=client), \
             patch("ptu_benchmark.scenarios.scenario_b.run_concurrent_requests",
                   side_effect=_fake_concurrent):
            results = [
                ScenarioA(benchmark_config).run(),
                ScenarioB(benchmark_config).run(),
            ]

        # ── Export to a per-test temporary directory ────────────────
        out_dir = tmp_path / "results"
        json_path = export_json(results, output_dir=out_dir)
        csv_path = export_csv_summary(results, output_dir=out_dir)

        # JSON file ─────────────────────────────────────────────────
        assert json_path.exists()
        assert json_path.parent == out_dir
        payload = json.loads(json_path.read_text())
        assert "timestamp" in payload
        assert len(payload["scenarios"]) == 2
        scenario_keys = {s["scenario"] for s in payload["scenarios"]}
        assert scenario_keys == {"A", "B"}
        # Each scenario carries per-request results.
        for s in payload["scenarios"]:
            assert s["total_requests"] >= 1
            assert isinstance(s["results"], list)

        # CSV summary ───────────────────────────────────────────────
        assert csv_path.exists()
        rows = list(csv.DictReader(csv_path.read_text().splitlines()))
        assert len(rows) == 2
        assert {r["scenario"] for r in rows} == {"A", "B"}
        for r in rows:
            assert r["total"]
            assert r["success"]
            # TTFT and TPS columns are populated for successful runs.
            assert r["ttft_p50_ms"]
            assert r["tps_avg"]

    def test_export_handles_failure_only_results(self, benchmark_config, tmp_path):
        """Exporters tolerate scenarios where every request errored."""
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("boom")

        with patch.object(ScenarioA, "SHORT_RUNS", 1), \
             patch.object(ScenarioA, "LONG_RUNS", 0), \
             patch("ptu_benchmark.scenarios.scenario_a.openai.OpenAI",
                   return_value=client):
            results = [ScenarioA(benchmark_config).run()]

        json_path = export_json(results, output_dir=tmp_path)
        csv_path = export_csv_summary(results, output_dir=tmp_path)

        assert json_path.exists()
        assert csv_path.exists()
        payload = json.loads(json_path.read_text())
        sc = payload["scenarios"][0]
        assert sc["successful"] == 0
        assert sc["failed"] == 1
