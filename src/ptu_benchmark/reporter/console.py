"""Console output helpers for benchmark results."""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Sequence

import numpy as np
from tabulate import tabulate

from ptu_benchmark.utils import ScenarioResult, SingleRequestResult

from .utils import _delta, _scenario_display_name, _scenario_metrics


# ─────────────────────────────────────────────
# Console output
# ─────────────────────────────────────────────

def print_header(title: str, char: str = "=") -> None:
    width = 60
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


# ─────────────────────────────────────────────
# Progress bar
# ─────────────────────────────────────────────

_PROGRESS_BAR_WIDTH = 25

# Short display labels for scenario status block
_SCENARIO_SHORT_NAMES: dict[str, str] = {
    "A": "Latency",
    "B": "Concurrency",
    "C": "Sustained",
    "D": "Burst",
    "E": "Context",
}

# Status icons
_ICON_DONE = "✓"
_ICON_RUNNING = "▶"
_ICON_PENDING = "·"


def _bar(completed: int, total: int) -> str:
    """Build an ASCII progress bar string (no brackets)."""
    if total <= 0:
        return "█" * _PROGRESS_BAR_WIDTH
    filled = int(round(_PROGRESS_BAR_WIDTH * completed / total))
    filled = max(0, min(filled, _PROGRESS_BAR_WIDTH))
    return "█" * filled + "░" * (_PROGRESS_BAR_WIDTH - filled)


def _status_icon(status: str) -> str:
    if status == "done":
        return _ICON_DONE
    if status == "running":
        return _ICON_RUNNING
    return _ICON_PENDING


class BenchmarkProgress:
    """Tracks overall benchmark progress state and prints a persistent status block.

    The status block is pipe-friendly (no ANSI escapes, no carriage returns)
    and reprints after each major output section so the user always sees
    current progress at the bottom of the terminal.
    """

    def __init__(self, scenario_keys: list[str], phase: str = "") -> None:
        self.scenario_keys = scenario_keys
        self.scenario_status: dict[str, str] = {k: "pending" for k in scenario_keys}
        self.report_status: dict[str, str] = {}
        self.output_dir: str = ""
        self.phase: str = phase  # e.g. "PTU scenarios", "Token API scenarios"
        self._final: bool = False

    def mark_scenario_running(self, key: str) -> None:
        self.scenario_status[key] = "running"

    def mark_scenario_done(self, key: str) -> None:
        self.scenario_status[key] = "done"

    def set_report_names(self, names: list[str]) -> None:
        """Initialize report tracking with the given report names."""
        for name in names:
            if name not in self.report_status:
                self.report_status[name] = "pending"

    def mark_report_running(self, name: str) -> None:
        self.report_status[name] = "running"

    def mark_report_done(self, name: str) -> None:
        self.report_status[name] = "done"

    def set_output_dir(self, path: str) -> None:
        self.output_dir = path

    def set_phase(self, phase: str) -> None:
        self.phase = phase

    def mark_final(self) -> None:
        self._final = True

    def print(self) -> None:
        """Print the persistent status block."""
        scenarios_done = sum(1 for s in self.scenario_status.values() if s == "done")
        scenarios_total = len(self.scenario_keys)
        reports_done = sum(1 for s in self.report_status.values() if s == "done")
        reports_total = len(self.report_status)

        # Inner width (content between │ and │)
        W = 61
        lines: list[str] = []

        def _row(content: str) -> str:
            """Pad or truncate content to fit exactly W chars inside borders."""
            if len(content) > W:
                content = content[: W - 1] + "…"
            return "│" + content.ljust(W) + "│"

        # ── Top border ──
        lines.append("┌" + "─" * W + "┐")

        # ── Scenario progress line ──
        if self._final:
            progress_line = f"  Progress: [{_bar(scenarios_total, scenarios_total)}] Complete {_ICON_DONE}"
        else:
            progress_line = f"  Progress: [{_bar(scenarios_done, scenarios_total)}] {scenarios_done}/{scenarios_total} scenarios"
            if scenarios_done >= scenarios_total:
                progress_line += f" {_ICON_DONE}"
        if self.phase and not self._final:
            progress_line += f"  ({self.phase})"
        lines.append(_row(progress_line))

        # ── Scenario items ──
        scenario_parts: list[str] = []
        for key in self.scenario_keys:
            icon = _status_icon(self.scenario_status[key])
            short = _SCENARIO_SHORT_NAMES.get(key, key)
            scenario_parts.append(f"{icon} {key} ({short})")

        # Arrange scenario items in rows of 3
        row_items: list[str] = []
        for i, part in enumerate(scenario_parts):
            row_items.append(part)
            if len(row_items) == 3 or i == len(scenario_parts) - 1:
                row_str = "  " + "  ".join(row_items)
                lines.append(_row(row_str))
                row_items = []

        # ── Reports line ──
        if self.report_status:
            if reports_done >= reports_total and reports_total > 0:
                report_line = f"  Reports: [{_bar(reports_total, reports_total)}] Complete {_ICON_DONE}"
            elif any(s == "running" for s in self.report_status.values()):
                report_line = f"  Reports: [{_bar(reports_done, reports_total)}] generating..."
            else:
                report_line = "  Reports: pending"
            lines.append(_row(report_line))

            # Report items
            report_parts: list[str] = []
            for name, status in self.report_status.items():
                icon = _status_icon(status)
                report_parts.append(f"{icon} {name}")

            rrow_items: list[str] = []
            for i, part in enumerate(report_parts):
                rrow_items.append(part)
                if len(rrow_items) == 3 or i == len(report_parts) - 1:
                    rrow_str = "  " + "  ".join(rrow_items)
                    lines.append(_row(rrow_str))
                    rrow_items = []
        elif not self._final:
            lines.append(_row("  Reports: pending"))

        # ── Output dir (final state) ──
        if self.output_dir and self._final:
            lines.append(_row(f"  Output: {self.output_dir}"))

        # ── Bottom border ──
        lines.append("└" + "─" * W + "┘")

        print("\n" + "\n".join(lines))


