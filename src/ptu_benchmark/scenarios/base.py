"""
Scenario base class and shared async infrastructure.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any

import aiohttp

from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import print_scenario_summary, print_single_result
from ptu_benchmark.utils import ScenarioResult, SingleRequestResult


class BaseScenario(ABC):
    """Abstract base for all benchmark scenarios."""

    name: str = ""
    display_name: str = ""
    description: str = ""

    def __init__(self, config: BenchmarkConfig) -> None:
        self.config = config

    @abstractmethod
    def run(self) -> ScenarioResult:
        """Execute the scenario and return aggregated results."""

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _build_url(self) -> str:
        return f"{self.config.base_url}/chat/completions"

    def _single_request_openai(
        self,
        client: Any,
        prompt: str,
        request_id: int = 0,
        *,
        max_tokens: int | None = None,
    ) -> SingleRequestResult:
        """
        Execute a single streaming chat completion using the OpenAI SDK and
        measure TTFT (Time To First Token) and TPS (Tokens Per Second).

        Shared by single-request scenarios (A, E). Prefers the API-reported
        ``completion_tokens`` from the final usage chunk and falls back to a
        chunk count when usage is absent.
        """
        start = time.time()
        first_token_time: float | None = None
        chunk_count = 0
        usage_completion_tokens: int | None = None

        effective_max_tokens = (
            max_tokens if max_tokens is not None else self.config.default_max_tokens
        )

        try:
            response = client.chat.completions.create(
                model=self.config.model_id,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=effective_max_tokens,
                stream_options={"include_usage": True},
            )

            for chunk in response:
                # Final chunk (when include_usage=True) carries usage and
                # may have empty `choices` — capture it first.
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    ct = getattr(usage, "completion_tokens", None)
                    if isinstance(ct, int):
                        usage_completion_tokens = ct
                if chunk.choices and chunk.choices[0].delta.content:
                    if first_token_time is None:
                        first_token_time = time.time()
                    chunk_count += 1
        except Exception as exc:
            return SingleRequestResult(
                request_id=request_id,
                error=str(exc),
                total_seconds=time.time() - start,
            )

        # Prefer API-reported completion_tokens; fall back to chunk count.
        tokens = (
            usage_completion_tokens
            if usage_completion_tokens is not None
            else chunk_count
        )

        end = time.time()
        ttft = (first_token_time - start) * 1000 if first_token_time else None
        gen_time = end - first_token_time if first_token_time else 0
        tps = tokens / gen_time if gen_time > 0 and tokens > 0 else 0.0

        return SingleRequestResult(
            request_id=request_id,
            ttft_ms=ttft,
            tps=tps,
            tokens=tokens,
            total_seconds=end - start,
        )


# ─────────────────────────────────────────────
# Shared async request helpers
# ─────────────────────────────────────────────

async def async_streaming_request(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    request_id: int = 0,
) -> SingleRequestResult:
    """
    Fire a single streaming request via aiohttp and parse the SSE stream.

    Returns a *SingleRequestResult* with TTFT, TPS, and token count.
    """
    start = time.time()
    first_token_time: float | None = None
    chunk_count = 0
    usage_completion_tokens: int | None = None
    error: str | None = None

    try:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status == 429:
                return SingleRequestResult(
                    request_id=request_id,
                    error="429_rate_limited",
                    total_seconds=time.time() - start,
                )
            if resp.status != 200:
                body = await resp.text()
                return SingleRequestResult(
                    request_id=request_id,
                    error=f"HTTP_{resp.status}",
                    total_seconds=time.time() - start,
                )

            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                # Capture usage from the final chunk (when
                # stream_options.include_usage=True). The final chunk
                # may have an empty `choices` list, so handle it first.
                usage = data.get("usage")
                if isinstance(usage, dict):
                    ct = usage.get("completion_tokens")
                    if isinstance(ct, int):
                        usage_completion_tokens = ct

                choices = data.get("choices") or []
                if not choices:
                    continue
                content = choices[0].get("delta", {}).get("content")
                if content:
                    if first_token_time is None:
                        first_token_time = time.time()
                    chunk_count += 1
    except Exception as exc:
        error = str(exc)

    # Prefer the API-reported completion_tokens; fall back to chunk count
    # if the upstream did not return usage info.
    tokens = (
        usage_completion_tokens
        if usage_completion_tokens is not None
        else chunk_count
    )

    end = time.time()
    ttft = (first_token_time - start) * 1000 if first_token_time else None
    gen_time = end - first_token_time if first_token_time else 0
    tps = tokens / gen_time if gen_time > 0 and tokens > 0 else 0.0

    return SingleRequestResult(
        request_id=request_id,
        ttft_ms=ttft,
        tps=tps,
        tokens=tokens,
        total_seconds=end - start,
        error=error,
    )


async def run_concurrent_requests(
    config: BenchmarkConfig,
    prompt: str,
    concurrency: int,
    max_tokens: int = 512,
) -> list[SingleRequestResult]:
    """
    Fire *concurrency* streaming requests simultaneously and return all results.
    """
    url = f"{config.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
        # Ask the API to include accurate token usage in the final chunk
        "stream_options": {"include_usage": True},
    }

    connector = aiohttp.TCPConnector(limit=concurrency + 10)
    timeout = aiohttp.ClientTimeout(
        total=config.request_timeout, connect=10, sock_read=60
    )
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [
            async_streaming_request(session, url, headers, payload, req_id)
            for req_id in range(concurrency)
        ]
        return list(await asyncio.gather(*tasks))
