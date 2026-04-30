"""Tests for install-target path resolution in the adoption pipeline.

Regression guard for Ceremonia prod bug (2026-04-22): direct `clawagentskill adopt`
CLI ran inside the gateway container installed to `/app/skills/...` (ephemeral
image FS, wiped on `docker compose up -d`) instead of the bind-mounted
`/home/node/.openclaw/skills/...` workspace.

Resolution order for target-dir base:
  1. Explicit `target_root` kwarg
  2. Explicit `workspace_root` kwarg (back-compat)
  3. `$OPENCLAW_WORKSPACE` env var
  4. `$HOME/.openclaw` fallback
  5. `Path.cwd()` absolute last resort
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clawagentskill.pipeline import _resolve_install_base


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear both env vars so tests start from a known state."""
    monkeypatch.delenv("OPENCLAW_WORKSPACE", raising=False)
    monkeypatch.delenv("HOME", raising=False)


class TestResolveInstallBase:
    """Unit tests for _resolve_install_base resolution order."""

    def test_openclaw_workspace_env_wins_over_fallbacks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """When OPENCLAW_WORKSPACE is set, it drives the install base."""
        workspace = tmp_path / "testwsp"
        workspace.mkdir()
        monkeypatch.setenv("OPENCLAW_WORKSPACE", str(workspace))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        base = _resolve_install_base(target_root=None, workspace_root=None)

        assert base == workspace

    def test_explicit_target_root_overrides_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Explicit target_root kwarg beats OPENCLAW_WORKSPACE."""
        monkeypatch.setenv("OPENCLAW_WORKSPACE", str(tmp_path / "env_wsp"))
        explicit = tmp_path / "explicit"
        explicit.mkdir()

        base = _resolve_install_base(target_root=explicit, workspace_root=None)

        assert base == explicit

    def test_explicit_workspace_root_overrides_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Explicit workspace_root kwarg beats OPENCLAW_WORKSPACE (back-compat)."""
        monkeypatch.setenv("OPENCLAW_WORKSPACE", str(tmp_path / "env_wsp"))
        ws = tmp_path / "ws_kwarg"
        ws.mkdir()

        base = _resolve_install_base(target_root=None, workspace_root=ws)

        assert base == ws

    def test_home_fallback_when_env_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Without OPENCLAW_WORKSPACE, fall back to $HOME/.openclaw."""
        monkeypatch.delenv("OPENCLAW_WORKSPACE", raising=False)
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))

        base = _resolve_install_base(target_root=None, workspace_root=None)

        assert base == home / ".openclaw"

    def test_never_returns_app_without_explicit_opt_in(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Regression: container default cwd=/app must not leak into target path."""
        monkeypatch.setenv("OPENCLAW_WORKSPACE", str(tmp_path / "wsp"))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.chdir(tmp_path)  # simulate non-/app cwd for safety

        base = _resolve_install_base(target_root=None, workspace_root=None)

        assert "/app/skills" not in str(base)
        assert str(base) != "/app"


class TestPipelineTargetPathFromEnv:
    """Integration-lite: verify run_adopt anchors target_path on install_base.

    Stubs out the search + select + download stages (owned by other agents)
    and asserts only that the target_path derivation stage uses the
    OPENCLAW_WORKSPACE-derived install_base rather than cwd.

    Regression test for Ceremonia prod bug — production scenario:
    ``docker exec`` enters /app as cwd but the real skills dir lives at
    $OPENCLAW_WORKSPACE (bind-mounted volume).
    """

    @pytest.mark.asyncio
    async def test_target_path_anchored_on_openclaw_workspace(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """target_path in meta.yaml must land under $OPENCLAW_WORKSPACE/skills."""
        from clawagentskill import pipeline as pipeline_mod

        workspace = tmp_path / "testwsp"
        workspace.mkdir()
        monkeypatch.setenv("OPENCLAW_WORKSPACE", str(workspace))

        captured: dict[str, str] = {}

        # Stub select_best to return a deterministic candidate, bypassing the
        # in-flight select.py changes owned by another agent.
        def fake_select_best(
            candidates: list[dict[str, Any]],
            query: str,
        ) -> dict[str, Any]:
            return {
                "name": "fireflies",
                "publisher": "openclaw",
                "install_ref": "https://example.invalid/fireflies",
                "install_count": 100,
                "tier": "B",
                "source": "registry",
            }

        monkeypatch.setattr(pipeline_mod, "select_best", fake_select_best)

        # Stub download so we fail fast after target_path is written to meta.
        def fake_download_to_staging(*args: Any, **kwargs: Any) -> Path:
            raise RuntimeError("stubbed-download-abort")

        monkeypatch.setattr(
            pipeline_mod, "download_to_staging", fake_download_to_staging
        )

        # Feed a fake candidate so search() stage passes.
        def fake_sh_search(query: str) -> list[dict[str, Any]]:
            return [{
                "name": "fireflies",
                "publisher": "openclaw",
                "install_ref": "https://example.invalid/fireflies",
                "install_count": 100,
                "tier": "B",
                "source": "registry",
            }]

        monkeypatch.setattr(pipeline_mod.skills_sh, "search", fake_sh_search)

        # Spy on save_meta to capture the target_path the pipeline derives.
        original_save_meta = pipeline_mod.StateManager.save_meta

        def spy_save_meta(
            self: pipeline_mod.StateManager,
            meta: dict[str, Any],
        ) -> None:
            tp = meta.get("target_path", "")
            if tp:
                captured["target"] = tp
            original_save_meta(self, meta)

        monkeypatch.setattr(
            pipeline_mod.StateManager, "save_meta", spy_save_meta
        )

        result = await pipeline_mod.run_adopt(
            "fireflies",
            auto_approve=True,
            force=True,
            workspace_root=workspace,
        )

        # Expect graceful error at download stage (our stub raised).
        assert result["status"] == "error", result
        assert result["stage"] == "download", result

        target = captured.get("target", "")
        assert target, "target_path was never written to meta.yaml"
        assert "/app/skills" not in target, (
            f"target_path leaked ephemeral /app FS: {target}"
        )
        assert str(workspace) in target, (
            f"target_path not under OPENCLAW_WORKSPACE={workspace}: {target}"
        )
        assert target.endswith("SKILL.md")
