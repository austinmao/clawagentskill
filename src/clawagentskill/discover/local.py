"""Local workspace skill and agent search.

Scans the local `skills/` and `agents/` directories for matching entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawagentskill.state import slugify


def search(
    query: str,
    workspace_root: Path,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search local workspace for skills and agents matching the query.

    Args:
        query: Search query (matched against SKILL.md name and directory names).
        workspace_root: Root directory of the workspace.
        max_results: Maximum results to return.

    Returns:
        List of SkillCandidate dicts for local matches.
    """
    candidates: list[dict[str, Any]] = []
    query_lower = query.lower().strip()
    query_slug = slugify(query)

    # Handle "publisher/name" format for Tier A resolution
    if "/" in query:
        parts = query.split("/", 1)
        publisher = parts[0].strip().lower()
        name_part = parts[1].strip().lower()
        name_slug = slugify(name_part)
    else:
        publisher = ""
        name_part = query_lower
        name_slug = query_slug

    # Search skills/ directory
    skills_dir = workspace_root / "skills"
    if skills_dir.exists():
        for skill_md in skills_dir.rglob("SKILL.md"):
            skill_name = skill_md.parent.name
            # Match against directory name
            if name_slug in skill_name or name_part in skill_name:
                candidates.append({
                    "name": skill_name,
                    "publisher": publisher or "local",
                    "install_ref": str(skill_md.parent),
                    "install_count": 999_999,
                    "tier": "A" if publisher else "C",
                    "source": "local_workspace",
                    "target_path": str(skill_md),
                })

    # Search agents/ directory
    agents_dir = workspace_root / "agents"
    if agents_dir.exists():
        for soul_md in agents_dir.rglob("SOUL.md"):
            agent_name = soul_md.parent.name
            if name_slug in agent_name or name_part in agent_name:
                candidates.append({
                    "name": agent_name,
                    "publisher": publisher or "local",
                    "install_ref": str(soul_md.parent),
                    "install_count": 999_999,
                    "tier": "A" if publisher else "C",
                    "source": "local_workspace",
                    "target_path": str(soul_md),
                })

    return candidates[:max_results]
