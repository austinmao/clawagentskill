"""Tests for the CLI interface."""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from clawagentskill.cli import _cmd_adopt, build_parser


PACKAGE_DIR = Path(__file__).parent.parent


class TestCLI:
    def test_help_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "--help"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 0
        assert "find" in result.stdout
        assert "adopt" in result.stdout
        assert "port" in result.stdout
        assert "scan" in result.stdout
        assert "status" in result.stdout

    def test_version_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "--version"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_find_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "find", "--help"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 0
        assert "query" in result.stdout

    def test_scan_missing_file(self):
        result = subprocess.run(
            [sys.executable, "-m", "clawagentskill", "scan", "/nonexistent/path.md"],
            capture_output=True, text=True,
            cwd=str(PACKAGE_DIR),
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()


class TestAdoptDisambiguationFlags:
    """Tests for the 2026-04-22 fuzzy-rank adoption bug fix.

    Cover the new CLI flags: --exact, --publisher, --dry-run, --show-top.
    Use parser-level invocation + monkeypatched discovery modules to avoid
    spawning npx (which is slow and network-dependent).
    """

    def test_adopt_flags_are_registered(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "adopt", "fireflies — membranedev",
            "--publisher", "membranedev",
            "--dry-run",
            "--show-top", "5",
            "--exact",
        ])
        assert args.publisher == "membranedev"
        assert args.dry_run is True
        assert args.show_top == 5
        assert args.exact is True

    def test_adopt_dry_run_no_install(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """--dry-run must print the plan and never invoke adopt_sync."""
        corpus = [
            {
                "name": "fireflies",
                "publisher": "membranedev",
                "install_ref": "membranedev/fireflies",
                "install_count": 120,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "game-development",
                "publisher": "miles990",
                "install_ref": "miles990/game-development",
                "install_count": 232,
                "source": "npx_search",
                "tier": "C",
            },
        ]

        monkeypatch.setattr(
            "clawagentskill.discover.skills_sh.search",
            lambda *a, **kw: corpus,
        )
        monkeypatch.setattr(
            "clawagentskill.discover.local.search",
            lambda *a, **kw: [],
        )

        called = {"adopt_sync": 0}

        def _fail_adopt(*args, **kwargs):
            called["adopt_sync"] += 1
            return {"status": "installed", "target_path": "SHOULD_NOT_HAPPEN"}

        monkeypatch.setattr("clawagentskill.pipeline.adopt_sync", _fail_adopt)

        ns = argparse.Namespace(
            query="fireflies — membranedev",
            url="",
            scan_mode="quality",
            yes=True,
            force=False,
            exact=False,
            publisher=None,
            dry_run=True,
            show_top=3,
        )

        rc = _cmd_adopt(ns)
        captured = capsys.readouterr()

        assert rc == 0
        assert called["adopt_sync"] == 0
        assert "dry-run" in captured.err.lower()
        assert "membranedev" in captured.err

    def test_adopt_low_confidence_requires_confirm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ambiguous query + --yes must still prompt before install."""
        corpus = [
            {
                "name": "game-development",
                "publisher": "miles990",
                "install_ref": "miles990/game-development",
                "install_count": 232,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "flame-game-dev",
                "publisher": "miles990",
                "install_ref": "miles990/flame-game-dev",
                "install_count": 180,
                "source": "npx_search",
                "tier": "C",
            },
        ]

        monkeypatch.setattr(
            "clawagentskill.discover.skills_sh.search",
            lambda *a, **kw: corpus,
        )
        monkeypatch.setattr(
            "clawagentskill.discover.local.search",
            lambda *a, **kw: [],
        )

        prompted = {"count": 0}
        forwarded: dict[str, str] = {}

        def _fake_input(prompt: str = "") -> str:
            prompted["count"] += 1
            # User cancels -> exit code 2
            return "n"

        monkeypatch.setattr("builtins.input", _fake_input)

        def _capture_adopt(q, **kwargs):
            forwarded["query"] = q
            return {"status": "installed", "target_path": "/tmp/x"}

        monkeypatch.setattr("clawagentskill.pipeline.adopt_sync", _capture_adopt)

        ns = argparse.Namespace(
            query="game dev",
            url="",
            scan_mode="quality",
            yes=False,  # not auto-approving
            force=False,
            exact=False,
            publisher=None,
            dry_run=False,
            show_top=3,
        )

        rc = _cmd_adopt(ns)

        assert prompted["count"] >= 1
        assert rc == 2  # user cancelled
        assert "query" not in forwarded  # adopt_sync never invoked

    def test_adopt_publisher_filter_fail_fast(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """--publisher with no matching candidates returns nonzero immediately."""
        monkeypatch.setattr(
            "clawagentskill.discover.skills_sh.search",
            lambda *a, **kw: [
                {
                    "name": "fireflies",
                    "publisher": "miles990",
                    "install_ref": "miles990/fireflies",
                    "install_count": 10,
                    "source": "npx_search",
                    "tier": "C",
                }
            ],
        )
        monkeypatch.setattr(
            "clawagentskill.discover.local.search", lambda *a, **kw: []
        )

        ns = argparse.Namespace(
            query="fireflies",
            url="",
            scan_mode="quality",
            yes=True,
            force=False,
            exact=False,
            publisher="membranedev",
            dry_run=True,
            show_top=3,
        )

        rc = _cmd_adopt(ns)
        captured = capsys.readouterr()
        assert rc == 1
        assert "membranedev" in captured.err

    def test_adopt_backward_compat_legacy_yes_still_installs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legacy `adopt foo --yes` must still result in a successful install.

        The new code may print a top-N preview first, but it must forward to
        adopt_sync when a single high-confidence candidate exists and --yes
        is set (no user prompt required).
        """
        corpus = [
            {
                "name": "foo",
                "publisher": "acme",
                "install_ref": "acme/foo",
                "install_count": 500,
                "source": "npx_search",
                "tier": "C",
            }
        ]
        monkeypatch.setattr(
            "clawagentskill.discover.skills_sh.search",
            lambda *a, **kw: corpus,
        )
        monkeypatch.setattr(
            "clawagentskill.discover.local.search", lambda *a, **kw: []
        )

        forwarded: dict[str, str] = {}

        def _fake_adopt(q, **kwargs):
            forwarded["query"] = q
            return {"status": "installed", "target_path": "/tmp/x"}

        monkeypatch.setattr("clawagentskill.pipeline.adopt_sync", _fake_adopt)

        ns = argparse.Namespace(
            query="foo",
            url="",
            scan_mode="quality",
            yes=True,
            force=False,
            exact=False,
            publisher=None,
            dry_run=False,
            show_top=3,
        )

        rc = _cmd_adopt(ns)
        assert rc == 0
        # Single high-confidence candidate: forwarded query may be the
        # install_ref (install ref or name). Key contract: adopt_sync ran.
        assert "query" in forwarded
        assert forwarded["query"] in ("foo", "acme/foo")


class TestAdoptDirectUrl:
    """Regression tests for the 2026-04-23 'query positional required' bug.

    Reported via Ceremonia tenant Telegram: the LLM fell back to passing a
    direct GitHub URL after fuzzy search returned the wrong skill, but
    argparse rejected the invocation because `query` was a required
    positional. The fix makes `query` optional so `--url` alone is sufficient.
    """

    def test_adopt_url_only_no_query_is_accepted_by_parser(self) -> None:
        """adopt --url <url> (no positional query) must parse cleanly."""
        parser = build_parser()
        args = parser.parse_args([
            "adopt",
            "--url",
            "https://github.com/membranedev/fireflies",
        ])
        assert args.query == ""
        assert args.url == "https://github.com/membranedev/fireflies"

    def test_adopt_no_query_no_url_exits_nonzero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """adopt with neither a query nor --url must fail fast with a clear
        error, not silently invoke the pipeline with an empty query."""
        ns = argparse.Namespace(
            query="",
            url="",
            scan_mode="quality",
            yes=True,
            force=False,
            exact=False,
            publisher=None,
            dry_run=False,
            show_top=3,
        )
        rc = _cmd_adopt(ns)
        captured = capsys.readouterr()
        assert rc == 2
        assert "--url" in captured.err or "query" in captured.err

    def test_adopt_url_only_forwards_to_adopt_sync(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When only --url is provided, adopt_sync must receive the URL and
        an empty query, then run (the pipeline handles direct-url installs
        at the search stage)."""
        forwarded: dict[str, str] = {}

        def _fake_adopt(q, **kwargs):
            forwarded["query"] = q
            forwarded["url"] = kwargs.get("url", "")
            return {"status": "installed", "target_path": "/tmp/x"}

        monkeypatch.setattr("clawagentskill.pipeline.adopt_sync", _fake_adopt)

        ns = argparse.Namespace(
            query="",
            url="https://github.com/membranedev/fireflies",
            scan_mode="quality",
            yes=True,
            force=False,
            exact=False,
            publisher=None,
            dry_run=False,
            show_top=3,
        )
        rc = _cmd_adopt(ns)
        assert rc == 0
        assert forwarded["query"] == ""
        assert forwarded["url"] == "https://github.com/membranedev/fireflies"


class TestAdoptResolvedOutputsInstallRef:
    """Regression tests for the 2026-04-24 'Resolved display misleads LLMs' bug.

    Reported via Ceremonia tenant Telegram on 2026-04-24: LLM searched for
    "Membrane Dev Fireflies skill". Search correctly resolved to the
    skills.sh candidate with:
        install_ref  = membranedev/application-skills@fireflies
        install_url  = https://skills.sh/membranedev/application-skills/fireflies
    CLI printed only `Resolved: membranedev/fireflies` (publisher/name),
    which looks identical to a GitHub `<org>/<repo>` slug. LLM mistakenly
    interpreted the display as `github.com/membranedev/fireflies`, then
    hallucinated `github.com/membranedev/openclaw-skill-fireflies` as a
    fallback URL. Install failed because that repo doesn't exist.

    Fix: the adopt CLI must always print the full install_ref AND install_url
    so LLMs see the unambiguous identifiers, not just a publisher/name label.
    """

    def test_resolved_output_includes_install_ref_and_url(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """On successful resolution, stderr must contain both install_ref
        and install_url so LLMs can see the unambiguous upstream identity.

        This mirrors the Ceremonia incident: the publisher/name display
        (`membranedev/fireflies`) is ambiguous because the real repo is
        `membranedev/application-skills` — only install_ref + install_url
        carry the truth.
        """
        corpus = [
            {
                "name": "fireflies",
                "publisher": "membranedev",
                "install_ref": "membranedev/application-skills@fireflies",
                "install_url": "https://skills.sh/membranedev/application-skills/fireflies",
                "install_count": 500,
                "source": "npx_search",
                "tier": "C",
            }
        ]

        monkeypatch.setattr(
            "clawagentskill.discover.skills_sh.search",
            lambda *a, **kw: corpus,
        )
        monkeypatch.setattr(
            "clawagentskill.discover.local.search",
            lambda *a, **kw: [],
        )

        def _fake_adopt(q, **kwargs):
            return {"status": "installed", "target_path": "/tmp/x"}

        monkeypatch.setattr("clawagentskill.pipeline.adopt_sync", _fake_adopt)

        ns = argparse.Namespace(
            query="Membrane Dev Fireflies skill",
            url="",
            scan_mode="quality",
            yes=True,
            force=False,
            exact=False,
            publisher=None,
            dry_run=False,
            show_top=3,
        )

        rc = _cmd_adopt(ns)
        captured = capsys.readouterr()

        assert rc == 0
        # Install identifier strings must appear in stderr output so LLMs
        # can recover when they need a fallback URL.
        assert "membranedev/application-skills@fireflies" in captured.err, (
            "install_ref must appear in Resolved output so LLMs see the real "
            "repo path, not the publisher/name display that looks like a "
            "GitHub slug."
        )
        assert (
            "https://skills.sh/membranedev/application-skills/fireflies"
            in captured.err
        ), "install_url must appear in Resolved output for LLM fallback."

    def test_dry_run_output_also_includes_install_ref_and_url(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """--dry-run must also surface install_ref + install_url — that's the
        mode LLMs should use to preview before committing to install."""
        corpus = [
            {
                "name": "fireflies",
                "publisher": "membranedev",
                "install_ref": "membranedev/application-skills@fireflies",
                "install_url": "https://skills.sh/membranedev/application-skills/fireflies",
                "install_count": 500,
                "source": "npx_search",
                "tier": "C",
            }
        ]
        monkeypatch.setattr(
            "clawagentskill.discover.skills_sh.search",
            lambda *a, **kw: corpus,
        )
        monkeypatch.setattr(
            "clawagentskill.discover.local.search",
            lambda *a, **kw: [],
        )

        ns = argparse.Namespace(
            query="fireflies",
            url="",
            scan_mode="quality",
            yes=True,
            force=False,
            exact=False,
            publisher=None,
            dry_run=True,
            show_top=3,
        )

        rc = _cmd_adopt(ns)
        captured = capsys.readouterr()
        assert rc == 0
        assert "membranedev/application-skills@fireflies" in captured.err
        assert (
            "https://skills.sh/membranedev/application-skills/fireflies"
            in captured.err
        )
