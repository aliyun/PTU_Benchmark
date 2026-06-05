"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path

import pytest
from ptu_benchmark.config import BenchmarkConfig, ProjectConfig


# ── BenchmarkConfig (flat mode) ──────────────────────────────

class TestBenchmarkConfig:
    def test_default_values(self):
        cfg = BenchmarkConfig()
        assert cfg.base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        assert cfg.concurrency_levels == [10, 50, 100]
        assert cfg.sustained_duration == 1800
        assert cfg.burst_size == 200

    def test_validate_missing_api_key(self):
        cfg = BenchmarkConfig(api_key="", model_id="some-model")
        errors = cfg.validate()
        assert any("DASHSCOPE_API_KEY" in e for e in errors)

    def test_validate_missing_model_id(self):
        cfg = BenchmarkConfig(api_key="sk-test", model_id="")
        errors = cfg.validate()
        assert any("PTU_MODEL_ID" in e for e in errors)

    def test_validate_success(self):
        cfg = BenchmarkConfig(api_key="sk-test", model_id="some-model")
        errors = cfg.validate()
        assert errors == []

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-key")
        monkeypatch.setenv("PTU_MODEL_ID", "qwen-test-model")
        monkeypatch.setenv("CONCURRENCY_LEVELS", "5,20,50")
        monkeypatch.setenv("BURST_SIZE", "300")

        cfg = BenchmarkConfig.from_env()
        assert cfg.api_key == "sk-test-key"
        assert cfg.model_id == "qwen-test-model"
        assert cfg.concurrency_levels == [5, 20, 50]
        assert cfg.burst_size == 300


# ── ProjectConfig (YAML loading) ─────────────────────────────

class TestProjectConfig:
    def test_from_yaml_minimal(self, tmp_path: Path):
        yaml_path = tmp_path / "project.yaml"
        yaml_path.write_text(
            "service_name: 'demo'\n"
            "model_code: 'qwen-test'\n"
            "input_tpm: 50000\n"
            "output_tpm: 5000\n"
        )
        p = ProjectConfig.from_yaml(yaml_path)
        assert p.service_name == "demo"
        assert p.model_code == "qwen-test"
        assert p.input_tpm == 50000
        assert p.output_tpm == 5000
        assert p.deployment_id == ""

    def test_from_yaml_full(self, tmp_path: Path):
        yaml_path = tmp_path / "project.yaml"
        yaml_path.write_text(
            "service_name: 'test'\n"
            "model_name: 'Qwen3.6-Plus-2026-04-02'\n"
            "model_code: 'qwen3.6-plus-2026-04-02'\n"
            "deployment_id: 'qwen3.6-plus-2026-04-02-d1839645ee95'\n"
            "billing_method: 'Provisioned Throughput Unit / Pay-as-you-go'\n"
            "input_tpm: 100000\n"
            "output_tpm: 10000\n"
            "input_unit_price: 0.12\n"
            "output_unit_price: 0.72\n"
            "hourly_price: 19.2\n"
        )
        p = ProjectConfig.from_yaml(yaml_path)
        assert p.service_name == "test"
        assert p.model_name == "Qwen3.6-Plus-2026-04-02"
        assert p.deployment_id == "qwen3.6-plus-2026-04-02-d1839645ee95"
        assert p.input_tpm == 100000
        assert p.output_tpm == 10000
        assert p.input_unit_price == 0.12
        assert p.output_unit_price == 0.72
        assert p.hourly_price == 19.2

    def test_from_yaml_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            ProjectConfig.from_yaml(tmp_path / "does_not_exist.yaml")

    def test_from_yaml_empty(self, tmp_path: Path):
        yaml_path = tmp_path / "project.yaml"
        yaml_path.write_text("")
        p = ProjectConfig.from_yaml(yaml_path)
        # All defaults
        assert p.service_name == ""
        assert p.input_tpm == 0


# ── BenchmarkConfig.from_project ─────────────────────────────

class TestFromProject:
    def test_loads_project_yaml(self, tmp_path: Path, monkeypatch):
        """from_project reads project.yaml and sets model_id from model_code."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")

        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(
            "service_name: 'acme-corp'\n"
            "model_code: 'qwen3.6-plus'\n"
            "input_tpm: 200000\n"
            "output_tpm: 20000\n"
            "hourly_price: 38.4\n"
        )

        cfg = BenchmarkConfig.from_project(project_dir)
        assert cfg.api_key == "sk-test"
        assert cfg.model_id == "qwen3.6-plus"
        assert cfg.project is not None
        assert cfg.project.service_name == "acme-corp"
        assert cfg.project.input_tpm == 200000
        assert cfg.project.hourly_price == 38.4
        assert cfg.project_dir == project_dir.resolve()

    def test_project_env_used_when_root_unset(self, tmp_path: Path):
        """Project .env is used when no root env var is set."""
        # Do NOT set root env — simulate no .env at root

        project_dir = tmp_path / "acme"
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text("model_code: 'm1'\n")
        (project_dir / ".env").write_text("DASHSCOPE_API_KEY=project-key\n")

        cfg = BenchmarkConfig.from_project(project_dir)
        assert cfg.api_key == "project-key"
        assert cfg.model_id == "m1"

    def test_applies_yaml_benchmark_overrides(self, tmp_path: Path, monkeypatch):
        """Benchmark overrides in project.yaml are applied."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")

        project_dir = tmp_path / "bursty"
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(
            "model_code: 'ql'\n"
            "concurrency_levels: [5, 25]\n"
            "sustained_duration: 300\n"
            "sustained_concurrency: 8\n"
            "burst_size: 500\n"
            "context_sizes:\n"
            "  '16K': 16000\n"
        )

        cfg = BenchmarkConfig.from_project(project_dir)
        assert cfg.concurrency_levels == [5, 25]
        assert cfg.sustained_duration == 300
        assert cfg.sustained_concurrency == 8
        assert cfg.burst_size == 500
        assert cfg.context_sizes == {"16K": 16000}

    def test_model_id_falls_back_to_env(self, tmp_path: Path, monkeypatch):
        """When project.yaml has no model_code, fall back to env."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
        monkeypatch.setenv("PTU_MODEL_ID", "fallback-model")

        project_dir = tmp_path / "no-model"
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text("service_name: 'foo'\n")

        cfg = BenchmarkConfig.from_project(project_dir)
        assert cfg.model_id == "fallback-model"
