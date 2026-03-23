"""Tests for adopt/rebuild.py — OpenProse rebuild wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from clawagentskill.adopt.rebuild import rebuild


class TestRebuild:
    def test_success_returns_true(self, tmp_path: Path):
        staging = tmp_path / "SKILL.md"
        staging.write_text("---\nname: test\n---\nBody", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        mock_result = subprocess.CompletedProcess(
            args=["python", "-m", "compiler.engine.cli", "skill", "rebuild"],
            returncode=0,
            stdout="Rebuild complete",
            stderr="",
        )
        with patch("clawagentskill.adopt.rebuild.subprocess.run", return_value=mock_result):
            assert rebuild(staging, run_dir) is True

    def test_failure_returns_false(self, tmp_path: Path):
        staging = tmp_path / "SKILL.md"
        staging.write_text("---\nname: test\n---\nBody", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        mock_result = subprocess.CompletedProcess(
            args=["python", "-m", "compiler.engine.cli", "skill", "rebuild"],
            returncode=1,
            stdout="",
            stderr="rebuild error: invalid skill structure",
        )
        with patch("clawagentskill.adopt.rebuild.subprocess.run", return_value=mock_result):
            assert rebuild(staging, run_dir) is False

    def test_compiler_not_found_returns_true(self, tmp_path: Path):
        staging = tmp_path / "SKILL.md"
        staging.write_text("---\nname: test\n---\nBody", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        with patch(
            "clawagentskill.adopt.rebuild.subprocess.run",
            side_effect=FileNotFoundError("No such file or directory: 'python'"),
        ):
            # FileNotFoundError triggers the skip path, which returns True
            assert rebuild(staging, run_dir) is True
