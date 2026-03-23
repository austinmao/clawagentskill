"""Tests for translate/skillkit.py — 3-tier SkillKit translation fallback."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from clawagentskill.translate.skillkit import translate


FIXTURES = Path(__file__).parent / "fixtures"


class TestSkillkitTranslateFallback:
    @pytest.fixture()
    def cc_agent_content(self) -> str:
        return (FIXTURES / "cc-agent-sample.md").read_text(encoding="utf-8")

    def test_falls_back_to_builtin_when_no_skillkit(self, cc_agent_content: str):
        with patch("clawagentskill.translate.skillkit.shutil.which", return_value=None):
            result = translate(cc_agent_content)

        # Builtin converter produces SOUL.md sections
        assert "# Who I Am" in result
        assert "error-coordinator" in result

    def test_tries_openclaw_format_first(self, cc_agent_content: str):
        mock_result = subprocess.CompletedProcess(
            args=["skillkit", "translate", "--to", "openclaw"],
            returncode=0,
            stdout="# Who I Am\n\nI am skillkit-translated agent.",
            stderr="",
        )
        with (
            patch(
                "clawagentskill.translate.skillkit.shutil.which",
                return_value="/usr/local/bin/skillkit",
            ),
            patch(
                "clawagentskill.translate.skillkit.subprocess.run",
                return_value=mock_result,
            ),
        ):
            result = translate(cc_agent_content)

        assert result == "# Who I Am\n\nI am skillkit-translated agent."

    def test_falls_back_to_clawdbot_on_openclaw_failure(self, cc_agent_content: str):
        openclaw_fail = subprocess.CompletedProcess(
            args=["skillkit", "translate", "--to", "openclaw"],
            returncode=1,
            stdout="",
            stderr="unsupported format",
        )
        clawdbot_ok = subprocess.CompletedProcess(
            args=["skillkit", "translate", "--to", "clawdbot"],
            returncode=0,
            stdout="# Who I Am\n\nI am clawdbot-translated agent.",
            stderr="",
        )

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "--to" in cmd:
                idx = cmd.index("--to")
                fmt = cmd[idx + 1]
                if fmt == "openclaw":
                    return openclaw_fail
                if fmt == "clawdbot":
                    return clawdbot_ok
            return openclaw_fail

        with (
            patch(
                "clawagentskill.translate.skillkit.shutil.which",
                return_value="/usr/local/bin/skillkit",
            ),
            patch(
                "clawagentskill.translate.skillkit.subprocess.run",
                side_effect=mock_run,
            ),
        ):
            result = translate(cc_agent_content)

        assert result == "# Who I Am\n\nI am clawdbot-translated agent."
        assert call_count == 2

    def test_all_tiers_fail_uses_builtin(self, cc_agent_content: str):
        fail_result = subprocess.CompletedProcess(
            args=["skillkit", "translate"],
            returncode=1,
            stdout="",
            stderr="error",
        )
        with (
            patch(
                "clawagentskill.translate.skillkit.shutil.which",
                return_value="/usr/local/bin/skillkit",
            ),
            patch(
                "clawagentskill.translate.skillkit.subprocess.run",
                return_value=fail_result,
            ),
        ):
            result = translate(cc_agent_content)

        # Falls through to builtin translator
        assert "# Who I Am" in result
        assert "error-coordinator" in result
        assert "# Security Rules" in result