def print_progress(
    completed: int,
    total: int,
    current_scenario: str = "",
    *,
    scenario_status: dict[str, str] | None = None,
    reports_status: dict[str, str] | None = None,
    output_dir: str = "",
    final: bool = False,
    phase: str = "",
) -> None:
    """Print a persistent status block showing overall benchmark progress.

    Pipe-friendly: emits fresh lines each call (no carriage returns or
    ANSI escapes), so the output stays readable in logs and redirected
    streams.

    Parameters
    ----------
    completed
        Number of scenarios already finished (0..total).
    total
        Total number of scenarios planned for this run.
    current_scenario
        Optional label for backward compat (ignored when scenario_status
        is provided).
    scenario_status
        Dict mapping scenario keys to status strings:
        ``"done"``, ``"running"``, ``"pending"``.
    reports_status
        Dict mapping report names to status strings.
    output_dir
        Path to display in the final state.
    final
        Whether this is the final completion print.
    phase
        Optional phase label for A/B mode (e.g. "PTU scenarios").
    """
    if total <= 0:
        return

    # If scenario_status is provided, use the rich status block
    if scenario_status is not None:
        keys = list(scenario_status.keys())
        progress = BenchmarkProgress(keys, phase=phase)
        progress.scenario_status = dict(scenario_status)
        if reports_status:
            progress.report_status = dict(reports_status)
        if output_dir:
            progress.set_output_dir(output_dir)
        if final:
            progress.mark_final()
        progress.print()
        return

    # Legacy fallback: simple one-line progress (backward compat)
    completed = max(0, min(completed, total))
    bar = _bar(completed, total)

    if completed >= total:
        suffix = "All scenarios complete ✓"
    elif current_scenario:
        suffix = f"Next: {current_scenario}" if completed > 0 else f"Running: {current_scenario}"
    else:
        suffix = "scenarios"

    print(f"\n  Progress: [{bar}] {completed}/{total} — {suffix}")


