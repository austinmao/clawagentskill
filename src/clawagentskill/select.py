"""Candidate ranking for adoption pipeline.

Fixes two related bugs:

1. Local candidates injected with a synthetic `install_count` of 999_999
   would always beat real registry results via naive `candidates[0]`
   selection, causing queries like "review contract" to resolve to an
   existing local `contract-review` skill instead of the intended
   registry candidate.

2. Popularity-weighted ranking caused multi-word queries with publisher
   intent (e.g. "fireflies — membranedev") to silently adopt the wrong
   skill. Introduces token-aware match scoring, optional publisher
   filtering, strict `exact` mode, and a confidence signal so callers
   can prompt for confirmation on low-confidence matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .state import slugify

LOCAL_SENTINEL_INSTALL_COUNT = 999_999
LOCAL_SOURCES = {"local_workspace", "local"}
TIER_RANK = {"A": 3, "B": 2, "C": 1}

# Unicode separators that indicate "skill — publisher" style human queries
# (em-dash, en-dash, vertical bar). Forward-slash uses the opposite
# convention (publisher/skill) and is handled separately.
_QUERY_SEPARATORS = re.compile(r"[—–|]+")

# Forward-slash form: left = publisher, right = skill name. Install refs
# like "openclaw/resend" follow this convention.
_SLASH_RE = re.compile(r"\s*/\s*")

# Used to split normalized query into individual tokens for overlap scoring.
_TOKEN_SPLIT = re.compile(r"[\s_\-]+")

# Confidence margin: rank-1 must beat rank-2 by this fraction of its own
# score to be considered "high confidence" for auto-install.
_CONFIDENCE_MARGIN = 0.5


@dataclass(frozen=True)
class SelectionResult:
    """Result of candidate selection with confidence signal.

    Attributes:
        candidate: The selected candidate dict.
        confidence: "high" | "low" — callers should prompt on "low".
        reason: Human-readable explanation of why this was chosen.
    """

    candidate: dict[str, Any]
    confidence: str
    reason: str


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


def normalize_query(query: str) -> tuple[str, list[str], str | None]:
    """Split a query and extract an optional publisher hint.

    Two forms are recognized:
      - "skill — publisher" (em-dash / en-dash / pipe): skill first.
      - "publisher/skill"    (forward slash):           publisher first.

    Examples:
        "fireflies"                 -> ("fireflies", ["fireflies"], None)
        "fireflies — membranedev"   -> ("fireflies", ["fireflies"], "membranedev")
        "membranedev/fireflies"     -> ("fireflies", ["fireflies"], "membranedev")
        "openclaw/resend"           -> ("resend",   ["resend"],    "openclaw")
        "review contract"           -> ("review-contract",
                                        ["review", "contract"], None)

    Returns:
        Tuple of (primary_slug, tokens, publisher_hint). `primary_slug` is
        always the skill-name side. `publisher_hint` is lowercased.
    """
    if not query:
        return ("", [], None)

    stripped = query.strip()
    publisher_hint: str | None = None
    primary: str = stripped

    # Slash form wins (left=publisher, right=skill) because it is
    # unambiguous in our install refs.
    if "/" in stripped:
        slash_parts = [p.strip() for p in _SLASH_RE.split(stripped) if p.strip()]
        if len(slash_parts) >= 2:
            publisher_hint = slash_parts[0].lower()
            primary = slash_parts[1]
    else:
        dash_parts = [
            p.strip() for p in _QUERY_SEPARATORS.split(stripped) if p.strip()
        ]
        if len(dash_parts) >= 2:
            primary = dash_parts[0]
            publisher_hint = dash_parts[1].lower()
        elif dash_parts:
            primary = dash_parts[0]

    primary_slug = slugify(primary)
    tokens = [t for t in _TOKEN_SPLIT.split(primary_slug) if t]

    return (primary_slug, tokens, publisher_hint)


def _token_overlap_score(candidate: dict[str, Any], tokens: list[str]) -> float:
    """Fraction of query tokens present in the candidate's slugified name."""
    if not tokens:
        return 0.0
    name_slug = slugify(str(candidate.get("name", "")))
    name_tokens = set(t for t in _TOKEN_SPLIT.split(name_slug) if t)
    if not name_tokens:
        return 0.0
    matched = sum(1 for t in tokens if t in name_tokens)
    return matched / len(tokens)


def _publisher_matches(candidate: dict[str, Any], publisher: str) -> bool:
    """Case-insensitive check that the candidate's publisher matches."""
    return str(candidate.get("publisher", "")).lower() == publisher.lower()


