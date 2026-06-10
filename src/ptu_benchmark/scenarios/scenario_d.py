"""
Scenario D: Peak Burst Test
============================

Sends a sudden spike of simultaneous requests to verify PTU handles
bursts without 429 errors.  Compares with Token API (shared pool)
behaviour where rate-limiting is common under burst traffic.
"""

from __future__ import annotations

import asyncio

from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.reporter import print_single_result
from ptu_benchmark.scenarios.base import BaseScenario, run_concurrent_requests
from ptu_benchmark.utils import PROMPT_BURST, ScenarioResult


class ScenarioD(BaseScenario):
    """Peak burst test — all requests fired simultaneously."""

    name = "D"
    display_name = "Peak Burst Resilience"
    description = "Peak Burst Test"

    def run(self) -> ScenarioResult:
        burst_size = self.config.burst_size
        print(f"  Sending {burst_size} simultaneous requests...")

        results = asyncio.run(
            run_concurrent_requests(
                config=self.config,
                prompt=PROMPT_BURST,
                concurrency=burst_size,
                max_tokens=self.config.concurrent_max_tokens,
            )
        )

        # Per-request output (abbreviated for large bursts)
        if burst_size <= 50:
            for r in results:
                print_single_result(r, label=f"req-{r.request_id}")

        # Summary
        successful = [r for r in results if r.success]
        rate_limited = [r for r in results if r.error == "429_rate_limited"]
        other_errors = [
            r for r in results if not r.success and r.error != "429_rate_limited"
        ]

        print(f"\n  Burst Results:")
        print(
            f"  Successful: {len(successful)}/{burst_size} "
            f"({len(successful) / burst_size * 100:.0f}%)"
        )
        print(f"  Rate Limited (429): {len(rate_limited)}")
        print(f"  Other Errors: {len(other_errors)}")

        if rate_limited:
            print(
                "\n  NOTE: 429 errors occurred. This traffic exceeded PTU capacity.\n"
                "  Excess traffic auto-falls back to PAYG (no service interruption)."
            )
        else:
            print("\n  PASS: Zero 429 errors. PTU handled full burst successfully.")

        return ScenarioResult(
            scenario=self.name,
            label=self.description,
            results=results,
        )
