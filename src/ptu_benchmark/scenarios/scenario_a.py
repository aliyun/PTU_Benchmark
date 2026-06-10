"""
Scenario A: Single Request Baseline (TTFT + TPS)
=================================================

Establishes baseline latency for a single request with no contention.
Runs multiple iterations of short and long prompts to measure:
  - TTFT  (Time To First Token)
  - TPS   (Tokens Per Second during generation)
"""

from __future__ import annotations

import openai

from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import print_single_result
from ptu_benchmark.scenarios.base import BaseScenario
from ptu_benchmark.utils import PROMPT_SHORT, PROMPT_LONG, ScenarioResult, SingleRequestResult


class ScenarioA(BaseScenario):
    """Single-request baseline latency benchmark."""

    name = "A"
    display_name = "Latency Baseline"
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
            result = self._single_request_openai(client, PROMPT_SHORT, request_id=i)
            print_single_result(result, label=f"Short Run {i + 1}")
            all_results.append(result)

        print(f"\n--- Long generation ({self.LONG_RUNS} runs) ---")
        for i in range(self.LONG_RUNS):
            result = self._single_request_openai(
                client, PROMPT_LONG, request_id=self.SHORT_RUNS + i
            )
            print_single_result(result, label=f"Long Run {i + 1}")
            all_results.append(result)

        return ScenarioResult(
            scenario=self.name,
            label=self.description,
            results=all_results,
        )
