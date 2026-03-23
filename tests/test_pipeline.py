"""Pipeline tests for adoption workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from clawagentskill.pipeline import run_adopt


FIXTURES = Path(__file__).parent / "fixtures"


class TestTierASkipsScanners:
    """Scenario: tier-a-skips-scanners — query "openclaw/resend" with local workspace."""

    def test_tier_a_install(self, tmp_path: Path):
        """Tier A skill from local workspace should skip scanners and install."""
        # Create a mock workspace with a local skill
        skills_dir = tmp_path / "skills" / "operations" / "tools" / "resend"
        skills_dir.mkdir(parents=True)
        skill_md = skills_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: resend\ndescription: Send email\nversion: 1.0.0\n"
            "permissions:\n  filesystem: none\n  network: true\n---\n# Resend\nSend emails via Resend API.\n"
        )

        result = asyncio.run(run_adopt(
            "openclaw/resend",
            auto_approve=True,
            force=True,
            workspace_root=tmp_path,
        ))

        assert result["status"] == "installed"
        assert result["verdict"] == "install"


class TestBlockedClawHavocPattern:
    """Scenario: blocked-clawhavoc-pattern — fixture with C2 IP triggers block."""

    def test_clawhavoc_blocked(self, tmp_path: Path):
        """ClawHavoc fixture should be blocked at prefilter stage."""
        # Create workspace with clawhavoc fixture as a "local skill"
        skills_dir = tmp_path / "skills" / "platform" / "governance" / "test-clawhavoc"
        skills_dir.mkdir(parents=True)
        skill_md = skills_dir / "SKILL.md"

        # Copy clawhavoc fixture
        import shutil
        shutil.copy2(str(FIXTURES / "clawhavoc-skill.md"), str(skill_md))

        # The pipeline should detect the C2 IP in prefilter stage
        result = asyncio.run(run_adopt(
            "openclaw/test-clawhavoc",
            auto_approve=True,
            force=True,
            workspace_root=tmp_path,
        ))

        assert result["status"] == "blocked"
        assert result["stage"] == "prefilter"


class TestWarnTriggersRebuild:
    """Scenario: warn-triggers-rebuild — overpermissioned fixture from untrusted publisher."""

    def test_untrusted_warn_triggers_rebuild(self, tmp_path: Path):
        """Overpermissioned skill from untrusted publisher should trigger rebuild verdict."""
        from clawagentskill.decide.rule_c import apply_rule_c

        # Simulate scan results with warn findings
        scan_results = {
            "prefilter": {"status": "clean", "findings": []},
            "permission": {
                "status": "warn",
                "findings": [{"code": "exfil-risk", "severity": "warn", "message": "fs:write + net:true"}],
            },
            "config": {"status": "clean", "findings": []},
            "injection": {"status": "clean", "findings": []},
        }

        decision = apply_rule_c("C", "untrusted-publisher", scan_results, ("openclaw", "anthropic"))
        assert decision["verdict"] == "rebuild"
        assert "permission" in decision.get("rebuild_scope", [])
