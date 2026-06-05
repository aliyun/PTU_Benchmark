"""Tests for shared utilities."""

import pytest
from ptu_benchmark.utils import (
    SingleRequestResult,
    ScenarioResult,
    Timer,
    generate_long_context,
    parse_sse_tokens,
)


# ── SingleRequestResult ────────────────────────────────────────

class TestSingleRequestResult:
    def test_success(self):
        r = SingleRequestResult(request_id=0, ttft_ms=120.0, tps=45.0, tokens=100)
        assert r.success is True

    def test_failure_with_error(self):
        r = SingleRequestResult(request_id=1, error="connection_timeout")
        assert r.success is False

    def test_failure_no_ttft(self):
        r = SingleRequestResult(request_id=2, ttft_ms=None, tokens=0)
        assert r.success is False


# ── ScenarioResult ─────────────────────────────────────────────

class TestScenarioResult:
    def test_successful_filter(self):
        results = [
            SingleRequestResult(request_id=0, ttft_ms=100.0, tps=40.0, tokens=50),
            SingleRequestResult(request_id=1, error="429_rate_limited"),
            SingleRequestResult(request_id=2, ttft_ms=200.0, tps=30.0, tokens=80),
        ]
        sr = ScenarioResult(scenario="X", label="Test", results=results)
        assert len(sr.successful) == 2
        assert len(sr.failed) == 1
        assert len(sr.rate_limited) == 1

    def test_to_dict(self):
        results = [
            SingleRequestResult(request_id=0, ttft_ms=100.0, tps=40.0, tokens=50),
        ]
        sr = ScenarioResult(scenario="A", label="Test", results=results)
        d = sr.to_dict()
        assert d["scenario"] == "A"
        assert d["total_requests"] == 1
        assert d["successful"] == 1


# ── Timer ──────────────────────────────────────────────────────

class TestTimer:
    def test_elapsed(self):
        import time
        with Timer() as t:
            time.sleep(0.05)
        assert t.elapsed >= 0.04
        assert t.elapsed_ms >= 40


# ── generate_long_context ──────────────────────────────────────

class TestGenerateLongContext:
    def test_returns_string(self):
        text = generate_long_context(1000)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_scales_with_tokens(self):
        small = generate_long_context(100)
        large = generate_long_context(10000)
        assert len(large) > len(small)

    def test_minimum_one_repetition(self):
        text = generate_long_context(1)
        assert len(text) > 0

    @pytest.mark.parametrize("target", [1_000, 10_000, 32_000, 64_000, 128_000])
    def test_approximates_target_tokens(self, target: int):
        """
        The generated text length, divided by the ~4 chars/token rule,
        should be within 20% of the requested target token count.
        """
        text = generate_long_context(target)
        approx_tokens = len(text) / 4
        # For tiny targets the floor of // tokens_per_rep can give a
        # whole-extra repetition, so allow a generous lower bound and a
        # tight upper bound (we never want to wildly overshoot).
        assert approx_tokens >= target * 0.8, (
            f"target={target}, approx_tokens={approx_tokens:.0f}"
        )
        assert approx_tokens <= target * 1.25, (
            f"target={target}, approx_tokens={approx_tokens:.0f}"
        )


# ── parse_sse_tokens ───────────────────────────────────────────

class TestParseSseTokens:
    def test_chunk_count_when_no_usage(self):
        """Without a usage block, fall back to counting content chunks."""
        body = (
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n'
            b'data: {"choices":[{"delta":{"content":" world"}}]}\n'
            b'data: {"choices":[{"delta":{"content":"!"}}]}\n'
            b'data: [DONE]\n'
        )
        first_t, tokens = parse_sse_tokens(body)
        assert tokens == 3
        assert first_t is not None

    def test_uses_usage_completion_tokens(self):
        """When the final chunk includes usage, prefer completion_tokens."""
        body = (
            b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n'
            b'data: {"choices":[{"delta":{"content":" there"}}]}\n'
            b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":42,"total_tokens":52}}\n'
            b'data: [DONE]\n'
        )
        first_t, tokens = parse_sse_tokens(body)
        assert tokens == 42  # NOT 2 (chunk count)
        assert first_t is not None

    def test_no_content(self):
        """Empty stream returns zero tokens and no first_token_time."""
        body = b'data: [DONE]\n'
        first_t, tokens = parse_sse_tokens(body)
        assert tokens == 0
        assert first_t is None

    def test_ignores_malformed_lines(self):
        body = (
            b'event: ping\n'
            b'data: not-json\n'
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
        )
        first_t, tokens = parse_sse_tokens(body)
        assert tokens == 1
        assert first_t is not None
