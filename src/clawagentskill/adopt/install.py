"""Skill installation — download to staging, copy to target on success.

Handles direct raw-file downloads plus `npx skills add` staging for marketplace refs.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import httpx


def _looks_like_html(text: str) -> bool:
    """Return True when fetched text appears to be an HTML document."""
    probe = text.lstrip().lower()
    return probe.startswith("<!doctype html") or probe.startswith("<html")


def _parse_skills_sh_ref(install_ref: str) -> tuple[str, str] | None:
    """Translate a skills.sh page URL to the source repo and skill slug.

    Example:
        https://skills.sh/github/awesome-copilot/review-and-refactor
        -> ("github/awesome-copilot", "review-and-refactor")
    """
    parsed = urlparse(install_ref)
    if "skills.sh" not in parsed.netloc:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3:
        return None

    return f"{parts[0]}/{parts[1]}", parts[2]


def _normalize_direct_url(install_ref: str) -> str | None:
    """Normalize repo / dashboard URLs into a bare ``owner/repo`` slug.

    LLMs fall back to pasting direct URLs when fuzzy-search ranks the wrong
    skill. The common shapes they paste are NOT raw SKILL.md URLs — they are
    the GitHub repo landing page or the skills.sh dashboard page. Without
    normalization those URLs fall through to the httpx direct fetch path
    which returns HTML and fails with ``Could not download skill``.

    Supported conversions:
      ``https://github.com/<org>/<repo>``       (strip trailing ``.git``)
      ``https://skills.sh/<org>/<slug>``        (dashboard, 2 path parts)

    Rejected (return None — caller should use an existing path):
      ``github.com/<org>/<repo>/blob/...``      (existing raw-rewrite wins)
      ``github.com/<org>/<repo>/tree/...``      (not a repo root)
      Any URL with 0, 1, or 3+ path segments on github.com
      Non-github.com / non-skills.sh hosts

    Returns ``owner/repo`` (or ``owner/slug``) ready for ``npx skills add``,
    or ``None`` when no normalization applies.
    """
    if not install_ref.startswith("http"):
        return None

    parsed = urlparse(install_ref)
    parts = [part for part in parsed.path.split("/") if part]

    if "github.com" in parsed.netloc and len(parts) == 2:
        org, repo = parts
        if repo.endswith(".git"):
            repo = repo[: -len(".git")]
        if not org or not repo:
            return None
        return f"{org}/{repo}"

    if "skills.sh" in parsed.netloc and len(parts) == 2:
        owner, slug = parts
        if not owner or not slug:
            return None
        return f"{owner}/{slug}"

    return None


def _stage_with_skills_cli(
    source: str,
    staging_path: Path,
    *,
    skill_name: str,
) -> bool:
    """Install a marketplace skill into a throwaway project, then copy it out."""
    with tempfile.TemporaryDirectory(prefix="clawagentskill-") as sandbox:
        sandbox_path = Path(sandbox)
        result = subprocess.run(
            [
                "npx",
                "--yes",
                "skills",
                "add",
                source,
                "--skill",
                skill_name,
                "--yes",
                "--agent",
                "openclaw",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(sandbox_path),
        )
        if result.returncode != 0:
            return False

        installed_path = sandbox_path / "skills" / skill_name / "SKILL.md"
        if not installed_path.exists():
            return False

        staging_path.write_text(installed_path.read_text(encoding="utf-8"), encoding="utf-8")
        return True


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

    # Path 1: skills.sh page URL — https://skills.sh/owner/repo/skill
    skills_sh_ref = _parse_skills_sh_ref(install_ref)
    if skills_sh_ref is not None:
        source, skill_name = skills_sh_ref
        try:
            downloaded = _stage_with_skills_cli(source, staging_path, skill_name=skill_name)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            downloaded = False

    # Path 2: owner/repo@skill format from skills.sh marketplace search results
    # e.g. "claude-office-skills/skills@contract-review"
    if not downloaded and "@" in install_ref and "/" in install_ref and not install_ref.startswith("http"):
        at_idx = install_ref.rfind("@")
        source_repo = install_ref[:at_idx]
        skill_name = install_ref[at_idx + 1:]
        if source_repo and skill_name:
            try:
                downloaded = _stage_with_skills_cli(source_repo, staging_path, skill_name=skill_name)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                downloaded = False

    # Path 3: direct URL download via httpx (raw files, GitHub blobs)
    if not downloaded and install_ref.startswith("http"):
        raw_url = install_ref
        if "github.com" in raw_url and "/blob/" in raw_url:
            raw_url = raw_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        try:
            resp = httpx.get(raw_url, timeout=30, follow_redirects=True)
            if resp.status_code == 200 and not _looks_like_html(resp.text):
                staging_path.write_text(resp.text, encoding="utf-8")
                downloaded = True
        except httpx.HTTPError:
            pass

    # Path 3.5: URL normalization — repo / dashboard URLs that Path 3 can't
    # resolve get translated into bare ``owner/repo`` slugs and passed through
    # the npx install pipeline. Handles the LLM-fallback shapes of
    # ``https://github.com/<org>/<repo>`` and ``https://skills.sh/<org>/<slug>``.
    if not downloaded and install_ref.startswith("http"):
        normalized = _normalize_direct_url(install_ref)
        if normalized:
            try:
                downloaded = _stage_with_skills_cli(
                    normalized, staging_path, skill_name=skill_id
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    # Path 4: bare owner/repo slug (no @skill qualifier) — install all skills from repo
    if not downloaded and "/" in install_ref and not install_ref.startswith("http") and "@" not in install_ref:
        try:
            downloaded = _stage_with_skills_cli(install_ref, staging_path, skill_name=skill_id)
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
