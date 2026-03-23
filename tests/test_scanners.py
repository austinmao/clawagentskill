"""Unit tests for all 4 security scanners."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawagentskill.scan.prefilter import scan_prefilter
from clawagentskill.scan.permission import scan_permission
from clawagentskill.scan.config import scan_config
from clawagentskill.scan.injection import scan_injection
from clawagentskill.scan.runner import run_scanners


FIXTURES = Path(__file__).parent / "fixtures"


class TestPrefilter:
    def test_blocks_clawhavoc_c2_ip(self):
        result = scan_prefilter(FIXTURES / "clawhavoc-skill.md")
        assert result["status"] == "blocked"
        codes = [f["code"] for f in result["findings"]]
        assert "clawhavoc-indicator" in codes

    def test_clean_passes(self):
        result = scan_prefilter(FIXTURES / "clean-skill.md")
        assert result["status"] == "clean"
        assert len(result["findings"]) == 0

    def test_returns_scanner_name(self):
        result = scan_prefilter(FIXTURES / "clean-skill.md")
        assert result["scanner"] == "prefilter"

    def test_includes_scanned_at(self):
        result = scan_prefilter(FIXTURES / "clean-skill.md")
        assert "scanned_at" in result


class TestPermission:
    def test_detects_exfil_risk(self):
        result = scan_permission(FIXTURES / "overpermissioned-skill.md")
        assert result["status"] == "warn"
        codes = [f["code"] for f in result["findings"]]
        assert "exfil-risk" in codes

    def test_clean_passes(self):
        result = scan_permission(FIXTURES / "clean-skill.md")
        assert result["status"] == "clean"

    def test_returns_scanner_name(self):
        result = scan_permission(FIXTURES / "clean-skill.md")
        assert "permission" in result["scanner"]


class TestConfig:
    def test_clean_passes(self):
        result = scan_config(FIXTURES / "clean-skill.md")
        assert result["status"] == "clean"

    def test_returns_scanner_name(self):
        result = scan_config(FIXTURES / "clean-skill.md")
        assert "config" in result["scanner"]

    def test_detects_undeclared_env_var(self, tmp_path):
        """Config scanner should detect env vars not declared in requires.env."""
        skill = tmp_path / "test.md"
        skill.write_text(
            "---\nname: test\ndescription: test\nversion: 1.0.0\n"
            "permissions:\n  filesystem: none\n  network: false\n"
            "metadata:\n  openclaw:\n    requires:\n      env: []\n"
            "---\n\n# Test\n\nConnect using ${UNDECLARED_API_KEY} for auth.\n"
        )
        result = scan_config(skill)
        assert result["status"] == "warn"
        codes = [f["code"] for f in result["findings"]]
        assert "undeclared-env" in codes

    def test_detects_clawhub_origin(self, tmp_path):
        """Config scanner should detect .clawhub/origin.json references."""
        skill = tmp_path / "test.md"
        skill.write_text(
            "---\nname: test\ndescription: test\nversion: 1.0.0\n"
            "permissions:\n  filesystem: none\n  network: false\n"
            "---\n\n# Test\n\nCheck .clawhub/origin.json for source.\n"
        )
        result = scan_config(skill)
        assert result["status"] in ("warn", "blocked")

    def test_detects_clawhub_cli(self, tmp_path):
        """Config scanner should detect clawdhub CLI references."""
        skill = tmp_path / "test.md"
        skill.write_text(
            "---\nname: test\ndescription: test\nversion: 1.0.0\n"
            "permissions:\n  filesystem: none\n  network: false\n"
            "---\n\n# Test\n\nRun clawdhub install my-skill to set up.\n"
        )
        result = scan_config(skill)
        assert result["status"] == "blocked"


class TestInjection:
    def test_clean_passes(self):
        result = scan_injection(FIXTURES / "clean-skill.md")
        assert result["status"] == "clean"

    def test_detects_clawhavoc_patterns(self):
        result = scan_injection(FIXTURES / "clawhavoc-skill.md")
        assert result["status"] == "blocked"
        codes = [f["code"] for f in result["findings"]]
        assert "clawhavoc-indicator" in codes

    def test_returns_scanner_name(self):
        result = scan_injection(FIXTURES / "clean-skill.md")
        assert "injection" in result["scanner"]


class TestRunner:
    async def test_runs_all_4_scanners(self):
        results = await run_scanners(FIXTURES / "clean-skill.md")
        assert "prefilter" in results
        assert "permission" in results
        assert "config" in results
        assert "injection" in results

    async def test_all_clean_for_clean_fixture(self):
        results = await run_scanners(FIXTURES / "clean-skill.md")
        for scanner_name, result in results.items():
            assert result["status"] == "clean", f"{scanner_name} should be clean"

    async def test_prefilter_blocks_clawhavoc(self):
        results = await run_scanners(FIXTURES / "clawhavoc-skill.md")
        assert results["prefilter"]["status"] == "blocked"

    async def test_respects_enabled_filter(self):
        results = await run_scanners(
            FIXTURES / "clean-skill.md",
            enabled=("prefilter",),
        )
        assert "prefilter" in results
        assert "permission" not in results
