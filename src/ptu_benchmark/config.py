"""
Configuration management for PTU Benchmark.

Supports two configuration sources:

1.  **Environment / .env**  — traditional flat env-vars
2.  **Project YAML**         — per-use-case project folder with ``project.yaml``

When ``--project`` is passed on the CLI, the project YAML is loaded first,
then merged with environment variables (env vars take precedence).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# ─────────────────────────────────────────────
# Project Configuration (per use case)
# ─────────────────────────────────────────────

@dataclass
class ProjectConfig:
    """
    Per-deployment / per-use-case project metadata.

    This is loaded from ``project.yaml`` inside a project folder.
    """

    # ── Service identity ────────────────────────────────────────────
    service_name: str = ""
    model_name: str = ""
    model_code: str = ""
    deployment_id: str = ""

    # ── Billing ─────────────────────────────────────────────────────
    billing_method: str = "Provisioned Throughput Unit / Pay-as-you-go"

    # ── Throughput quota ────────────────────────────────────────────
    input_tpm: int = 0
    output_tpm: int = 0

    # ── Pricing (USD) ───────────────────────────────────────────────
    input_unit_price: float = 0.0    # $/kTPM·hour
    output_unit_price: float = 0.0   # $/kTPM·hour
    hourly_price: float = 0.0        # total USD/hour

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProjectConfig:
        """
        Load project configuration from a YAML file.

        Parameters
        ----------
        path:
            Path to ``project.yaml`` inside a project directory.

        Raises
        ------
        ImportError
            If PyYAML is not installed (``pip install pyyaml``).
        FileNotFoundError
            If the YAML file does not exist.
        """
        if yaml is None:
            raise ImportError(
                "PyYAML is required to read project.yaml files. "
                "Install it with: pip install pyyaml"
            )

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Project config not found: {path}")

        raw = yaml.safe_load(path.read_text()) or {}

        return cls(
            service_name=str(raw.get("service_name", "")),
            model_name=str(raw.get("model_name", "")),
            model_code=str(raw.get("model_code", "")),
            deployment_id=str(raw.get("deployment_id", "")),
            billing_method=str(raw.get("billing_method", "")),
            input_tpm=int(raw.get("input_tpm", 0)),
            output_tpm=int(raw.get("output_tpm", 0)),
            input_unit_price=float(raw.get("input_unit_price", 0.0)),
            output_unit_price=float(raw.get("output_unit_price", 0.0)),
            hourly_price=float(raw.get("hourly_price", 0.0)),
        )


# ─────────────────────────────────────────────
# Benchmark Configuration
# ─────────────────────────────────────────────

@dataclass
class BenchmarkConfig:
    """Central configuration for all benchmark scenarios."""

    # ── Connection ──────────────────────────────────────────────────
    api_key: str = ""
    model_id: str = ""
    base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    # ── Project (optional) ──────────────────────────────────────────
    project: ProjectConfig | None = None
    project_dir: Path | None = None

    # ── Scenario B ──────────────────────────────────────────────────
    concurrency_levels: list[int] = field(default_factory=lambda: [10, 50, 100])

    # ── Scenario C ──────────────────────────────────────────────────
    sustained_duration: int = 1800      # seconds
    sustained_concurrency: int = 20

    # ── Scenario D ──────────────────────────────────────────────────
    burst_size: int = 200

    # ── Scenario E ──────────────────────────────────────────────────
    context_sizes: dict[str, int] = field(default_factory=lambda: {
        "32K": 32_000,
        "64K": 64_000,
        "128K": 128_000,
    })

    # ── Shared defaults ─────────────────────────────────────────────
    default_max_tokens: int = 2048
    concurrent_max_tokens: int = 512
    sustained_max_tokens: int = 1024

    # ─────────────────────────────────────────────────────────────────
    # Factory methods
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> BenchmarkConfig:
        """
        Build configuration from environment / .env file only.

        Parameters
        ----------
        env_path:
            Explicit path to a .env file.  When *None*, auto-detected.
        """
        load_dotenv(env_path)
        return cls(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            model_id=os.getenv("PTU_MODEL_ID", ""),
            base_url=os.getenv(
                "BASE_URL",
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            ),
            concurrency_levels=_int_list(
                os.getenv("CONCURRENCY_LEVELS", ""), [10, 50, 100]
            ),
            sustained_duration=int(os.getenv("SUSTAINED_DURATION", "1800")),
            sustained_concurrency=int(os.getenv("SUSTAINED_CONCURRENCY", "20")),
            burst_size=int(os.getenv("BURST_SIZE", "200")),
            context_sizes=_context_sizes(
                os.getenv("CONTEXT_SIZES", ""),
                {"32K": 32_000, "64K": 64_000, "128K": 128_000},
            ),
        )

    @classmethod
    def from_project(cls, project_dir: str | Path) -> BenchmarkConfig:
        """
        Build configuration from a project directory.

        Loads ``project.yaml`` for model/TPM/pricing metadata.
        Loads ``.env`` from the project folder for API credentials.
        Falls back to the repository root ``.env`` if the project
        folder does not contain one (with a printed warning).

        Parameters
        ----------
        project_dir:
            Path to the project folder (must contain ``project.yaml``).
        """
        project_dir = Path(project_dir).resolve()

        # ── Load project YAML ───────────────────────────────────────
        yaml_path = project_dir / "project.yaml"
        project = ProjectConfig.from_yaml(yaml_path)

        # ── Load .env: project folder first, fall back to root ──────
        project_env = project_dir / ".env"
        if project_env.exists():
            load_dotenv(project_env, override=True)
        else:
            # Fall back to repository root .env (walk up to find it)
            root_env = _find_root_env(project_dir)
            if root_env is not None:
                print(
                    f"  Note: no .env in {project_dir}, "
                    f"falling back to root {root_env}"
                )
                load_dotenv(root_env, override=True)

        # ── Build config ─────────────────────────────────────────────
        config = cls(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            model_id=project.model_code or os.getenv("PTU_MODEL_ID", ""),
            base_url=os.getenv(
                "BASE_URL",
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            ),
            project=project,
            project_dir=project_dir,
            concurrency_levels=_int_list(
                os.getenv("CONCURRENCY_LEVELS", ""), [10, 50, 100]
            ),
            sustained_duration=int(os.getenv("SUSTAINED_DURATION", "1800")),
            sustained_concurrency=int(os.getenv("SUSTAINED_CONCURRENCY", "20")),
            burst_size=int(os.getenv("BURST_SIZE", "200")),
            context_sizes=_context_sizes(
                os.getenv("CONTEXT_SIZES", ""),
                {"32K": 32_000, "64K": 64_000, "128K": 128_000},
            ),
        )

        # ── Apply YAML benchmark overrides (if any) ──────────────────
        _apply_yaml_overrides(yaml_path, config)

        return config

    # ─────────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return a list of missing required fields (empty = valid)."""
        errors: list[str] = []
        if not self.api_key:
            errors.append("DASHSCOPE_API_KEY is not set")
        if not self.model_id:
            errors.append("PTU_MODEL_ID is not set (or project.yaml missing model_code)")
        return errors


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _find_root_env(start: Path) -> Path | None:
    """
    Walk up from *start* looking for the first ancestor that contains
    a ``.env`` file **and** is not the project folder itself.

    Returns the path to that ``.env``, or *None* if not found.
    """
    for ancestor in start.parents:
        candidate = ancestor / ".env"
        if candidate.exists():
            return candidate
    return None


