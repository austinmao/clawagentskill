"""Unit tests for all 4 security scanners."""

from __future__ import annotations

import asyncio
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


class TestInjection:
    def test_clean_passes(self):
        result = scan_injection(FIXTURES / "clean-skill.md")
        assert result["status"] == "clean"

    def test_detects_clawhavoc_patterns(self):
        result = scan_injection(FIXTURES / "clawhavoc-skill.md")
        # ClawHavoc patterns should be detected
        assert result["status"] in ("warn", "blocked")

    def test_returns_scanner_name(self):
        result = scan_injection(FIXTURES / "clean-skill.md")
        assert "injection" in result["scanner"]


class TestRunner:
    def test_runs_all_4_scanners(self):
        results = asyncio.run(run_scanners(FIXTURES / "clean-skill.md"))
        assert "prefilter" in results
        assert "permission" in results
        assert "config" in results
        assert "injection" in results

    def test_all_clean_for_clean_fixture(self):
        results = asyncio.run(run_scanners(FIXTURES / "clean-skill.md"))
        for scanner_name, result in results.items():
            assert result["status"] == "clean", f"{scanner_name} should be clean"

    def test_prefilter_blocks_clawhavoc(self):
        results = asyncio.run(run_scanners(FIXTURES / "clawhavoc-skill.md"))
        assert results["prefilter"]["status"] == "blocked"

    def test_respects_enabled_filter(self):
        results = asyncio.run(run_scanners(
            FIXTURES / "clean-skill.md",
            enabled=("prefilter",),
        ))
        assert "prefilter" in results
        assert "permission" not in results
