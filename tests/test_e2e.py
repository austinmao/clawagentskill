"""End-to-end tests that run the CLI as a subprocess.

Exercises the full clawagentskill CLI through ``python3 -m clawagentskill``
with real fixture files and temp workspaces.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PACKAGE_DIR = Path(__file__).resolve().parent.parent


class TestE2EScan:
    def test_e2e_scan_clean_fixture(self) -> None:
        """Scan a clean fixture -> exit 0, output contains CLEAN."""
        clean_path = FIXTURES_DIR / "clean-skill.md"

        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "scan", str(clean_path)],
            capture_output=True,
            text=True,
            cwd=str(PACKAGE_DIR),
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for clean fixture.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "CLEAN" in combined, (
            f"Expected 'CLEAN' in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_e2e_scan_clawhavoc_fixture(self) -> None:
        """Scan a ClawHavoc fixture -> exit 1, output contains BLOCKED."""
        havoc_path = FIXTURES_DIR / "clawhavoc-skill.md"

        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "scan", str(havoc_path)],
            capture_output=True,
            text=True,
            cwd=str(PACKAGE_DIR),
            timeout=30,
        )

        assert result.returncode == 1, (
            f"Expected exit 1 for ClawHavoc fixture.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "BLOCKED" in combined, (
            f"Expected 'BLOCKED' in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_e2e_scan_json_output(self) -> None:
        """Scan with --json flag -> valid JSON with all 4 scanner keys."""
        clean_path = FIXTURES_DIR / "clean-skill.md"

        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "scan", "--json", str(clean_path)],
            capture_output=True,
            text=True,
            cwd=str(PACKAGE_DIR),
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for JSON scan.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        data = json.loads(result.stdout)
        expected_keys = {"prefilter", "permission", "config", "injection"}
        assert expected_keys == set(data.keys()), (
            f"Expected keys {expected_keys}, got {set(data.keys())}"
        )

        # Each scanner result should have a status field
        for scanner_name, scanner_result in data.items():
            assert "status" in scanner_result, (
                f"Scanner '{scanner_name}' result missing 'status' field"
            )


class TestE2EAdopt:
    def test_e2e_adopt_tier_a_local(self, tmp_path: Path) -> None:
        """Create a temp workspace with a local skill, adopt it -> exit 0."""
        # Set up a minimal workspace with a local skill
        skill_dir = tmp_path / "skills" / "operations" / "tools" / "resend"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\n"
            'name: resend\n'
            'description: "Send email via Resend API"\n'
            'version: "1.0.0"\n'
            "permissions:\n"
            "  filesystem: none\n"
            "  network: true\n"
            "triggers:\n"
            "  - command: /resend\n"
            "metadata:\n"
            "  openclaw:\n"
            '    emoji: "\\U0001F4E7"\n'
            "    requires:\n"
            "      env: [RESEND_API_KEY]\n"
            "---\n"
            "\n"
            "# Resend\n"
            "\n"
            "Send email via Resend API.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable, "-m", "clawagentskill",
                "adopt", "openclaw/resend", "--yes",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for Tier A local adopt.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "Installed" in combined or "installed" in combined.lower(), (
            f"Expected 'Installed' in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestE2EStatus:
    def test_e2e_status_empty(self, tmp_path: Path) -> None:
        """Run status in empty workspace -> exit 0, 'No adoption runs'."""
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "status"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for empty status.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "No adoption runs" in combined or "no adoption runs" in combined.lower(), (
            f"Expected 'No adoption runs' in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestE2EHelp:
    def test_e2e_help(self) -> None:
        """Run --help -> exit 0, all 8 subcommands listed."""
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "--help"],
            capture_output=True,
            text=True,
            cwd=str(PACKAGE_DIR),
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for --help.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        expected_subcommands = [
            "find", "adopt", "port", "scan",
            "status", "state-init", "validate-prereqs", "get-field",
        ]
        for subcmd in expected_subcommands:
            assert subcmd in result.stdout, (
                f"Expected subcommand '{subcmd}' in --help output.\n"
                f"stdout: {result.stdout}"
            )


class TestE2EVersion:
    def test_e2e_version(self) -> None:
        """Run --version -> exit 0, contains '0.1.0'."""
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "--version"],
            capture_output=True,
            text=True,
            cwd=str(PACKAGE_DIR),
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for --version.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "0.1.0" in result.stdout, (
            f"Expected '0.1.0' in version output.\nstdout: {result.stdout}"
        )
