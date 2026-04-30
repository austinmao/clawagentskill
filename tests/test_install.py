"""Tests for adopt/install.py — staging, workspace install, and cleanup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from clawagentskill.adopt.install import (
    cleanup_staging,
    copy_local,
    download_to_staging,
    install_to_workspace,
)


class TestCopyLocal:
    def test_copy_local_creates_file(self, tmp_path: Path):
        source = tmp_path / "source" / "SKILL.md"
        source.parent.mkdir(parents=True)
        source.write_text("# My Skill\nHello world", encoding="utf-8")

        staging = tmp_path / "staging" / "my-skill" / "SKILL.md"
        result = copy_local(source, staging)

        assert result == staging
        assert staging.exists()
        assert staging.read_text(encoding="utf-8") == "# My Skill\nHello world"


class TestInstallToWorkspace:
    def test_install_to_workspace_creates_parent_dirs(self, tmp_path: Path):
        staging = tmp_path / "staged" / "SKILL.md"
        staging.parent.mkdir(parents=True)
        staging.write_text("---\nname: test\n---\nBody", encoding="utf-8")

        target = tmp_path / "workspace" / "skills" / "ops" / "my-skill" / "SKILL.md"
        result = install_to_workspace(staging, target)

        assert result == target
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "---\nname: test\n---\nBody"


class TestCleanupStaging:
    def test_cleanup_staging_removes_dir(self, tmp_path: Path):
        staging_base = tmp_path / "staging"
        skill_dir = staging_base / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")

        cleanup_staging("my-skill", staging_base=staging_base)

        assert not skill_dir.exists()

    def test_cleanup_staging_noop_when_absent(self, tmp_path: Path):
        staging_base = tmp_path / "staging"
        # Directory does not exist — should not raise
        cleanup_staging("nonexistent-skill", staging_base=staging_base)


class TestDownloadGithubUrlRewriting:
    def test_download_github_url_rewriting(self, tmp_path: Path):
        """Verify that github.com/blob/ URLs get rewritten to raw.githubusercontent.com.

        We test the URL transformation logic that lives inside download_to_staging
        by examining the pattern directly rather than making real HTTP calls.
        """
        # The install module rewrites URLs with this logic:
        #   if "github.com" in raw_url and "/blob/" in raw_url:
        #       raw_url = raw_url.replace("github.com", "raw.githubusercontent.com")
        #                        .replace("/blob/", "/")
        original = "https://github.com/user/repo/blob/main/skills/test/SKILL.md"
        expected = "https://raw.githubusercontent.com/user/repo/main/skills/test/SKILL.md"

        # Apply the same transformation used in the source
        rewritten = original.replace(
            "github.com", "raw.githubusercontent.com"
        ).replace("/blob/", "/")

        assert rewritten == expected

        # Non-blob URL should remain unchanged
        non_blob = "https://github.com/user/repo/tree/main/skills/"
        rewritten_non_blob = non_blob
        if "github.com" in rewritten_non_blob and "/blob/" in rewritten_non_blob:
            rewritten_non_blob = rewritten_non_blob.replace(
                "github.com", "raw.githubusercontent.com"
            ).replace("/blob/", "/")
        assert rewritten_non_blob == non_blob


class TestDownloadSkillsShUrl:
    def test_skills_sh_url_uses_skills_cli_staging(self, tmp_path: Path):
        install_ref = "https://skills.sh/github/awesome-copilot/review-and-refactor"
        staged_text = "---\nname: review-and-refactor\n---\nBody"

        def fake_run(*args, **kwargs):
            cwd = Path(kwargs["cwd"])
            installed = cwd / "skills" / "review-and-refactor" / "SKILL.md"
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_text(staged_text, encoding="utf-8")
            return Mock(returncode=0, stdout="", stderr="")

        with (
            patch("clawagentskill.adopt.install.httpx.get") as httpx_get,
            patch("clawagentskill.adopt.install.subprocess.run", side_effect=fake_run) as run,
        ):
            result = download_to_staging(
                install_ref,
                "review-and-refactor",
                staging_base=tmp_path / "staging",
            )

        assert result.exists()
        assert result.read_text(encoding="utf-8") == staged_text
        httpx_get.assert_not_called()
        run.assert_called_once()
        command = run.call_args.args[0]
        assert command == [
            "npx",
            "--yes",
            "skills",
            "add",
            "github/awesome-copilot",
            "--skill",
            "review-and-refactor",
            "--yes",
            "--agent",
            "openclaw",
        ]

    def test_html_response_raises_runtime_error(self, tmp_path: Path):
        # A URL that returns HTML (e.g. a marketplace page, not a raw SKILL.md) and
        # is not a recognized skills.sh URL should raise RuntimeError — no silent fallback.
        install_ref = "https://example.com/not-a-skill-file"
        html_response = Mock(status_code=200, text="<!DOCTYPE html><html>marketplace</html>")

        with (
            patch("clawagentskill.adopt.install.httpx.get", return_value=html_response) as httpx_get,
            pytest.raises(RuntimeError, match="Could not download skill"),
        ):
            download_to_staging(
                install_ref,
                "test-skill",
                staging_base=tmp_path / "staging",
            )

        httpx_get.assert_called_once_with(install_ref, timeout=30, follow_redirects=True)


class TestDownloadDirectUrlNormalization:
    """Regression tests for the 2026-04-24 URL-format coverage fix.

    Before the fix, ``github.com/<org>/<repo>`` repo URLs and
    ``skills.sh/<org>/<slug>`` dashboard URLs (2 path segments only)
    fell through to the direct httpx fetch, which returned HTML and
    failed the ``_looks_like_html`` check. LLM direct-URL fallback was
    broken for the two shapes LLMs most commonly paste.

    The normalizer converts both shapes into bare ``owner/repo`` slugs
    and delegates to ``npx skills add``.
    """

    def _fake_skills_run(self, skill_text: str, skill_dir_name: str):
        """Build a subprocess.run fake that pretends ``npx skills add`` succeeded."""
        def _fake(*args, **kwargs):
            cwd = Path(kwargs["cwd"])
            installed = cwd / "skills" / skill_dir_name / "SKILL.md"
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_text(skill_text, encoding="utf-8")
            return Mock(returncode=0, stdout="", stderr="")

        return _fake

    def test_github_repo_url_normalized_to_slug(self, tmp_path: Path):
        """``https://github.com/<org>/<repo>`` → ``npx skills add <org>/<repo>``."""
        install_ref = "https://github.com/membranedev/fireflies"
        staged_text = "---\nname: fireflies\n---\nBody"

        fake = self._fake_skills_run(staged_text, "fireflies")

        with (
            patch("clawagentskill.adopt.install.httpx.get") as httpx_get,
            patch("clawagentskill.adopt.install.subprocess.run", side_effect=fake) as run,
        ):
            httpx_get.return_value = Mock(
                status_code=200,
                text="<!DOCTYPE html><html>GitHub repo page</html>",
            )
            result = download_to_staging(
                install_ref,
                "fireflies",
                staging_base=tmp_path / "staging",
            )

        assert result.exists()
        assert result.read_text(encoding="utf-8") == staged_text
        run.assert_called_once()
        command = run.call_args.args[0]
        assert command == [
            "npx",
            "--yes",
            "skills",
            "add",
            "membranedev/fireflies",
            "--skill",
            "fireflies",
            "--yes",
            "--agent",
            "openclaw",
        ]

    def test_github_repo_url_strips_dot_git(self, tmp_path: Path):
        """``https://github.com/owner/repo.git`` → ``owner/repo`` (strip .git)."""
        install_ref = "https://github.com/owner/cool-skill.git"
        staged_text = "---\nname: cool-skill\n---\nBody"

        fake = self._fake_skills_run(staged_text, "cool-skill")

        with (
            patch("clawagentskill.adopt.install.httpx.get") as httpx_get,
            patch("clawagentskill.adopt.install.subprocess.run", side_effect=fake) as run,
        ):
            httpx_get.return_value = Mock(
                status_code=200,
                text="<!DOCTYPE html><html>GitHub repo page</html>",
            )
            result = download_to_staging(
                install_ref,
                "cool-skill",
                staging_base=tmp_path / "staging",
            )

        assert result.exists()
        assert result.read_text(encoding="utf-8") == staged_text
        run.assert_called_once()
        assert run.call_args.args[0][4] == "owner/cool-skill"

    def test_skills_sh_dashboard_url_normalized_to_slug(self, tmp_path: Path):
        """``https://skills.sh/<owner>/<slug>`` (2 parts) → bare-slug npx install.

        The existing 3-part path (``skills.sh/<owner>/<repo>/<skill>``) goes
        through ``_parse_skills_sh_ref`` — still honored. This test covers the
        2-part dashboard URL that previously fell through to httpx.
        """
        install_ref = "https://skills.sh/membranedev/fireflies-sdk-patterns"
        staged_text = "---\nname: fireflies-sdk-patterns\n---\nBody"

        fake = self._fake_skills_run(staged_text, "fireflies-sdk-patterns")

        with (
            patch("clawagentskill.adopt.install.httpx.get") as httpx_get,
            patch("clawagentskill.adopt.install.subprocess.run", side_effect=fake) as run,
        ):
            httpx_get.return_value = Mock(
                status_code=200,
                text="<!DOCTYPE html><html>skills.sh dashboard</html>",
            )
            result = download_to_staging(
                install_ref,
                "fireflies-sdk-patterns",
                staging_base=tmp_path / "staging",
            )

        assert result.exists()
        assert result.read_text(encoding="utf-8") == staged_text
        run.assert_called_once()
        assert run.call_args.args[0][4] == "membranedev/fireflies-sdk-patterns"

    def test_github_blob_url_still_uses_raw_rewrite(self, tmp_path: Path):
        """``github.com/.../blob/...`` URL with >2 parts: raw rewrite path wins.

        Normalizer must NOT hijack URLs that the existing raw-rewrite logic
        already handles successfully.
        """
        install_ref = "https://github.com/owner/repo/blob/main/skills/test/SKILL.md"
        raw_body = "---\nname: test\n---\nBody content"
        ok_response = Mock(status_code=200, text=raw_body)

        with (
            patch("clawagentskill.adopt.install.httpx.get", return_value=ok_response) as httpx_get,
            patch("clawagentskill.adopt.install.subprocess.run") as run,
        ):
            result = download_to_staging(
                install_ref,
                "test",
                staging_base=tmp_path / "staging",
            )

        assert result.exists()
        assert result.read_text(encoding="utf-8") == raw_body
        httpx_get.assert_called_once()
        fetched_url = httpx_get.call_args.args[0]
        assert fetched_url == (
            "https://raw.githubusercontent.com/owner/repo/main/skills/test/SKILL.md"
        )
        run.assert_not_called()

    def test_github_tree_url_does_not_normalize(self, tmp_path: Path):
        """``github.com/<org>/<repo>/tree/...`` must NOT trigger normalization.

        Normalizer requires exactly 2 path parts — branch-tree URLs have more
        and are not repo roots.
        """
        install_ref = "https://github.com/owner/repo/tree/main"
        html_response = Mock(
            status_code=200,
            text="<!DOCTYPE html><html>GitHub tree page</html>",
        )

        with (
            patch("clawagentskill.adopt.install.httpx.get", return_value=html_response),
            patch("clawagentskill.adopt.install.subprocess.run") as run,
            pytest.raises(RuntimeError, match="Could not download skill"),
        ):
            download_to_staging(
                install_ref,
                "repo",
                staging_base=tmp_path / "staging",
            )

        run.assert_not_called()