def _rank_key(
    candidate: dict[str, Any],
    query_slug: str,
    tokens: list[str],
    publisher_hint: str | None,
) -> tuple[float, ...]:
    """Higher tuple wins (Python max on tuple comparison).

    Priority order:
      1. Exact name match to query_slug (massive boost)
      2. Publisher-hint match (when query contained "skill — publisher")
      3. Token overlap fraction (all tokens present > some tokens > none)
      4. Already-installed preference (only when exact match)
      5. Effective install count (sentinel demoted)
      6. Tier rank (A > B > C)
    """
    exact = _exact_match(candidate, query_slug)
    local = _is_local(candidate)
    publisher_match = bool(
        publisher_hint and _publisher_matches(candidate, publisher_hint)
    )
    overlap = _token_overlap_score(candidate, tokens)

    return (
        1000.0 if exact else 0.0,
        100.0 if publisher_match else 0.0,
        overlap * 10.0,
        1.0 if (exact and local) else 0.0,
        float(_effective_install_count(candidate)),
        float(TIER_RANK.get(str(candidate.get("tier", "C")), 0)),
    )


def _score_total(key: tuple[float, ...]) -> float:
    return sum(key)


def select_best(
    candidates: list[dict[str, Any]],
    query: str,
    *,
    exact: bool = False,
    publisher: str | None = None,
) -> dict[str, Any]:
    """Return the best-matching candidate for `query`.

    Backward-compatible wrapper around `select_with_confidence` that returns
    only the candidate dict. Raises ValueError on empty input or when
    `exact=True` / `publisher` filter eliminates all candidates.

    Args:
        candidates: List of candidate dicts.
        query: Search query; may contain unicode separators and a
            "skill — publisher" publisher hint.
        exact: If True, only exact slug matches are allowed.
        publisher: If provided, filter candidates to this publisher.

    Returns:
        The best-matching candidate dict.
    """
    result = select_with_confidence(
        candidates, query, exact=exact, publisher=publisher
    )
    return result.candidate


def select_with_confidence(
    candidates: list[dict[str, Any]],
    query: str,
    *,
    exact: bool = False,
    publisher: str | None = None,
) -> SelectionResult:
    """Rank candidates and return the winner with a confidence signal.

    See `select_best` for filter semantics. The returned `confidence` is
    "high" when:
      - there is exactly one candidate after filtering, OR
      - the top candidate is an exact slug match, OR
      - the top candidate beats rank-2 by >= 50% of its score.
    Otherwise "low" — callers should prompt for confirmation.

    Raises:
        ValueError: if `candidates` is empty or filtering removes everything.
    """
    if not candidates:
        raise ValueError("select_best requires at least one candidate")

    primary_slug, tokens, publisher_hint = normalize_query(query)

    # Publisher param (explicit CLI flag) overrides hint from query text.
    effective_publisher = publisher if publisher else publisher_hint

    filtered = list(candidates)
    if effective_publisher:
        filtered = [c for c in filtered if _publisher_matches(c, effective_publisher)]
        if not filtered:
            raise ValueError(
                f"No candidates match publisher={effective_publisher!r}"
            )

    if exact:
        filtered = [c for c in filtered if _exact_match(c, primary_slug)]
        if not filtered:
            raise ValueError(
                f"No candidates exactly match name={primary_slug!r}"
            )

    scored = [
        (c, _rank_key(c, primary_slug, tokens, publisher_hint)) for c in filtered
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    top_candidate, top_key = scored[0]
    exact_top = _exact_match(top_candidate, primary_slug)

    # Determine confidence and reason.
    if len(scored) == 1:
        confidence = "high"
        reason = "only candidate after filtering"
    elif exact_top:
        confidence = "high"
        reason = f"exact name match to {primary_slug!r}"
    else:
        top_score = _score_total(top_key)
        runner_score = _score_total(scored[1][1])
        margin = top_score - runner_score
        if top_score > 0 and margin >= top_score * _CONFIDENCE_MARGIN:
            confidence = "high"
            reason = f"top result beats rank-2 by {margin:.1f} points"
        else:
            confidence = "low"
            reason = (
                "ambiguous: top result does not clearly outrank alternatives"
            )

    return SelectionResult(
        candidate=top_candidate, confidence=confidence, reason=reason
    )


def rank_candidates(
    candidates: list[dict[str, Any]],
    query: str,
    *,
    publisher: str | None = None,
) -> list[dict[str, Any]]:
    """Return candidates sorted by rank (best first). Does not filter.

    Useful for `--show-top N` previews where we want to display the full
    ordering without failing on missing matches.
    """
    if not candidates:
        return []

    primary_slug, tokens, publisher_hint = normalize_query(query)
    effective_publisher = publisher if publisher else publisher_hint

    pool = list(candidates)
    if effective_publisher:
        pool = [c for c in pool if _publisher_matches(c, effective_publisher)]

    return sorted(
        pool,
        key=lambda c: _rank_key(c, primary_slug, tokens, publisher_hint),
        reverse=True,
    )
