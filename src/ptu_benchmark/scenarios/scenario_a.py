"""
Scenario A: Single Request Baseline (TTFT + TPS)
=================================================

Establishes baseline latency for a single request with no contention.
Runs multiple iterations of short and long prompts to measure:
  - TTFT  (Time To First Token)
  - TPS   (Tokens Per Second during generation)
"""

from __future__ import annotations

import time

import openai

from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import print_single_result
from ptu_benchmark.scenarios.base import BaseScenario
from ptu_benchmark.utils import PROMPT_SHORT, PROMPT_LONG, ScenarioResult, SingleRequestResult


class ScenarioA(BaseScenario):
    """Single-request baseline latency benchmark."""

    name = "A"
    description = "Single Request Baseline (TTFT + TPS)"

    SHORT_RUNS: int = 5
    LONG_RUNS: int = 3

    def run(self) -> ScenarioResult:
        """Execute scenario A and return aggregated results."""
        client = openai.OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

        all_results: list[SingleRequestResult] = []

        print(f"\n--- Short prompt ({self.SHORT_RUNS} runs) ---")
        for i in range(self.SHORT_RUNS):
            result = self._single_request(client, PROMPT_SHORT, request_id=i)
            print_single_result(result, label=f"Short Run {i + 1}")
            all_results.append(result)

        print(f"\n--- Long generation ({self.LONG_RUNS} runs) ---")
        for i in range(self.LONG_RUNS):
            result = self._single_request(client, PROMPT_LONG, request_id=self.SHORT_RUNS + i)
            print_single_result(result, label=f"Long Run {i + 1}")
            all_results.append(result)

        return ScenarioResult(
            scenario=self.name,
            label=self.description,
            results=all_results,
        )

    def _single_request(
        self,
        client: openai.OpenAI,
        prompt: str,
        request_id: int = 0,
    ) -> SingleRequestResult:
        """Execute a single streaming request using the OpenAI SDK."""
        start = time.time()
        first_token_time: float | None = None
        chunk_count = 0
        usage_completion_tokens: int | None = None

        try:
            response = client.chat.completions.create(
                model=self.config.model_id,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=self.config.default_max_tokens,
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
