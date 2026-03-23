"""GitHub API client for agent repository search.

Searches configured agent repositories (VoltAgent, mergisi, etc.) for
matching Claude Code agents by keyword.
"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import Any

import httpx

from clawagentskill.state import slugify


async def _fetch_repo_index(
    client: httpx.AsyncClient,
    repo: str,
    path: str,
) -> list[dict[str, Any]]:
    """Fetch directory listing from GitHub API for a repo path."""
    url = f"https://api.github.com/repos/{repo}/contents/{path.rstrip('/')}"
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
    except (httpx.HTTPError, ValueError):
        pass
    return []


async def _search_registry(
    client: httpx.AsyncClient,
    registry: dict[str, str],
    query: str,
    max_results: int,
) -> list[dict[str, Any]]:
    """Search a single agent registry for matching agents."""
    repo = registry["repo"]
    path = registry.get("path", "")
    agent_type = registry.get("type", "claude-code")

    entries = await _fetch_repo_index(client, repo, path)
    query_lower = query.lower()
    query_slug = slugify(query)

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("type") != "dir":
            # Check file names for .md files
            name = entry.get("name", "")
            if not name.endswith(".md"):
                continue
            name_slug = slugify(PurePosixPath(name).stem)
        else:
            name = entry.get("name", "")
            name_slug = slugify(name)

        if query_lower in name.lower() or query_slug in name_slug:
            download_url = entry.get("download_url") or entry.get("html_url", "")
            # For directories, construct the raw URL pattern
            if entry.get("type") == "dir" and not download_url:
                download_url = f"https://raw.githubusercontent.com/{repo}/main/{path}{name}/{name}.md"

            candidates.append({
                "name": name_slug or name,
                "publisher": repo.split("/")[0],
                "install_ref": download_url,
                "install_count": 0,
                "tier": "C",
                "source": "github",
                "agent_type": agent_type,
                "repo": repo,
            })

        if len(candidates) >= max_results:
            break

    return candidates


async def search_async(
    query: str,
    registries: tuple[dict[str, str], ...],
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search all configured agent registries for matching agents.

    Args:
        query: Search keyword.
        registries: Configured agent registries from Config.
        max_results: Maximum total results.

    Returns:
        List of AgentTemplate candidate dicts.
    """
    async with httpx.AsyncClient(
        headers={"Accept": "application/vnd.github.v3+json"},
    ) as client:
        tasks = [
            _search_registry(client, reg, query, max_results)
            for reg in registries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, list):
            candidates.extend(result)

    return candidates[:max_results]


def search(
    query: str,
    registries: tuple[dict[str, str], ...],
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Sync wrapper around search_async."""
    return asyncio.run(search_async(query, registries, max_results))
