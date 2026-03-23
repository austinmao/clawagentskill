"""Tests for scan/snyk.py — Snyk scanner with prerequisite checks."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from clawagentskill.scan.snyk import scan_snyk


FIXTURES = Path(__file__).parent / "fixtures"


class TestSnykPrerequisites:
    def test_skipped_when_no_uvx(self):
        with patch("clawagentskill.scan.snyk.shutil.which", return_value=None):
            result = scan_snyk(FIXTURES / "clean-skill.md")

        assert result["status"] == "skipped"
        assert result["skip_reason"] == "uvx binary not found on PATH"
        assert result["findings"] == []

    def test_skipped_when_no_snyk_token(self):
        with (
            patch("clawagentskill.scan.snyk.shutil.which", return_value="/usr/bin/uvx"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = scan_snyk(FIXTURES / "clean-skill.md")

        assert result["status"] == "skipped"
        assert result["skip_reason"] == "SNYK_TOKEN environment variable not set"

    def test_returns_scanner_name(self):
        with patch("clawagentskill.scan.snyk.shutil.which", return_value=None):
            result = scan_snyk(FIXTURES / "clean-skill.md")

        assert result["scanner"] == "snyk"


class TestSnykErrors:
    def test_error_on_timeout(self):
        with (
            patch("clawagentskill.scan.snyk.shutil.which", return_value="/usr/bin/uvx"),
            patch.dict("os.environ", {"SNYK_TOKEN": "test-token"}),
            patch(
                "clawagentskill.scan.snyk.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="uvx", timeout=120),
            ),
        ):
            result = scan_snyk(FIXTURES / "clean-skill.md")

        assert result["status"] == "error"
        assert result["scanner"] == "snyk"
        assert any("timed out" in f["message"].lower() for f in result["findings"])

    def test_error_on_nonzero_exit(self):
        mock_result = subprocess.CompletedProcess(
            args=["uvx", "snyk-agent-scan@latest"],
            returncode=1,
            stdout="",
            stderr="scan failed: invalid token",
        )
        with (
            patch("clawagentskill.scan.snyk.shutil.which", return_value="/usr/bin/uvx"),
            patch.dict("os.environ", {"SNYK_TOKEN": "test-token"}),
            patch("clawagentskill.scan.snyk.subprocess.run", return_value=mock_result),
        ):
            result = scan_snyk(FIXTURES / "clean-skill.md")

        assert result["status"] == "error"
        assert result["scanner"] == "snyk"
        assert any("exited with code 1" in f["message"] for f in result["findings"])
