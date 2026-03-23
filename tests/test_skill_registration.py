"""Tests for workspace skill registration."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).parent.parent.parent  # clawagentskill/ -> openclaw/


class TestClawAgentSkillRegistration:
    """Verify clawagentskill is registered in the workspace skill tree."""

    def test_skill_md_exists(self):
        skill_path = REPO_ROOT / "skills" / "platform" / "governance" / "clawagentskill" / "SKILL.md"
        assert skill_path.exists(), f"SKILL.md not found at {skill_path}"

    def test_skill_md_has_valid_frontmatter(self):
        skill_path = REPO_ROOT / "skills" / "platform" / "governance" / "clawagentskill" / "SKILL.md"
        content = skill_path.read_text()
        parts = content.split("---", 2)
        assert len(parts) >= 3, "No YAML frontmatter found"

        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter.get("name") == "clawagentskill"
        assert "description" in frontmatter
        assert "permissions" in frontmatter
        assert "triggers" in frontmatter

    def test_skill_md_requires_python3(self):
        skill_path = REPO_ROOT / "skills" / "platform" / "governance" / "clawagentskill" / "SKILL.md"
        content = skill_path.read_text()
        parts = content.split("---", 2)
        frontmatter = yaml.safe_load(parts[1])
        requires = frontmatter.get("metadata", {}).get("openclaw", {}).get("requires", {})
        bins = requires.get("bins", [])
        assert "python3" in bins, f"python3 not in requires.bins: {bins}"
