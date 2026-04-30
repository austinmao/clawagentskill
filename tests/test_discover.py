"""Unit tests for the discovery modules (local, skills_sh, github)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from clawagentskill.discover import local, skills_sh, github


# ── Local discovery tests (filesystem, no mocking) ──────────────────────


class TestLocalDiscovery:
    def _create_skill(self, root: Path, rel_path: str) -> Path:
        """Helper: create a SKILL.md at the given relative path."""
        skill_md = root / rel_path
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text("---\nname: stub\n---\n")
        return skill_md

    def _create_agent(self, root: Path, rel_path: str) -> Path:
        """Helper: create a SOUL.md at the given relative path."""
        soul_md = root / rel_path
        soul_md.parent.mkdir(parents=True, exist_ok=True)
        soul_md.write_text("# Who I Am\nStub agent\n")
        return soul_md

    def test_local_finds_skill_by_name(self, tmp_path: Path) -> None:
        self._create_skill(tmp_path, "skills/operations/tools/resend/SKILL.md")

        results = local.search("resend", workspace_root=tmp_path)

        assert len(results) == 1
        assert results[0]["name"] == "resend"
        assert results[0]["source"] == "local_workspace"
        assert results[0]["target_path"].endswith("SKILL.md")

    def test_local_finds_agent_by_name(self, tmp_path: Path) -> None:
        self._create_agent(tmp_path, "agents/platform/orchestrator/SOUL.md")

        results = local.search("orchestrator", workspace_root=tmp_path)

        assert len(results) == 1
        assert results[0]["name"] == "orchestrator"
        assert results[0]["source"] == "local_workspace"
        assert results[0]["target_path"].endswith("SOUL.md")

    def test_local_no_results(self, tmp_path: Path) -> None:
        # Empty workspace — no skills/ or agents/ dirs
        results = local.search("nonexistent", workspace_root=tmp_path)

        assert results == []

    def test_local_respects_max_results(self, tmp_path: Path) -> None:
        for i in range(5):
            self._create_skill(tmp_path, f"skills/dept/send-{i}/SKILL.md")

        results = local.search("send", workspace_root=tmp_path, max_results=2)

        assert len(results) == 2

    def test_local_publisher_prefix(self, tmp_path: Path) -> None:
        self._create_skill(tmp_path, "skills/operations/tools/resend/SKILL.md")

        results = local.search("openclaw/resend", workspace_root=tmp_path)

        assert len(results) == 1
        assert results[0]["publisher"] == "openclaw"
        assert results[0]["tier"] == "A"

    def test_local_default_publisher_and_tier(self, tmp_path: Path) -> None:
        """Without publisher prefix, publisher is 'local' and tier is 'C'."""
        self._create_skill(tmp_path, "skills/ops/slack/SKILL.md")

        results = local.search("slack", workspace_root=tmp_path)

        assert len(results) == 1
        assert results[0]["publisher"] == "local"
        assert results[0]["tier"] == "C"

    def test_local_finds_both_skills_and_agents(self, tmp_path: Path) -> None:
        """A broad query can match entries in both skills/ and agents/."""
        self._create_skill(tmp_path, "skills/ops/builder/SKILL.md")
        self._create_agent(tmp_path, "agents/platform/builder/SOUL.md")

        results = local.search("builder", workspace_root=tmp_path)

        assert len(results) == 2
        names = {r["name"] for r in results}
        assert names == {"builder"}


# ── skills_sh search tests (mock subprocess) ────────────────────────────


class TestSkillsShSearch:
    def test_skills_sh_json_output(self) -> None:
        json_payload = json.dumps([
            {"name": "resend", "publisher": "wshobson", "install_ref": "https://skills.sh/wshobson/resend", "install_count": 5200, "tier": "B", "source": "npx_search"},
            {"name": "stripe", "publisher": "wshobson", "install_ref": "https://skills.sh/wshobson/stripe", "install_count": 3100, "tier": "B", "source": "npx_search"},
        ])

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json_payload

        with patch("clawagentskill.discover.skills_sh.subprocess.run", return_value=mock_result):
            results = skills_sh.search("resend")

        assert len(results) == 2
        assert results[0]["name"] == "resend"
        assert results[1]["name"] == "stripe"

    def test_skills_sh_json_dict_format(self) -> None:
        """Handle JSON response wrapped in a {results: [...]} dict."""
        json_payload = json.dumps({
            "results": [
                {"name": "notion", "publisher": "author1", "install_ref": "ref", "install_count": 100, "tier": "C", "source": "npx_search"},
            ],
        })

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json_payload

        with patch("clawagentskill.discover.skills_sh.subprocess.run", return_value=mock_result):
            results = skills_sh.search("notion")

        assert len(results) == 1
        assert results[0]["name"] == "notion"

    def test_skills_sh_text_output(self) -> None:
        # The skills CLI always emits ANSI-colored output — never bare plain text.
        # Mock the actual format it produces so the parser is tested against reality.
        ansi_output = (
            "\n"
            "\x1b[38;5;250m███████╗██╗  ██╗\x1b[0m\n"
            "\n"
            "\x1b[38;5;102mInstall with\x1b[0m npx skills add <owner/repo@skill>\n"
            "\n"
            "\x1b[38;5;145mwshobson/agents@resend-email-sender\x1b[0m \x1b[36m5200 installs\x1b[0m\n"
            "\x1b[38;5;102m└ https://skills.sh/wshobson/agents/resend-email-sender\x1b[0m\n"
            "\n"
            "\x1b[38;5;145msome-user/skills@stripe-integration\x1b[0m \x1b[36m120 installs\x1b[0m\n"
            "\x1b[38;5;102m└ https://skills.sh/some-user/skills/stripe-integration\x1b[0m\n"
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ansi_output

        with patch("clawagentskill.discover.skills_sh.subprocess.run", return_value=mock_result):
            results = skills_sh.search("resend")

        assert len(results) == 2
        assert results[0]["source"] == "npx_search"
        assert results[0]["publisher"] == "wshobson"
        assert results[0]["tier"] == "C"
        assert results[0]["name"] == "resend-email-sender"
        assert results[0]["install_ref"] == "wshobson/agents@resend-email-sender"
        assert results[0]["install_count"] == 5200
        assert results[0]["install_url"] == "https://skills.sh/wshobson/agents/resend-email-sender"
        assert results[1]["name"] == "stripe-integration"
        assert results[1]["install_count"] == 120

    def test_skills_sh_timeout(self) -> None:
        with patch(
            "clawagentskill.discover.skills_sh.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="npx", timeout=60),
        ):
            results = skills_sh.search("anything")

        assert results == []

    def test_skills_sh_not_found(self) -> None:
        with patch(
            "clawagentskill.discover.skills_sh.subprocess.run",
            side_effect=FileNotFoundError("npx not found"),
        ):
            results = skills_sh.search("anything")

        assert results == []

    def test_skills_sh_nonzero_return(self) -> None:
        """Non-zero returncode yields empty results."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("clawagentskill.discover.skills_sh.subprocess.run", return_value=mock_result):
            results = skills_sh.search("fail")

        assert results == []

    def test_skills_sh_respects_max_results(self) -> None:
        json_payload = json.dumps([
            {"name": f"skill-{i}", "publisher": "pub", "install_ref": f"ref-{i}", "install_count": i, "tier": "C", "source": "npx_search"}
            for i in range(10)
        ])

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json_payload

        with patch("clawagentskill.discover.skills_sh.subprocess.run", return_value=mock_result):
            results = skills_sh.search("skill", max_results=3)

        assert len(results) == 3