def print_single_result(result: SingleRequestResult, label: str = "") -> None:
    """Print a single-request result line."""
    tag = f"[{label}] " if label else ""
    if not result.success:
        print(f"{tag}ERROR: {result.error}")
        return
    print(
        f"{tag}TTFT: {result.ttft_ms:.0f}ms | "
        f"TPS: {result.tps:.1f} | "
        f"Total: {result.total_seconds:.2f}s | "
        f"Tokens: {result.tokens}"
    )


# ─────────────────────────────────────────────
# Real-time progress bar (TTY) + log capture
# ─────────────────────────────────────────────

class LogCapture:
    """File-like object that mirrors writes into a log file only.

    Used as a stand-in for ``sys.stdout`` so that verbose scenario
    output is captured to ``benchmark.log`` without ever touching the
    real terminal. The terminal is reserved for the live progress bar.
    """

    def __init__(self, log_file) -> None:
        self.log_file = log_file

    def write(self, text: str) -> int:
        if self.log_file is not None and text:
            self.log_file.write(text)
        return len(text or "")

    def flush(self) -> None:
        if self.log_file is not None:
            try:
                self.log_file.flush()
            except Exception:
                pass

    def isatty(self) -> bool:  # never claim to be a TTY
        return False


class ProgressBar:
    """Real-time single-line progress bar with TTY detection and log capture.

    Behaviour:
    * In TTY mode, the active step rewrites a single line via ``\\r`` and
      is committed to scrollback (with a newline) when the step finishes.
    * In non-TTY mode, only completed steps are emitted as plain lines.
    * All non-progress output (banners, per-request logs, summaries) is
      redirected via :py:meth:`capture_stdout` to ``log_file`` so the
      terminal stays clean during scenario execution.
    * A daemon ticker thread bumps the in-step fill every couple of
      seconds (4 micro-steps per scenario) so the bar visibly breathes
      while a scenario is running.
    """

    BAR_WIDTH = 30
    _TICK_INTERVAL = 2.0  # seconds between micro-step bumps
    _TICK_STEPS = (0.25, 0.50, 0.75, 0.95)

    def __init__(self, total_steps: int, log_file=None, real_stdout=None) -> None:
        self.total_steps = max(1, int(total_steps))
        self.completed = 0
        self.log_file = log_file
        self._real_stdout = real_stdout if real_stdout is not None else sys.stdout
        self.is_tty = bool(getattr(self._real_stdout, "isatty", lambda: False)())
        self._start_time = time.time()
        self._current_label = ""
        self._step_start = 0.0
        self._sub_progress = 0.0
        self._stop_event: threading.Event | None = None
        self._ticker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._line_dirty = False  # True when a \r-rewriting line is on screen

    # ── stream helpers ────────────────────────────────────────────

    def _write_terminal(self, text: str) -> None:
        try:
            self._real_stdout.write(text)
            self._real_stdout.flush()
        except Exception:
            pass

    def _clear_line(self) -> None:
        """Erase the current in-progress line on TTY terminals."""
        if self.is_tty and self._line_dirty:
            self._write_terminal("\r" + " " * 120 + "\r")
            self._line_dirty = False

    def _timestamp(self) -> str:
        return datetime.now().strftime("[%H:%M:%S]")

    def _bar(self, fraction: float) -> str:
        fraction = max(0.0, min(1.0, fraction))
        filled = int(self.BAR_WIDTH * fraction)
        empty = self.BAR_WIDTH - filled
        return f"|{'█' * filled}{'░' * empty}|"

    def _log(self, message: str) -> None:
        if self.log_file is None:
            return
        try:
            self.log_file.write(message + "\n")
            self.log_file.flush()
        except Exception:
            pass

    # ── public API ────────────────────────────────────────────────

    def update(self, label: str, sub_progress: float = 0.0) -> None:
        """Update the in-progress line (TTY only). Called frequently."""
        with self._lock:
            self._current_label = label
            self._sub_progress = max(0.0, min(1.0, sub_progress))
            if not self.is_tty:
                return
            overall = (self.completed + self._sub_progress) / self.total_steps
            pct = int(overall * 100)
            step_no = min(self.completed + 1, self.total_steps)
            step_display = f"[{step_no:>2}/{self.total_steps}]"
            line = (
                f"\r{self._timestamp()} {self._bar(overall)} "
                f"{pct:>3}% {step_display} {label}..."
            )
            self._write_terminal(line)
            self._line_dirty = True

    def start_step(self, label: str) -> None:
        """Begin a new step and start the background ticker."""
        self._current_label = label
        self._step_start = time.time()
        self._sub_progress = 0.0
        self._log(f"{self._timestamp()} ▶ {label}")
        self.update(label, 0.0)
        if self.is_tty:
            self._stop_event = threading.Event()
            self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
            self._ticker.start()

    def _tick_loop(self) -> None:
        idx = 0
        assert self._stop_event is not None
        while not self._stop_event.wait(self._TICK_INTERVAL):
            if idx < len(self._TICK_STEPS):
                self.update(self._current_label, self._TICK_STEPS[idx])
                idx += 1
            else:
                # keep redrawing at last micro-step so the timestamp
                # stays fresh while the scenario runs long
                self.update(self._current_label, self._TICK_STEPS[-1])

    def _stop_ticker(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._ticker is not None:
            self._ticker.join(timeout=1.0)
        self._stop_event = None
        self._ticker = None

    def end_step(self, success: bool = True, label: str | None = None) -> None:
        """Finish the current step and commit a scrollback line."""
        self._stop_ticker()
        elapsed = time.time() - self._step_start if self._step_start else 0.0
        lbl = label if label is not None else self._current_label
        if success:
            self.complete_step(lbl, elapsed)
        else:
            self.fail_step(lbl, elapsed)

    def complete_step(self, label: str, elapsed: float) -> None:
        """Mark current step as done; commit to scrollback."""
        with self._lock:
            self.completed = min(self.completed + 1, self.total_steps)
            overall = self.completed / self.total_steps
            pct = int(overall * 100)
            step_display = f"[{self.completed:>2}/{self.total_steps}]"
            status = f"— Success ({elapsed:.1f}s)"
            if self.is_tty:
                line = (
                    f"\r{self._timestamp()} {self._bar(overall)} "
                    f"{pct:>3}% {step_display} {label} {status}"
                )
                self._write_terminal(line + "\n")
                self._line_dirty = False
            else:
                self._write_terminal(
                    f"{self._timestamp()} {pct:>3}% {step_display} "
                    f"{label} {status}\n"
                )
            self._log(f"{self._timestamp()} ✓ {step_display} {label} {status}")

    def fail_step(self, label: str, elapsed: float) -> None:
        """Mark current step as failed; commit to scrollback."""
        with self._lock:
            self.completed = min(self.completed + 1, self.total_steps)
            overall = self.completed / self.total_steps
            pct = int(overall * 100)
            step_display = f"[{self.completed:>2}/{self.total_steps}]"
            status = f"— Failed ({elapsed:.1f}s)"
            if self.is_tty:
                line = (
                    f"\r{self._timestamp()} {self._bar(overall)} "
                    f"{pct:>3}% {step_display} {label} {status}"
                )
                self._write_terminal(line + "\n")
                self._line_dirty = False
            else:
                self._write_terminal(
                    f"{self._timestamp()} {pct:>3}% {step_display} "
                    f"{label} {status}\n"
                )
            self._log(f"{self._timestamp()} ✗ {step_display} {label} {status}")

    def info(self, message: str) -> None:
        """Print a one-off scrollback line (e.g. report milestones)."""
        with self._lock:
            self._clear_line()
            self._write_terminal(f"{self._timestamp()} {message}\n")
            self._log(f"{self._timestamp()} {message}")

    def finish(self, suffix: str = "") -> None:
        """Print the final completion line."""
        self._stop_ticker()
        elapsed_total = time.time() - self._start_time
        with self._lock:
            tail = f" {suffix}" if suffix else ""
            if self.is_tty:
                line = (
                    f"\r{self._timestamp()} {self._bar(1.0)} 100% "
                    f"[{self.total_steps:>2}/{self.total_steps}] "
                    f"Complete ✓ (total: {elapsed_total:.1f}s){tail}"
                )
                self._write_terminal(line + "\n")
                self._line_dirty = False
            else:
                self._write_terminal(
                    f"{self._timestamp()} 100% Complete ✓ "
                    f"(total: {elapsed_total:.1f}s){tail}\n"
                )
            self._log(
                f"{self._timestamp()} ✓ Complete (total: {elapsed_total:.1f}s)"
            )

    def log(self, message: str) -> None:
        """Write a verbose-only message to the log file."""
        self._log(message)

    @contextmanager
    def capture_stdout(self):
        """Redirect ``sys.stdout`` to the log file for the block.

        Inside the block, every ``print()`` writes to ``benchmark.log``
        only; nothing reaches the terminal. The progress bar continues
        to render via the saved real stdout reference.
        """
        if self.log_file is None:
            yield
            return
        previous = sys.stdout
        sys.stdout = LogCapture(self.log_file)
        try:
            yield
        finally:
            sys.stdout = previous


def print_scenario_summary(result: ScenarioResult) -> None:
    """Print aggregated statistics for a scenario run."""
    display = _scenario_display_name(result.scenario)
    if display:
        print_header(f"Scenario {result.scenario} — {display}: {result.label}")
    else:
        print_header(f"Scenario {result.scenario}: {result.label}")
    ok = result.successful
    errs = result.failed
    rl = result.rate_limited

    print(
        f"  Total: {len(result.results)} | "
        f"Success: {len(ok)} | "
        f"Errors: {len(errs)} | "
        f"429s: {len(rl)}"
    )

    if not ok:
        print("  No successful requests to report.")
        return

    ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
    tps_vals = [r.tps for r in ok]

    if ttfts:
        print(
            f"  TTFT  → P50: {np.percentile(ttfts, 50):.0f}ms | "
            f"P95: {np.percentile(ttfts, 95):.0f}ms | "
            f"P99: {np.percentile(ttfts, 99):.0f}ms"
        )
    if tps_vals:
        print(
            f"  TPS   → Avg: {np.mean(tps_vals):.1f} | "
            f"Min: {np.min(tps_vals):.1f} | "
            f"Max: {np.max(tps_vals):.1f}"
        )

    total_tokens = sum(r.tokens for r in ok)
    # NOTE: For multi-batch scenarios (e.g. Scenario B's aggregated
    # ScenarioResult across multiple concurrency levels), max_time is the
    # slowest single-request duration and `total_tokens / max_time` does
    # NOT represent the true aggregate TPM. Per-batch TPM is printed
    # inside each scenario; this line is an order-of-magnitude estimate.
    max_time = max((r.total_seconds for r in ok), default=0.0)
    if max_time >= 1e-3:
        print(f"  Est. TPM: {total_tokens / max_time * 60:,.0f}")


# ─────────────────────────────────────────────
# Comparison table (Token API vs PTU)
# ─────────────────────────────────────────────

def print_comparison_table(
    token_api: ScenarioResult,
    ptu: ScenarioResult,
) -> None:
    """Print a side-by-side comparison table."""
    print_header("Token API vs PTU Comparison")

    def _stats(sr: ScenarioResult) -> dict[str, Any]:
        ok = sr.successful
        if not ok:
            return {"ttft_p50": "—", "ttft_p99": "—", "tps_avg": "—", "max_concurrent": 0}
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        tps_vals = [r.tps for r in ok]
        max_time = max((r.total_seconds for r in ok), default=0.0)
        return {
            "ttft_p50": f"{np.percentile(ttfts, 50):.0f}" if ttfts else "—",
            "ttft_p99": f"{np.percentile(ttfts, 99):.0f}" if ttfts else "—",
            "tps_avg": f"{np.mean(tps_vals):.1f}" if tps_vals else "—",
            "max_concurrent": len(ok),
            "sustained_tpm": (
                sum(r.tokens for r in ok) / max_time * 60
                if max_time >= 1e-3 else 0.0
            ),
        }

    a, b = _stats(token_api), _stats(ptu)

    rows = [
        ["TTFT (P50)", f"{a['ttft_p50']} ms", f"{b['ttft_p50']} ms", ""],
        ["TTFT (P99)", f"{a['ttft_p99']} ms", f"{b['ttft_p99']} ms", ""],
        ["TPS (avg)", f"{a['tps_avg']}", f"{b['tps_avg']}", ""],
        ["Max Concurrent (no 429)", str(a["max_concurrent"]), str(b["max_concurrent"]), ""],
    ]
    print(tabulate(rows, headers=["Metric", "Token API", "PTU", "Improvement"], tablefmt="grid"))


# ─────────────────────────────────────────────
# Project A/B comparison (--compare-with)
# ─────────────────────────────────────────────

def print_project_comparison(
    name_a: str,
    results_a: Sequence[ScenarioResult],
    name_b: str,
    results_b: Sequence[ScenarioResult],
) -> None:
    """
    Print a side-by-side A/B comparison table for two project runs.

    Δ column shows the relative change of *B vs A*; '+' means B is better
    (lower latency / higher throughput).
    """
    print_header(f"A/B Comparison: {name_a}  vs  {name_b}")

    # Index by scenario key so we align rows even if order differs
    by_key_a = {r.scenario: r for r in results_a}
    by_key_b = {r.scenario: r for r in results_b}
    keys = [k for k in by_key_a if k in by_key_b]

    if not keys:
        print("  No overlapping scenarios to compare.")
        return

    rows: list[list[str]] = []
    for key in keys:
        sr_a, sr_b = by_key_a[key], by_key_b[key]
        ma, mb = _scenario_metrics(sr_a), _scenario_metrics(sr_b)

        def _fmt(v: float | None, suffix: str = "") -> str:
            return "—" if v is None else f"{v:.0f}{suffix}" if suffix in ("ms", "") and suffix == "ms" \
                else (f"{v:.1f}{suffix}" if v < 1000 else f"{v:,.0f}{suffix}")

        rows.append([
            f"{key} • TTFT P50",
            "—" if ma["ttft_p50"] is None else f"{ma['ttft_p50']:.0f} ms",
            "—" if mb["ttft_p50"] is None else f"{mb['ttft_p50']:.0f} ms",
            _delta(ma["ttft_p50"], mb["ttft_p50"], lower_is_better=True),
        ])
        rows.append([
            f"{key} • TTFT P99",
            "—" if ma["ttft_p99"] is None else f"{ma['ttft_p99']:.0f} ms",
            "—" if mb["ttft_p99"] is None else f"{mb['ttft_p99']:.0f} ms",
            _delta(ma["ttft_p99"], mb["ttft_p99"], lower_is_better=True),
        ])
        rows.append([
            f"{key} • TPS (avg)",
            "—" if ma["tps_avg"] is None else f"{ma['tps_avg']:.1f}",
            "—" if mb["tps_avg"] is None else f"{mb['tps_avg']:.1f}",
            _delta(ma["tps_avg"], mb["tps_avg"], lower_is_better=False),
        ])
        rows.append([
            f"{key} • Est. TPM",
            "—" if ma["tpm"] is None else f"{ma['tpm']:,.0f}",
            "—" if mb["tpm"] is None else f"{mb['tpm']:,.0f}",
            _delta(ma["tpm"], mb["tpm"], lower_is_better=False),
        ])
        rows.append([
            f"{key} • 429s / errors",
            f"{ma['rate_limited']} / {ma['errors']}",
            f"{mb['rate_limited']} / {mb['errors']}",
            "",
        ])
        rows.append(["", "", "", ""])  # separator

    headers = ["Metric", name_a, name_b, "Δ (B vs A)"]
    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print("\n  Δ legend: '+' means the right column wins "
          "(lower latency / higher throughput).")
