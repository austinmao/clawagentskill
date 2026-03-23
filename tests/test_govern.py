"""Unit tests for the governance integration modules.

Verifies that each governance module (scaffold, clawspec, clawwrap, paperclip)
handles missing dependencies and absent infrastructure gracefully.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml

from clawagentskill.govern import clawspec, clawwrap, paperclip, scaffold


class TestScaffold:
    def test_scaffold_skip_when_absent(self, tmp_path: Path) -> None:
        """ClawScaffold not importable -> status=skip."""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text("# Skill\n", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        # scaffold.register tries to import compiler.engine.cli.scaffold_adopt;
        # that module is never installed in this test env, so ImportError fires.
        result = scaffold.register(skill_path, run_dir)

        assert result["status"] == "skip"
        assert "not importable" in result["reason"]

    def test_scaffold_registered_when_available(self, tmp_path: Path) -> None:
        """When ClawScaffold is importable and works, status=registered."""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text("# Skill\n", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        with patch(
            "clawagentskill.govern.scaffold.scaffold_adopt",
            create=True,
        ):
            # Patch the import inside the function
            import importlib
            import types

            fake_cli = types.ModuleType("compiler.engine.cli")
            fake_cli.scaffold_adopt = lambda path: None  # type: ignore[attr-defined]

            with patch.dict("sys.modules", {"compiler": types.ModuleType("compiler"),
                                             "compiler.engine": types.ModuleType("compiler.engine"),
                                             "compiler.engine.cli": fake_cli}):
                result = scaffold.register(skill_path, run_dir)

        assert result["status"] == "registered"
        assert result["path"] == str(skill_path)


class TestClawSpec:
    def test_clawspec_skip_when_absent(self, tmp_path: Path) -> None:
        """ClawSpec not importable -> status=skip."""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text("# Skill\n", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        # clawspec.audit tries to import clawspec.runner.run_scenarios;
        # that module is never installed in this test env.
        result = clawspec.audit(skill_path, run_dir)

        assert result["status"] == "skip"
        assert "not importable" in result["reason"]

    def test_clawspec_skip_when_no_scenarios(self, tmp_path: Path) -> None:
        """ClawSpec importable but no scenarios.yaml -> status=skip."""
        skill_path = tmp_path / "skills" / "test" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# Skill\n", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        import types

        fake_runner = types.ModuleType("clawspec.runner")
        fake_runner.run_scenarios = lambda path: {"passed": True}  # type: ignore[attr-defined]

        with patch.dict("sys.modules", {
            "clawspec": types.ModuleType("clawspec"),
            "clawspec.runner": fake_runner,
        }):
            result = clawspec.audit(skill_path, run_dir)

        assert result["status"] == "skip"
        assert "No scenarios.yaml" in result["reason"]


class TestClawWrap:
    def test_clawwrap_skip_when_no_targets(self, tmp_path: Path) -> None:
        """No targets.yaml -> status=skip."""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text("# Skill with no outbound.submit\n", encoding="utf-8")

        # workspace_root has no clawwrap/config/targets.yaml
        result = clawwrap.check(skill_path, tmp_path)

        assert result["status"] == "skip"
        assert "targets.yaml not found" in result["reason"]

    def test_clawwrap_clean_when_no_outbound_submit(self, tmp_path: Path) -> None:
        """Skill without outbound.submit -> status=clean."""
        # Create targets.yaml so the check proceeds past the first guard
        targets_dir = tmp_path / "clawwrap" / "config"
        targets_dir.mkdir(parents=True)
        targets_yaml = targets_dir / "targets.yaml"
        targets_yaml.write_text(
            yaml.dump({"targets": {"resend": {"channel": "email"}}}),
            encoding="utf-8",
        )

        skill_path = tmp_path / "skills" / "test-skill" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text(
            "---\nname: test-skill\n---\n# Test\nNo outbound calls here.\n",
            encoding="utf-8",
        )

        result = clawwrap.check(skill_path, tmp_path)

        assert result["status"] == "clean"
        assert "No outbound.submit" in result["message"]

    def test_clawwrap_detects_outbound_submit(self, tmp_path: Path) -> None:
        """Skill with outbound.submit + targets.yaml exists but skill not registered
        -> status=requires_registration."""
        # Create targets.yaml with a different skill registered
        targets_dir = tmp_path / "clawwrap" / "config"
        targets_dir.mkdir(parents=True)
        targets_yaml = targets_dir / "targets.yaml"
        targets_yaml.write_text(
            yaml.dump({"targets": {"other-skill": {"channel": "email"}}}),
            encoding="utf-8",
        )

        skill_path = tmp_path / "skills" / "my-sender" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text(
            "---\nname: my-sender\n---\n# Sender\nCall outbound.submit to send email.\n",
            encoding="utf-8",
        )

        result = clawwrap.check(skill_path, tmp_path)

        assert result["status"] == "requires_registration"
        assert "my-sender" in result["message"]

    def test_clawwrap_clean_when_already_registered(self, tmp_path: Path) -> None:
        """Skill uses outbound.submit but its target is already in targets.yaml
        -> status=clean."""
        targets_dir = tmp_path / "clawwrap" / "config"
        targets_dir.mkdir(parents=True)
        targets_yaml = targets_dir / "targets.yaml"
        targets_yaml.write_text(
            yaml.dump({"targets": {"my-sender": {"channel": "email"}}}),
            encoding="utf-8",
        )

        skill_path = tmp_path / "skills" / "my-sender" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text(
            "---\nname: my-sender\n---\n# Sender\nCall outbound.submit to dispatch.\n",
            encoding="utf-8",
        )

        result = clawwrap.check(skill_path, tmp_path)

        assert result["status"] == "clean"
        assert "already registered" in result["message"]

    def test_clawwrap_skip_when_skill_missing(self, tmp_path: Path) -> None:
        """Skill file does not exist -> status=skip."""
        targets_dir = tmp_path / "clawwrap" / "config"
        targets_dir.mkdir(parents=True)
        (targets_dir / "targets.yaml").write_text(
            yaml.dump({"targets": {}}), encoding="utf-8",
        )

        missing_skill = tmp_path / "skills" / "gone" / "SKILL.md"

        result = clawwrap.check(missing_skill, tmp_path)

        assert result["status"] == "skip"
        assert "Skill file not found" in result["reason"]


class TestPaperclip:
    def test_paperclip_skip_when_unreachable(self, tmp_path: Path) -> None:
        """Paperclip API unreachable -> status=skip."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        with patch("clawagentskill.govern.paperclip.httpx.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            result = paperclip.export("test-skill", run_dir)

        assert result["status"] == "skip"
        assert "unreachable" in result["reason"].lower() or "Paperclip" in result["reason"]

    def test_paperclip_skip_when_unhealthy(self, tmp_path: Path) -> None:
        """Paperclip health check returns non-200 -> status=skip."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        mock_response = httpx.Response(status_code=503)

        with patch("clawagentskill.govern.paperclip.httpx.get", return_value=mock_response):
            result = paperclip.export("test-skill", run_dir)

        assert result["status"] == "skip"
        assert "unhealthy" in result["reason"].lower()

    def test_paperclip_registered_when_healthy(self, tmp_path: Path) -> None:
        """Paperclip healthy + post succeeds -> status=registered."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        health_resp = httpx.Response(status_code=200)
        post_resp = httpx.Response(status_code=201)

        with patch("clawagentskill.govern.paperclip.httpx.get", return_value=health_resp), \
             patch("clawagentskill.govern.paperclip.httpx.post", return_value=post_resp):
            result = paperclip.export("test-skill", run_dir)

        assert result["status"] == "registered"
        assert result["skill_id"] == "test-skill"

    def test_paperclip_skip_when_post_fails(self, tmp_path: Path) -> None:
        """Paperclip healthy but post fails -> status=skip."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        health_resp = httpx.Response(status_code=200)
        post_resp = httpx.Response(status_code=500)

        with patch("clawagentskill.govern.paperclip.httpx.get", return_value=health_resp), \
             patch("clawagentskill.govern.paperclip.httpx.post", return_value=post_resp):
            result = paperclip.export("test-skill", run_dir)

        assert result["status"] == "skip"
        assert "500" in result["reason"]
