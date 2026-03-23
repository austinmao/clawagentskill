"""Unit tests for the config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawagentskill.config import TIER_A_PUBLISHERS, Config, load_config


class TestDefaultConfig:
    def test_default_config_values(self, tmp_path: Path):
        """load_config with no yaml file returns sensible defaults."""
        cfg = load_config(workspace_root=tmp_path)

        assert cfg.tier_b_installs == 10_000
        assert cfg.caution_installs == 1_000
        assert cfg.scrutiny_installs == 100
        assert cfg.run_dir == "memory/skill-adopt-runs"
        assert cfg.scanners == ("prefilter", "permission", "config", "injection")
        assert cfg.workspace_root == tmp_path

    def test_missing_yaml_uses_defaults(self, tmp_path: Path):
        """Non-existent yaml path returns defaults identical to Config()."""
        cfg = load_config(workspace_root=tmp_path / "does-not-exist")
        default = Config()

        assert cfg.trusted_publishers == default.trusted_publishers
        assert cfg.tier_b_installs == default.tier_b_installs
        assert cfg.caution_installs == default.caution_installs
        assert cfg.scrutiny_installs == default.scrutiny_installs
        assert cfg.scanners == default.scanners
        assert cfg.run_dir == default.run_dir


class TestPublisherMerging:
    def test_tier_a_publishers_always_included(self, tmp_path: Path):
        """Even with custom config, openclaw/anthropic are always present."""
        config_yaml = tmp_path / "clawagentskill.yaml"
        config_yaml.write_text(
            "trusted_publishers:\n  - custom-pub\n",
            encoding="utf-8",
        )
        cfg = load_config(workspace_root=tmp_path)

        for pub in TIER_A_PUBLISHERS:
            assert pub in cfg.trusted_publishers

    def test_custom_publishers_merged(self, tmp_path: Path):
        """Custom publishers from yaml are appended to hardcoded list."""
        config_yaml = tmp_path / "clawagentskill.yaml"
        config_yaml.write_text(
            "trusted_publishers:\n  - acme-corp\n  - example-io\n",
            encoding="utf-8",
        )
        cfg = load_config(workspace_root=tmp_path)

        # Hardcoded publishers first
        for pub in TIER_A_PUBLISHERS:
            assert pub in cfg.trusted_publishers

        # Custom publishers appended
        assert "acme-corp" in cfg.trusted_publishers
        assert "example-io" in cfg.trusted_publishers

        # Order: hardcoded first, custom after
        idx_openclaw = cfg.trusted_publishers.index("openclaw")
        idx_acme = cfg.trusted_publishers.index("acme-corp")
        assert idx_openclaw < idx_acme

    def test_duplicate_publishers_not_repeated(self, tmp_path: Path):
        """If yaml lists a hardcoded publisher, it is not duplicated."""
        config_yaml = tmp_path / "clawagentskill.yaml"
        config_yaml.write_text(
            "trusted_publishers:\n  - openclaw\n  - custom-pub\n",
            encoding="utf-8",
        )
        cfg = load_config(workspace_root=tmp_path)

        count = cfg.trusted_publishers.count("openclaw")
        assert count == 1


class TestThresholds:
    def test_thresholds_from_yaml(self, tmp_path: Path):
        """Custom thresholds override defaults."""
        config_yaml = tmp_path / "clawagentskill.yaml"
        config_yaml.write_text(
            "thresholds:\n"
            "  tier_b_installs: 20000\n"
            "  caution_installs: 5000\n"
            "  scrutiny_installs: 50\n",
            encoding="utf-8",
        )
        cfg = load_config(workspace_root=tmp_path)

        assert cfg.tier_b_installs == 20_000
        assert cfg.caution_installs == 5_000
        assert cfg.scrutiny_installs == 50

    def test_partial_thresholds_use_defaults_for_rest(self, tmp_path: Path):
        """Only overridden thresholds change; others keep defaults."""
        config_yaml = tmp_path / "clawagentskill.yaml"
        config_yaml.write_text(
            "thresholds:\n  tier_b_installs: 25000\n",
            encoding="utf-8",
        )
        cfg = load_config(workspace_root=tmp_path)

        assert cfg.tier_b_installs == 25_000
        assert cfg.caution_installs == 1_000  # default
        assert cfg.scrutiny_installs == 100  # default
