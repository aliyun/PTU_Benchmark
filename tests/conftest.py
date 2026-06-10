"""
Shared pytest fixtures for the PTU-Benchmark test suite.

Provides:
  * A minimal :class:`BenchmarkConfig` with safe, fast defaults so
    integration tests never hit the network.
  * Loaders for the canned SSE / error response fixture files used
    by the scenario integration tests.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ptu_benchmark.config import BenchmarkConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def benchmark_config() -> BenchmarkConfig:
    """Minimal :class:`BenchmarkConfig` for fast, network-free tests."""
    return BenchmarkConfig(
        api_key="test-key-123",
        model_id="qwen-test-model",
        base_url="https://test.api.example.com/v1",
        tps_estimate=100,
        concurrency_levels=[2, 4],
        sustained_duration=5,        # very short for tests
        sustained_concurrency=2,
        burst_size=10,
        request_timeout=10,
        default_max_tokens=100,
        concurrent_max_tokens=64,
        sustained_max_tokens=64,
        # Use a tiny context-size table for Scenario E so tests stay fast.
        context_sizes={"1K": 1000},
    )


@pytest.fixture
def success_sse_data() -> str:
    """Raw SSE payload representing a successful streaming completion."""
    return (FIXTURES_DIR / "streaming_response_success.txt").read_text()


@pytest.fixture
def error_429_data() -> str:
    """Raw 429 rate-limit error response body."""
    return (FIXTURES_DIR / "streaming_response_429.txt").read_text()


@pytest.fixture
def partial_sse_data() -> str:
    """Truncated SSE stream (no [DONE] sentinel)."""
    return (FIXTURES_DIR / "streaming_response_partial.txt").read_text()


# ─────────────────────────────────────────────────────────────────
# Helpers for OpenAI-SDK-style mocks (used by scenarios A and E).
# ─────────────────────────────────────────────────────────────────

def make_openai_chunk(content: str | None = None,
                      *,
                      role: str | None = None,
                      finish_reason: str | None = None,
                      usage_completion_tokens: int | None = None) -> SimpleNamespace:
    """
    Build a fake OpenAI streaming chunk object.

    The scenarios access ``chunk.usage.completion_tokens`` and
    ``chunk.choices[0].delta.content`` so we mimic that attribute
    layout with :class:`SimpleNamespace`.
    """
    delta = SimpleNamespace(content=content, role=role)
    choice = SimpleNamespace(index=0, delta=delta, finish_reason=finish_reason)
    usage = None
    if usage_completion_tokens is not None:
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=usage_completion_tokens,
            total_tokens=10 + usage_completion_tokens,
        )
    return SimpleNamespace(
        id="chatcmpl-test",
        object="chat.completion.chunk",
        created=1234567890,
        model="qwen-test-model",
        choices=[choice],
        usage=usage,
    )


def make_success_stream(num_content_chunks: int = 4,
                        completion_tokens: int = 50,
                        chunk_delay_s: float = 0.001):
    """
    Return a generator that yields a realistic OpenAI streaming response.

    A small ``chunk_delay_s`` is inserted between chunks so wall-clock
    based metrics (TTFT, TPS) are strictly positive even on very fast
    machines.
    """
    import time as _time

    def _gen():
        # Initial role chunk (no content).
        yield make_openai_chunk(role="assistant")
        for i in range(num_content_chunks):
            _time.sleep(chunk_delay_s)
            yield make_openai_chunk(content=f"token{i} ")
        # Final usage-bearing chunk (empty choices content, finish_reason=stop).
        yield make_openai_chunk(
            content=None,
            finish_reason="stop",
            usage_completion_tokens=completion_tokens,
        )

    return _gen()
