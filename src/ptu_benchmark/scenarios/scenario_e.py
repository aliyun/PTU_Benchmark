"""
Scenario E: Long Context Test
===============================

Measures performance with large input contexts (32K, 64K, 128K tokens).
Relevant for RAG, document processing, and summarisation use cases.
"""

from __future__ import annotations

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
    display_name = "Long Context Performance"
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
                result = self._single_request_openai(
                    client, prompt, request_id=req_id
                )
                print_single_result(result, label=f"{label} Run {i + 1}")
                all_results.append(result)
                req_id += 1

        return ScenarioResult(
            scenario=self.name,
            label=self.description,
            results=all_results,
        )
