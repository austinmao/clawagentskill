"""Skills.sh marketplace search wrapper.

Wraps `npx --yes skills find <query>` to discover available skills.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from clawagentskill.state import slugify


def search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search skills.sh marketplace for matching skills.

    Args:
        query: Natural language search query.
        max_results: Maximum number of results to return.

    Returns:
        List of SkillCandidate dicts with name, publisher, install_ref,
        install_count, tier, source fields.
    """
    candidates: list[dict[str, Any]] = []

    try:
        result = subprocess.run(
            ["npx", "--yes", "skills", "find", query],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return candidates

        # Try JSON parse first
        try:
            raw = json.loads(result.stdout)
            if isinstance(raw, list):
                candidates = raw[:max_results]
            elif isinstance(raw, dict) and "results" in raw:
                candidates = raw["results"][:max_results]
        except json.JSONDecodeError:
            # Plain text output — create stub candidates
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            for line in lines[:max_results]:
                candidates.append({
                    "name": slugify(line),
                    "publisher": "unknown",
                    "install_ref": line,
                    "install_count": 0,
                    "tier": "C",
                    "source": "npx_search",
                })

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return candidates
