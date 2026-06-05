"""
Scenario B: Concurrent Load Test (10 / 50 / 100 parallel requests)
===================================================================

Measures throughput degradation under concurrent load.
PTU should maintain consistent performance across all concurrency levels.
"""

from __future__ import annotations

import asyncio
import time

import numpy as np

from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import print_single_result
from ptu_benchmark.scenarios.base import BaseScenario, run_concurrent_requests
from ptu_benchmark.utils import PROMPT_CONCURRENT, ScenarioResult


class ScenarioB(BaseScenario):
    """Concurrent load benchmark at multiple concurrency levels."""

    name = "B"
    description = "Concurrent Load (10/50/100 parallel requests)"

    def run(self) -> ScenarioResult:
        """Execute scenario B across all configured concurrency levels."""
        all_results: list = []

        for concurrency in self.config.concurrency_levels:
            print(f"\n--- Concurrency: {concurrency} ---")

            # Measure wall-clock duration of the concurrent batch so we can
            # compute an accurate aggregate TPM. Using max(total_seconds)
            # would only approximate it for perfectly synchronized starts.
            batch_start = time.time()
            results = asyncio.run(
                run_concurrent_requests(
                    config=self.config,
                    prompt=PROMPT_CONCURRENT,
                    concurrency=concurrency,
                    max_tokens=self.config.concurrent_max_tokens,
                )
            )
            batch_wall = max(time.time() - batch_start, 1e-3)

            for r in results:
                label = f"req-{r.request_id}"
                print_single_result(r, label=label)

            # Per-batch summary (the aggregate ScenarioResult reports across
            # all concurrency levels and cannot represent a single TPM).
            ok = [r for r in results if r.success]
            rl = [r for r in results if r.error == "429_rate_limited"]
            errs = [r for r in results if not r.success]
            ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
            total_tokens = sum(r.tokens for r in ok)
            agg_tpm = total_tokens / batch_wall * 60

            print(
                f"  -> [c={concurrency}] "
                f"Success: {len(ok)}/{concurrency} | "
                f"429s: {len(rl)} | "
                f"Errors: {len(errs) - len(rl)}"
            )
            if ttfts:
                print(
                    f"     TTFT P50: {np.percentile(ttfts, 50):.0f}ms | "
                    f"P95: {np.percentile(ttfts, 95):.0f}ms | "
                    f"P99: {np.percentile(ttfts, 99):.0f}ms"
                )
            print(
                f"     Wall: {batch_wall:.2f}s | "
                f"Tokens: {total_tokens:,} | "
                f"Aggregate TPM: {agg_tpm:,.0f}"
            )

            all_results.extend(results)

        return ScenarioResult(
            scenario=self.name,
            label=self.description,
            results=all_results,
        )
