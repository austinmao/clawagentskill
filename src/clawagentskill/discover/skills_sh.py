"""Skills.sh marketplace search wrapper.

Wraps `npx --yes skills find <query>` to discover available skills.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from clawagentskill.state import slugify

# Strip ANSI escape codes (e.g. \x1b[38;5;250m ... \x1b[0m)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

# Split queries on unicode publisher separators so we search by the
# skill name alone (e.g. "fireflies — membranedev" -> "fireflies").
# The publisher portion is preserved for downstream filtering via
# `select.normalize_query`.
_QUERY_SEPARATORS = re.compile(r"[—–|/]+")

# Match a skills.sh entry line: owner/repo@skill-name  785 installs
#   or: owner/repo@skill name with spaces  4.4K installs
_ENTRY_RE = re.compile(r"^(\S+/\S+@\S.*?)\s+([\d.]+[Kk]?)\s+install", re.IGNORECASE)

# Match install URL line: └ https://skills.sh/...
_URL_RE = re.compile(r"└\s*(https?://\S+)")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _parse_installs(count_str: str) -> int:
    """Parse install count like '785', '4.4K', '1.2k' into an integer."""
    s = count_str.strip().upper()
    if s.endswith("K"):
        try:
            return int(float(s[:-1]) * 1000)
        except ValueError:
            return 0
    try:
        return int(s)
    except ValueError:
        return 0


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

    # Normalize the query so publisher hints (e.g. "fireflies — membranedev")
    # don't pollute the remote search — skills.sh has no concept of
    # "skill — publisher" syntax and pollution produces no results or
    # fuzzy-popularity-ranked garbage.
    search_query = _QUERY_SEPARATORS.split(query)[0].strip() if query else query
    if not search_query:
        search_query = query

    try:
        result = subprocess.run(
            ["npx", "--yes", "skills", "find", search_query],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return candidates

        # Try JSON parse first (in case the CLI ever adds --json support)
        try:
            raw = json.loads(result.stdout)
            if isinstance(raw, list):
                candidates = raw[:max_results]
            elif isinstance(raw, dict) and "results" in raw:
                candidates = raw["results"][:max_results]
            return candidates
        except json.JSONDecodeError:
            pass

        # Plain text output with ANSI codes — parse the structured format.
        # The skills CLI always emits ANSI color codes even when piped.
        # Format per entry (after stripping ANSI):
        #   owner/repo@skill-name  785 installs
        #   └ https://skills.sh/owner/repo/skill-name
        clean_lines = [_strip_ansi(line).strip() for line in result.stdout.splitlines()]
        i = 0
        while i < len(clean_lines) and len(candidates) < max_results:
            line = clean_lines[i]
            m = _ENTRY_RE.match(line)
            if m:
                install_ref = m.group(1).strip()
                install_count = _parse_installs(m.group(2))
                # name is the part after the last '@'
                name = install_ref.rsplit("@", 1)[-1] if "@" in install_ref else install_ref
                publisher = install_ref.split("/")[0] if "/" in install_ref else "unknown"
                # Look for URL on next non-empty line
                install_url = ""
                j = i + 1
                while j < len(clean_lines) and not clean_lines[j]:
                    j += 1
                if j < len(clean_lines):
                    url_m = _URL_RE.search(clean_lines[j])
                    if url_m:
                        install_url = url_m.group(1)
                candidates.append({
                    "name": slugify(name),
                    "publisher": publisher,
                    "install_ref": install_ref,
                    "install_count": install_count,
                    "install_url": install_url,
                    "tier": "C",
                    "source": "npx_search",
                })
            i += 1

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return candidates
