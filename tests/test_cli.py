"""Tests for the CLI interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_DIR = Path(__file__).parent.parent


class TestCLI:
    def test_help_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "--help"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 0
        assert "find" in result.stdout
        assert "adopt" in result.stdout
        assert "port" in result.stdout
        assert "scan" in result.stdout
        assert "status" in result.stdout

    def test_version_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "--version"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_find_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "find", "--help"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 0
        assert "query" in result.stdout

    def test_scan_missing_file(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "scan", "/nonexistent/path.md"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()
