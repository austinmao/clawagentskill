"""Candidate ranking for adoption pipeline.

Fixes a bug where local candidates injected with a synthetic `install_count`
of 999_999 would always beat real registry results via naive `candidates[0]`
selection, causing queries like "review contract" to resolve to an existing
local `contract-review` skill instead of the intended registry candidate.
"""

from __future__ import annotations

from typing import Any

from .state import slugify

LOCAL_SENTINEL_INSTALL_COUNT = 999_999
LOCAL_SOURCES = {"local_workspace", "local"}
TIER_RANK = {"A": 3, "B": 2, "C": 1}


def _is_local(candidate: dict[str, Any]) -> bool:
    return candidate.get("source") in LOCAL_SOURCES


def _effective_install_count(candidate: dict[str, Any]) -> int:
    """Demote the synthetic local sentinel so it never beats real counts.

    Local candidates carry `install_count=999_999` as a placeholder — it
    reflects "already installed," not popularity. Treat it as 0 for ranking.
    """
    count = int(candidate.get("install_count", 0) or 0)
    if _is_local(candidate) and count == LOCAL_SENTINEL_INSTALL_COUNT:
        return 0
    return count


def _exact_match(candidate: dict[str, Any], query_slug: str) -> bool:
    return slugify(str(candidate.get("name", ""))) == query_slug


def _rank_key(candidate: dict[str, Any], query_slug: str) -> tuple[int, ...]:
    """Higher tuple wins (Python max on tuple comparison).

    Priority order:
      1. Exact name match to query_slug
      2. Already-installed preference (only when exact match) — two
         candidates with the same exact slug are duplicate representations
         of the same skill; prefer the locally-installed copy.
      3. Effective install count (sentinel demoted so local sentinel does
         not beat real registry counts for non-exact candidates)
      4. Tier rank (A > B > C)
    """
    exact = _exact_match(candidate, query_slug)
    local = _is_local(candidate)
    return (
        1 if exact else 0,
        1 if (exact and local) else 0,
        _effective_install_count(candidate),
        TIER_RANK.get(str(candidate.get("tier", "C")), 0),
    )


def select_best(candidates: list[dict[str, Any]], query: str) -> dict[str, Any]:
    """Return the best-matching candidate for `query`.

    Ranking priorities (see `_rank_key`): exact-slug match, real install
    count, tier, then local-already-installed tiebreak.

    Raises ValueError if `candidates` is empty.
    """
    if not candidates:
        raise ValueError("select_best requires at least one candidate")

    query_slug = slugify(query)
    return max(candidates, key=lambda c: _rank_key(c, query_slug))
