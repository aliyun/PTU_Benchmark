"""
Integration tests for benchmark scenarios with mocked API responses.

All tests are network-free: the OpenAI SDK and the aiohttp-based
``run_concurrent_requests`` helper are mocked so scenarios exercise
real aggregation / control-flow logic without contacting any server.

Run only the integration tests with:

    python -m pytest tests/ -m integration -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from ptu_benchmark.scenarios.scenario_a import ScenarioA
from ptu_benchmark.scenarios.scenario_b import ScenarioB
from ptu_benchmark.scenarios.scenario_d import ScenarioD
from ptu_benchmark.scenarios.scenario_e import ScenarioE
from ptu_benchmark.utils import ScenarioResult, SingleRequestResult

from tests.conftest import make_openai_chunk, make_success_stream


pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _make_openai_client_mock(stream_factory):
    """
    Build a mock that mimics the synchronous OpenAI SDK surface used
    by ``BaseScenario._single_request_openai``.

    ``stream_factory`` is a no-arg callable returning a fresh iterable
    each time ``chat.completions.create`` is invoked (the SDK returns a
    one-shot iterator that the scenarios iterate with a plain ``for``).
    """
    client = MagicMock()
    client.chat.completions.create.side_effect = lambda *a, **kw: stream_factory()
    return client


def _scenario_results(*results: SingleRequestResult) -> list[SingleRequestResult]:
    return list(results)


# ─────────────────────────────────────────────────────────────────
# Scenario A — single-request baseline
# ─────────────────────────────────────────────────────────────────

class TestScenarioAIntegration:
    def test_scenario_a_single_request(self, benchmark_config):
        """Mocked successful streaming response → ScenarioResult with TTFT/TPS > 0."""
        # Keep the test brisk: 1 short run + 1 long run.
        with patch.object(ScenarioA, "SHORT_RUNS", 1), \
             patch.object(ScenarioA, "LONG_RUNS", 1), \
             patch("ptu_benchmark.scenarios.scenario_a.openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value = _make_openai_client_mock(
                lambda: make_success_stream(num_content_chunks=4, completion_tokens=50)
            )
            scenario = ScenarioA(benchmark_config)
            result = scenario.run()

        assert isinstance(result, ScenarioResult)
        assert result.scenario == "A"
        assert len(result.results) == 2          # 1 short + 1 long
        assert len(result.successful) == 2
        assert len(result.failed) == 0

        for r in result.successful:
            # TTFT must be a positive number of milliseconds.
            assert r.ttft_ms is not None and r.ttft_ms > 0
            # API-reported usage was 50 completion tokens.
            assert r.tokens == 50
            # TPS = tokens / generation-time, both strictly positive.
            assert r.tps > 0

    def test_scenario_a_handles_429(self, benchmark_config):
        """Mocked 429 from OpenAI client → captured as error, no crash."""

        class FakeRateLimitError(Exception):
            pass

        def _raise(*_a, **_kw):
            raise FakeRateLimitError("Error code: 429 - rate limit exceeded")

        client = MagicMock()
        client.chat.completions.create.side_effect = _raise

        with patch.object(ScenarioA, "SHORT_RUNS", 2), \
             patch.object(ScenarioA, "LONG_RUNS", 0), \
             patch("ptu_benchmark.scenarios.scenario_a.openai.OpenAI",
                   return_value=client):
            result = ScenarioA(benchmark_config).run()

        assert len(result.results) == 2
        # All requests must surface the error rather than crashing.
        assert all(r.error is not None for r in result.results)
        assert all("429" in r.error for r in result.results)
        assert len(result.failed) == 2
        assert len(result.successful) == 0


# ─────────────────────────────────────────────────────────────────
# Scenario B — concurrent load
# ─────────────────────────────────────────────────────────────────

class TestScenarioBIntegration:
    def test_scenario_b_concurrent(self, benchmark_config):
        """Mocked concurrent requests → results aggregated across all levels."""
        # Two concurrency levels (2 and 4) → 2 + 4 = 6 total responses.
        async def _fake_run_concurrent(config, prompt, concurrency, max_tokens):
            return [
                SingleRequestResult(
                    request_id=i,
                    ttft_ms=120.0 + i,
                    tps=45.0,
                    tokens=64,
                    total_seconds=1.5,
                )
                for i in range(concurrency)
            ]

        with patch(
            "ptu_benchmark.scenarios.scenario_b.run_concurrent_requests",
            side_effect=_fake_run_concurrent,
        ) as mock_run:
            result = ScenarioB(benchmark_config).run()

        assert mock_run.call_count == len(benchmark_config.concurrency_levels)
        assert result.scenario == "B"
        assert len(result.results) == sum(benchmark_config.concurrency_levels)
        assert len(result.successful) == len(result.results)

        # Each call to run_concurrent_requests received the right concurrency.
        observed = [kw["concurrency"] for _, kw in mock_run.call_args_list]
        assert observed == benchmark_config.concurrency_levels


# ─────────────────────────────────────────────────────────────────
# Scenario D — peak burst
# ─────────────────────────────────────────────────────────────────

class TestScenarioDIntegration:
    def test_scenario_d_burst(self, benchmark_config):
        """Mocked burst → all `burst_size` requests dispatched."""
        captured: dict = {}

        async def _fake_run_concurrent(config, prompt, concurrency, max_tokens):
            captured["concurrency"] = concurrency
            return [
                SingleRequestResult(
                    request_id=i,
                    ttft_ms=200.0,
                    tps=30.0,
                    tokens=64,
                    total_seconds=2.0,
                )
                for i in range(concurrency)
            ]

        with patch(
            "ptu_benchmark.scenarios.scenario_d.run_concurrent_requests",
            side_effect=_fake_run_concurrent,
        ) as mock_run:
            result = ScenarioD(benchmark_config).run()

        assert mock_run.call_count == 1
        assert captured["concurrency"] == benchmark_config.burst_size
        assert len(result.results) == benchmark_config.burst_size
        assert all(r.success for r in result.results)
        assert len(result.rate_limited) == 0

    def test_scenario_d_burst_with_rate_limits(self, benchmark_config):
        """A subset of burst requests are 429-rate-limited; results captured."""
        async def _fake(config, prompt, concurrency, max_tokens):
            out = []
            for i in range(concurrency):
                if i % 5 == 0:
                    out.append(SingleRequestResult(
                        request_id=i, error="429_rate_limited",
                        total_seconds=0.05,
                    ))
                else:
                    out.append(SingleRequestResult(
                        request_id=i, ttft_ms=180.0, tps=28.0,
                        tokens=64, total_seconds=1.8,
                    ))
            return out

        with patch(
            "ptu_benchmark.scenarios.scenario_d.run_concurrent_requests",
            side_effect=_fake,
        ):
            result = ScenarioD(benchmark_config).run()

        assert len(result.rate_limited) > 0
        assert len(result.successful) > 0
        assert len(result.results) == benchmark_config.burst_size


# ─────────────────────────────────────────────────────────────────
# Scenario E — long context
# ─────────────────────────────────────────────────────────────────

class TestScenarioEIntegration:
    def test_scenario_e_long_context(self, benchmark_config):
        """Long-context scenario aggregates RUNS_PER_SIZE results per size."""
        with patch.object(ScenarioE, "RUNS_PER_SIZE", 1), \
             patch("ptu_benchmark.scenarios.scenario_e.openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value = _make_openai_client_mock(
                lambda: make_success_stream(num_content_chunks=3, completion_tokens=30)
            )
            result = ScenarioE(benchmark_config).run()

        # benchmark_config sets a single context size key for speed.
        expected = len(benchmark_config.context_sizes) * 1
        assert len(result.results) == expected
        assert all(r.success for r in result.results)


# ─────────────────────────────────────────────────────────────────
# Cross-scenario timeout handling
# ─────────────────────────────────────────────────────────────────

class TestTimeoutHandling:
    def test_scenario_handles_timeout(self, benchmark_config):
        """asyncio.TimeoutError from the OpenAI client is captured, not raised."""
        client = MagicMock()
        client.chat.completions.create.side_effect = asyncio.TimeoutError(
            "request timed out"
        )

        with patch.object(ScenarioA, "SHORT_RUNS", 1), \
             patch.object(ScenarioA, "LONG_RUNS", 0), \
             patch("ptu_benchmark.scenarios.scenario_a.openai.OpenAI",
                   return_value=client):
            result = ScenarioA(benchmark_config).run()

        assert len(result.results) == 1
        only = result.results[0]
        assert only.error is not None
        assert only.success is False
        # The error message comes from str(asyncio.TimeoutError(...)), which
        # may be empty in some Python versions — so just assert presence.
        assert isinstance(only.error, str)

    def test_scenario_b_timeout_propagated_as_error(self, benchmark_config):
        """If concurrent requests time out, results carry the error string."""
        async def _fake(config, prompt, concurrency, max_tokens):
            return [
                SingleRequestResult(
                    request_id=i,
                    error="TimeoutError: request timed out",
                    total_seconds=float(config.request_timeout),
                )
                for i in range(concurrency)
            ]

        with patch(
            "ptu_benchmark.scenarios.scenario_b.run_concurrent_requests",
            side_effect=_fake,
        ):
            result = ScenarioB(benchmark_config).run()

        assert len(result.successful) == 0
        assert len(result.failed) == sum(benchmark_config.concurrency_levels)
        assert all("Timeout" in r.error for r in result.failed)
