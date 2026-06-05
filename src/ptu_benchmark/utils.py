"""
Shared utilities used across all benchmark scenarios.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any


# ─────────────────────────────────────────────
# Prompt library
# ─────────────────────────────────────────────

PROMPT_SHORT = "Explain quantum computing in one paragraph."

PROMPT_LONG = (
    "You are a technical documentation writer. Write a comprehensive 2000-word guide "
    "about implementing a microservices architecture with event-driven communication patterns. "
    "Include sections on: service discovery, message brokers, saga patterns, CQRS, and monitoring."
)

PROMPT_CONCURRENT = (
    "Write a detailed 3-paragraph analysis of cloud computing trends "
    "in the Middle East market for 2026."
)

PROMPT_SUSTAINED = (
    "Generate a detailed technical specification for a REST API endpoint that handles "
    "user authentication with OAuth 2.0, including request/response schemas, error codes, "
    "and rate limiting policies."
)

PROMPT_BURST = (
    "Summarize the key benefits of cloud-native architecture in 3 sentences."
)


# ─────────────────────────────────────────────
# Result data classes
# ─────────────────────────────────────────────

@dataclass
class SingleRequestResult:
    """Result of a single benchmark request."""
    request_id: int = 0
    ttft_ms: float | None = None      # Time-to-first-token in milliseconds
    tps: float = 0.0                   # Tokens per second (generation)
    tokens: int = 0                    # Number of output tokens
    total_seconds: float = 0.0         # Total wall-clock time
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None and self.ttft_ms is not None


@dataclass
class ScenarioResult:
    """Aggregated result for a scenario run."""
    scenario: str = ""
    label: str = ""
    results: list[SingleRequestResult] = field(default_factory=list)

    # ── Aggregate helpers ─────────────────────────────────────────────

    @property
    def successful(self) -> list[SingleRequestResult]:
        return [r for r in self.results if r.success]

    @property
    def failed(self) -> list[SingleRequestResult]:
        return [r for r in self.results if not r.success]

    @property
    def rate_limited(self) -> list[SingleRequestResult]:
        return [r for r in self.results if r.error == "429_rate_limited"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "label": self.label,
            "total_requests": len(self.results),
            "successful": len(self.successful),
            "failed": len(self.failed),
            "rate_limited": len(self.rate_limited),
            "results": [asdict(r) for r in self.results],
        }


# ─────────────────────────────────────────────
# Timing helpers
# ─────────────────────────────────────────────

class Timer:
    """Simple context-manager timer."""

    def __init__(self) -> None:
        self.start: float = 0.0
        self.end: float = 0.0

    def __enter__(self) -> "Timer":
        self.start = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        self.end = time.time()

    @property
    def elapsed(self) -> float:
        return self.end - self.start

    @property
    def elapsed_ms(self) -> float:
        return self.elapsed * 1000


def generate_long_context(target_tokens: int) -> str:
    """
    Generate approximately *target_tokens* worth of text context.

    Uses a ~4 chars-per-token heuristic (true for typical English / BPE
    tokenizers used by Qwen / GPT). The number of repetitions is derived
    from the base text's actual length so the result matches the target
    within ~10–15%, regardless of how the base text is edited later.
    """
    base_text = (
        "The cloud computing market in the Middle East and Africa region "
        "continues to grow rapidly. "
    )
    # Approximate token count of one repetition (~4 chars/token).
    tokens_per_rep = max(1, len(base_text) // 4)
    repetitions = max(1, target_tokens // tokens_per_rep)
    return base_text * repetitions


def parse_sse_tokens(raw_bytes: bytes) -> tuple[float | None, int]:
    """
    Parse an SSE stream body and return (first_token_time, token_count).

    If the stream contains a final ``usage`` block (i.e. the request was
    issued with ``stream_options={"include_usage": True}``), the returned
    token count is the API-reported ``completion_tokens``; otherwise it
    falls back to the number of content chunks observed.

    This is a *synchronous* helper; for async streaming use the
    scenario-level implementations directly.
    """
    first_token_time: float | None = None
    chunk_count = 0
    usage_completion_tokens: int | None = None
    for line in raw_bytes.splitlines():
        decoded = line.decode("utf-8", errors="ignore").strip()
        if not decoded.startswith("data: ") or decoded == "data: [DONE]":
            continue
        try:
            data = json.loads(decoded[6:])
        except json.JSONDecodeError:
            continue

        usage = data.get("usage")
        if isinstance(usage, dict):
            ct = usage.get("completion_tokens")
            if isinstance(ct, int):
                usage_completion_tokens = ct

        choices = data.get("choices") or []
        if not choices:
            continue
        if choices[0].get("delta", {}).get("content"):
            if first_token_time is None:
                first_token_time = time.time()
            chunk_count += 1

    tokens = (
        usage_completion_tokens
        if usage_completion_tokens is not None
        else chunk_count
    )
    return first_token_time, tokens
