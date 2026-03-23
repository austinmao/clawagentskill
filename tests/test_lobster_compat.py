"""Tests for Lobster workflow compatibility.

Verifies that clawagentskill CLI subcommands produce valid JSON envelopes
compatible with Lobster stdin-chaining.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_DIR = Path(__file__).parent.parent


class TestLobsterEnvelope:
    """Lobster stages communicate via JSON envelope on stdout: {"run_dir": "<path>"}."""

    def test_state_init_emits_envelope(self, tmp_path: Path):
        """state-init should emit a JSON envelope with run_dir."""
        result = subprocess.run(
            [
                sys.executable, "-m", "clawagentskill",
                "state-init",
                "--query", "test-skill",
                "--run-dir-base", str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        envelope = json.loads(result.stdout.strip())
        assert "run_dir" in envelope
        assert Path(envelope["run_dir"]).exists()

    def test_state_init_creates_meta_yaml(self, tmp_path: Path):
        """state-init should create meta.yaml in the run directory."""
        result = subprocess.run(
            [
                sys.executable, "-m", "clawagentskill",
                "state-init",
                "--query", "test-skill",
                "--run-dir-base", str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        envelope = json.loads(result.stdout.strip())
        meta_path = Path(envelope["run_dir"]) / "meta.yaml"
        assert meta_path.exists()

    def test_get_field_reads_meta(self, tmp_path: Path):
        """get-field should read a field from meta.yaml."""
        # First create a run
        result = subprocess.run(
            [
                sys.executable, "-m", "clawagentskill",
                "state-init",
                "--query", "test-skill",
                "--run-dir-base", str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        envelope = json.loads(result.stdout.strip())
        run_dir = envelope["run_dir"]

        # Then read a field
        result = subprocess.run(
            [
                sys.executable, "-m", "clawagentskill",
                "get-field",
                "--run-dir", run_dir,
                "--key", "query",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "test-skill"


class TestLobsterSubcommands:
    """Verify all Lobster-compatible subcommands are registered."""

    REQUIRED_SUBCOMMANDS = [
        "state-init",
        "validate-prereqs",
        "get-field",
        "find",
        "adopt",
        "port",
        "scan",
        "status",
    ]

    def test_all_subcommands_in_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "--help"],
            capture_output=True,
            text=True,
        )
        for cmd in self.REQUIRED_SUBCOMMANDS:
            assert cmd in result.stdout, f"Missing subcommand: {cmd}"
