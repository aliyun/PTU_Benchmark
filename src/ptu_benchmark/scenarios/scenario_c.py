"""
Scenario C: Sustained Throughput (30-minute window)
====================================================

Measures maximum sustained TPM (Tokens Per Minute) over a configurable
duration (default 30 minutes). Proves the PTU can maintain its
guaranteed throughput over time.
"""

from __future__ import annotations

import asyncio
import time

import aiohttp

from ptu_benchmark.config import BenchmarkConfig
from ptu_benchmark.scenarios.base import BaseScenario, async_streaming_request
from ptu_benchmark.utils import PROMPT_SUSTAINED, ScenarioResult, SingleRequestResult


class ScenarioC(BaseScenario):
    """Sustained throughput benchmark over a long time window."""

    name = "C"
    description = "Sustained Throughput (30-minute window)"

    def run(self) -> ScenarioResult:
        """Execute scenario C and return aggregated results."""
        results = asyncio.run(self._run_sustained())
        return ScenarioResult(
            scenario=self.name,
            label=self.description,
            results=results,
        )

    async def _run_sustained(self) -> list[SingleRequestResult]:
        duration = self.config.sustained_duration
        concurrency = self.config.sustained_concurrency

        print(
            f"  Duration: {duration}s ({duration // 60} min) | "
            f"Concurrency: {concurrency}"
        )

        url = self._build_url()
        headers = self._build_headers()

        connector = aiohttp.TCPConnector(limit=concurrency + 10)
        all_results: list[SingleRequestResult] = []
        start_time = time.time()
        request_counter = 0
        deadline = start_time + duration

        async with aiohttp.ClientSession(connector=connector) as session:

            async def _worker() -> None:
                """
                A worker keeps firing requests back-to-back until the
                deadline. This maintains *true* sustained concurrency:
                exactly `concurrency` requests are in flight at any
                moment (modulo network jitter), not bursty batches.
                """
                nonlocal request_counter
                while time.time() < deadline:
                    rid = request_counter
                    request_counter += 1
                    payload = {
                        "model": self.config.model_id,
                        "messages": [{"role": "user", "content": PROMPT_SUSTAINED}],
                        "max_tokens": self.config.sustained_max_tokens,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    }
                    result = await async_streaming_request(
                        session, url, headers, payload, request_id=rid
                    )
                    all_results.append(result)

            async def _reporter() -> None:
                """Print a TPM line every minute until the deadline."""
                next_report = start_time + 60.0
                last_minute = 0
                while time.time() < deadline:
                    sleep_for = max(0.0, next_report - time.time())
                    try:
                        await asyncio.sleep(sleep_for)
                    except asyncio.CancelledError:
                        return
                    if time.time() >= deadline:
                        return
                    last_minute += 1
                    next_report += 60.0
                    elapsed = time.time() - start_time
                    total_tokens = sum(r.tokens for r in all_results)
                    tpm = total_tokens / (elapsed / 60) if elapsed > 0 else 0
                    errors_429 = sum(
                        1 for r in all_results if r.error == "429_rate_limited"
                    )
                    print(
                        f"  [{last_minute}min] "
                        f"Requests: {len(all_results)} | "
                        f"TPM: {tpm:,.0f} | "
                        f"429s: {errors_429}"
                    )

            workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
            reporter = asyncio.create_task(_reporter())
            try:
                await asyncio.gather(*workers)
            finally:
                reporter.cancel()
                # Drain the reporter task without raising
                try:
                    await reporter
                except (asyncio.CancelledError, Exception):
                    pass

        # Final summary
        elapsed = time.time() - start_time
        total_tokens = sum(r.tokens for r in all_results)
        avg_tpm = total_tokens / (elapsed / 60) if elapsed > 0 else 0
        errors_429 = sum(1 for r in all_results if r.error == "429_rate_limited")
        print(f"\n  === FINAL RESULTS ({elapsed / 60:.1f} min) ===")
        print(f"  Total Requests: {len(all_results)}")
        print(f"  Total Tokens: {total_tokens:,}")
        print(f"  Average TPM: {avg_tpm:,.0f}")
        err_pct = errors_429 / max(len(all_results), 1) * 100
        print(f"  429 Errors: {errors_429} ({err_pct:.1f}%)")

        return all_results