def _int_list(raw: str, default: list[int]) -> list[int]:
    """Parse a comma-separated string of integers."""
    raw = raw.strip()
    if not raw:
        return default
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _context_sizes(raw: str, default: dict[str, int]) -> dict[str, int]:
    """Parse comma-separated token counts into a label→count dict."""
    raw = raw.strip()
    if not raw:
        return default
    sizes: dict[str, int] = {}
    for token_str in raw.split(","):
        token_str = token_str.strip()
        if not token_str:
            continue
        count = int(token_str)
        label = f"{count // 1000}K" if count >= 1000 else str(count)
        sizes[label] = count
    return sizes or default


def _apply_yaml_overrides(yaml_path: Path, config: BenchmarkConfig) -> None:
    """Apply optional benchmark overrides from project.yaml."""
    if yaml is None:
        return
    try:
        raw = yaml.safe_load(yaml_path.read_text()) or {}
    except Exception:
        return

    # Concurrency levels
    levels = raw.get("concurrency_levels")
    if isinstance(levels, list) and all(isinstance(x, int) for x in levels):
        config.concurrency_levels = levels

    # Sustained throughput
    dur = raw.get("sustained_duration")
    if isinstance(dur, int) and dur > 0:
        config.sustained_duration = dur
    sc = raw.get("sustained_concurrency")
    if isinstance(sc, int) and sc > 0:
        config.sustained_concurrency = sc

    # Burst
    burst = raw.get("burst_size")
    if isinstance(burst, int) and burst > 0:
        config.burst_size = burst

    # Context sizes
    cs = raw.get("context_sizes")
    if isinstance(cs, dict):
        config.context_sizes = {
            str(k): int(v) for k, v in cs.items() if isinstance(v, int)
        }
