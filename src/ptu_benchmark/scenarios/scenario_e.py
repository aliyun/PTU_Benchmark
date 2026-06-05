"""
Scenario E: Long Context Test
===============================

Measures performance with large input contexts (32K, 64K, 128K tokens).
Relevant for RAG, document processing, and summarisation use cases.
"""

from __future__ import annotations

import time

import openai

from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import print_single_result
from ptu_benchmark.scenarios.base import BaseScenario
from ptu_benchmark.utils import (
    ScenarioResult,
    SingleRequestResult,
    generate_long_context,
)


class ScenarioE(BaseScenario):
    """Long-context benchmark across multiple input sizes."""

    name = "E"
    description = "Long Context Test"

    RUNS_PER_SIZE: int = 3

    def run(self) -> ScenarioResult:
        client = openai.OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

        all_results: list[SingleRequestResult] = []
        req_id = 0

        for label, token_count in self.config.context_sizes.items():
            print(f"\n--- {label} input tokens ---")
            context = generate_long_context(token_count)
            prompt = (
                f"Based on the following document, provide a 200-word "
                f"executive summary:\n\n{context}"
            )

            for i in range(self.RUNS_PER_SIZE):
                result = self._single_request(client, prompt, request_id=req_id)
                print_single_result(result, label=f"{label} Run {i + 1}")
                all_results.append(result)
                req_id += 1

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
                # Final chunk may carry usage with empty choices.
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
