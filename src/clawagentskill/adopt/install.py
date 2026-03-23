"""Skill installation — download to staging, copy to target on success.

Handles both `npx skills add` and direct URL download via httpx.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx


def download_to_staging(
    install_ref: str,
    skill_id: str,
    staging_base: Path | None = None,
) -> Path:
    """Download a skill to a staging directory.

    Args:
        install_ref: URL or npm slug to download from.
        skill_id: Skill identifier for staging directory name.
        staging_base: Base staging directory. Defaults to /tmp/skill-staging/.

    Returns:
        Path to the staged SKILL.md file.

    Raises:
        RuntimeError: If download fails.
    """
    base = staging_base or Path("/tmp/skill-staging")
    staging_dir = base / skill_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / "SKILL.md"

    downloaded = False

    # Try direct URL download via httpx
    if install_ref.startswith("http"):
        raw_url = install_ref
        if "github.com" in raw_url and "/blob/" in raw_url:
            raw_url = raw_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        try:
            resp = httpx.get(raw_url, timeout=30, follow_redirects=True)
            if resp.status_code == 200:
                staging_path.write_text(resp.text, encoding="utf-8")
                downloaded = True
        except httpx.HTTPError:
            pass

    # Fallback: npx skills add
    if not downloaded:
        try:
            result = subprocess.run(
                ["npx", "--yes", "skills", "add", install_ref, "--output", str(staging_dir)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            downloaded = result.returncode == 0 and staging_path.exists()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not downloaded:
        msg = f"Could not download skill from '{install_ref}'"
        raise RuntimeError(msg)

    return staging_path


def install_to_workspace(staging_path: Path, target_path: Path) -> Path:
    """Copy a staged skill to the workspace target path.

    Args:
        staging_path: Path to the staged SKILL.md.
        target_path: Destination path in the workspace.

    Returns:
        The target path after successful copy.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(staging_path), str(target_path))
    return target_path


def copy_local(source_path: Path, staging_path: Path) -> Path:
    """Copy a local workspace skill to the staging directory.

    Args:
        source_path: Path to the local SKILL.md.
        staging_path: Destination staging path.

    Returns:
        The staging path after copy.
    """
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_path), str(staging_path))
    return staging_path


def cleanup_staging(skill_id: str, staging_base: Path | None = None) -> None:
    """Remove the staging directory for a skill."""
    base = staging_base or Path("/tmp/skill-staging")
    staging_dir = base / skill_id
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
