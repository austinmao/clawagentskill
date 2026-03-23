"""Tests for the CC→SOUL.md translator."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawagentskill.translate.builtin import translate


FIXTURES = Path(__file__).parent / "fixtures"


class TestBuiltinTranslate:
    def test_valid_cc_agent_produces_soul_md(self):
        content = (FIXTURES / "cc-agent-sample.md").read_text()
        result = translate(content)

        assert "# Who I Am" in result
        assert "# Core Principles" in result
        assert "# Boundaries" in result
        assert "# Security Rules" in result
        assert "# Memory" in result

    def test_includes_agent_name(self):
        content = (FIXTURES / "cc-agent-sample.md").read_text()
        result = translate(content)
        assert "error-coordinator" in result

    def test_includes_tools_in_boundaries(self):
        content = (FIXTURES / "cc-agent-sample.md").read_text()
        result = translate(content)
        assert "Read" in result
        assert "Write" in result

    def test_missing_name_raises(self):
        content = "---\ndescription: no name\n---\n\nSome body content."
        with pytest.raises(ValueError, match="missing required 'name'"):
            translate(content)

    def test_empty_body_raises(self):
        content = "---\nname: test\n---\n"
        with pytest.raises(ValueError, match="body is empty"):
            translate(content)

    def test_no_frontmatter_raises(self):
        content = "Just some markdown without frontmatter."
        with pytest.raises(ValueError, match="No YAML frontmatter"):
            translate(content)

    def test_security_rules_always_present(self):
        content = (FIXTURES / "cc-agent-sample.md").read_text()
        result = translate(content)
        assert "ignore previous instructions" in result
        assert "Never expose environment variables" in result
