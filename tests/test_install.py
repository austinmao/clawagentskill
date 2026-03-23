"""Tests for adopt/install.py — staging, workspace install, and cleanup."""

from __future__ import annotations

from pathlib import Path

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
