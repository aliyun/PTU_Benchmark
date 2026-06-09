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
from tabulate import tabulate

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
        # Per-batch metrics for the TPM utilization summary at the end.
        batch_summaries: list[dict] = []

        # Announce auto-derived levels (if applicable) so the user knows
        # the sweep matches their provisioned quota.
        if getattr(self.config, "concurrency_levels_auto_derived", False):
            print(
                f"  (concurrency_levels auto-derived from quota: "
                f"{self.config.concurrency_levels})"
            )

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

            batch_summaries.append({
                "concurrency": concurrency,
                "success": len(ok),
                "rate_limited": len(rl),
                "errors": len(errs) - len(rl),
                "tokens": total_tokens,
                "wall": batch_wall,
                "agg_tpm": agg_tpm,
            })
            all_results.extend(results)

        # ── TPM utilization summary vs provisioned output_tpm quota ─────
        self._print_tpm_utilization_summary(batch_summaries)

        return ScenarioResult(
            scenario=self.name,
            label=self.description,
            results=all_results,
        )

    def _print_tpm_utilization_summary(self, batches: list[dict]) -> None:
        """
        Print a per-concurrency table comparing achieved aggregate TPM
        to the provisioned ``output_tpm`` quota (from project.yaml).

        Skipped silently when no project quota is configured.
        """
        proj = getattr(self.config, "project", None)
        quota = getattr(proj, "output_tpm", 0) if proj else 0
        if not quota or not batches:
            return

        print("\n  === TPM Utilization vs Provisioned Quota ===")
        print(f"  Provisioned output TPM: {quota:,}")

        rows: list[list[str]] = []
        for b in batches:
            util_pct = b["agg_tpm"] / quota * 100 if quota else 0.0
            if b["rate_limited"] > 0:
                status = "THROTTLED (429)"
            elif util_pct >= 100:
                status = "OVER QUOTA"
            elif util_pct >= 80:
                status = "NEAR QUOTA"
            else:
                status = "OK"
            rows.append([
                str(b["concurrency"]),
                f"{b['agg_tpm']:,.0f}",
                f"{quota:,}",
                f"{util_pct:.1f}%",
                str(b["rate_limited"]),
                status,
            ])

        print(tabulate(
            rows,
            headers=["Concurrency", "Achieved TPM", "Quota TPM",
                     "Util %", "429s", "Status"],
            tablefmt="grid",
        ))