# ── GitHub search tests (mock httpx) ────────────────────────────────────


class TestGitHubSearch:
    REGISTRIES: tuple[dict[str, str], ...] = (
        {"repo": "voltagent/voltagent", "path": "agents/", "type": "claude-code"},
    )

    def _make_dir_entry(self, name: str) -> dict[str, Any]:
        """Create a mock GitHub API directory entry."""
        return {
            "name": name,
            "type": "dir",
            "html_url": f"https://github.com/voltagent/voltagent/tree/main/agents/{name}",
        }

    def _make_file_entry(self, name: str) -> dict[str, Any]:
        """Create a mock GitHub API file entry."""
        return {
            "name": name,
            "type": "file",
            "download_url": f"https://raw.githubusercontent.com/voltagent/voltagent/main/agents/{name}",
        }

    @pytest.mark.asyncio
    async def test_github_search_returns_candidates(self) -> None:
        entries = [
            self._make_dir_entry("code-reviewer"),
            self._make_dir_entry("code-helper"),
            self._make_dir_entry("deploy-bot"),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = entries

        with patch("clawagentskill.discover.github.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await github.search_async("code", self.REGISTRIES)

        assert len(results) == 2
        names = {r["name"] for r in results}
        assert "code-reviewer" in names
        assert "code-helper" in names
        for r in results:
            assert r["source"] == "github"
            assert r["publisher"] == "voltagent"

    @pytest.mark.asyncio
    async def test_github_search_handles_error(self) -> None:
        with patch("clawagentskill.discover.github.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await github.search_async("anything", self.REGISTRIES)

        assert results == []

    @pytest.mark.asyncio
    async def test_github_search_non_200_status(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("clawagentskill.discover.github.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await github.search_async("anything", self.REGISTRIES)

        assert results == []

    @pytest.mark.asyncio
    async def test_github_search_matches_md_files(self) -> None:
        entries = [
            self._make_file_entry("code-reviewer.md"),
            self._make_file_entry("deploy-bot.md"),
            self._make_file_entry("README.md"),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = entries

        with patch("clawagentskill.discover.github.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await github.search_async("code", self.REGISTRIES)

        assert len(results) == 1
        assert results[0]["name"] == "code-reviewer"

    @pytest.mark.asyncio
    async def test_github_search_respects_max_results(self) -> None:
        entries = [self._make_dir_entry(f"agent-{i}") for i in range(10)]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = entries

        with patch("clawagentskill.discover.github.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await github.search_async("agent", self.REGISTRIES, max_results=3)

        assert len(results) <= 3

    def test_github_sync_wrapper(self) -> None:
        """The sync search() function wraps search_async via asyncio.run."""
        entries = [self._make_dir_entry("helper-bot")]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = entries

        with patch("clawagentskill.discover.github.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = github.search("helper", self.REGISTRIES)

        assert len(results) == 1
        assert results[0]["name"] == "helper-bot"
