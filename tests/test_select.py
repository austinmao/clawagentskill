"""Tests for candidate ranking logic (select_best).

Failing-first (TDD RED) tests that prove the ranking bug where local
candidates with synthetic 999_999 install counts incorrectly beat real
registry candidates via `candidates[0]` naive selection.

Also covers the fuzzy-rank fix: popularity-weighted ranking caused
multi-word queries with publisher intent ("fireflies — membranedev")
to silently adopt the wrong skill.
"""

from __future__ import annotations

import pytest
from clawagentskill.select import (
    normalize_query,
    rank_candidates,
    select_best,
    select_with_confidence,
)


class TestSelectBestCandidate:
    """Ranking priorities (highest wins):
    1. Exact name match to query_slug
    2. Real install_count (synthetic 999_999 sentinel is demoted)
    3. Local source wins as tiebreak only when names are equal
    """

    def test_registry_exact_match_beats_local_fuzzy_sentinel(self) -> None:
        """Registry candidate whose name exactly matches query beats
        local candidate whose name only fuzzy-matches, even with sentinel."""
        candidates = [
            {
                "name": "contract-review",
                "publisher": "local",
                "install_count": 999_999,
                "source": "local_workspace",
                "tier": "C",
            },
            {
                "name": "review-contract",
                "publisher": "anthropics",
                "install_count": 780,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        best = select_best(candidates, "review-contract")
        assert best["name"] == "review-contract"
        assert best["source"] == "npx_search"

    def test_local_sentinel_does_not_outrank_real_install_count(self) -> None:
        """Synthetic 999_999 sentinel must be demoted; real install count wins
        when neither candidate is an exact match."""
        candidates = [
            {
                "name": "foo-bar",
                "publisher": "local",
                "install_count": 999_999,
                "source": "local_workspace",
                "tier": "C",
            },
            {
                "name": "foo-baz",
                "publisher": "acme",
                "install_count": 5000,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        best = select_best(candidates, "foo")
        assert best["name"] == "foo-baz"
        assert best["source"] == "npx_search"

    def test_query_slug_normalization_picks_exact_registry(self) -> None:
        """Query with spaces slugifies to kebab-case. Registry candidate with
        exact slug match wins over local fuzzy-match."""
        candidates = [
            {
                "name": "contract-review",
                "publisher": "local",
                "install_count": 999_999,
                "source": "local_workspace",
                "tier": "C",
            },
            {
                "name": "review-contract",
                "publisher": "anthropics",
                "install_count": 780,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        best = select_best(candidates, "review contract")
        assert best["name"] == "review-contract"

    def test_local_wins_only_when_equal_exact_match(self) -> None:
        """When local and registry candidates both match the query exactly
        by name, local wins as tiebreak (already-installed preference)."""
        candidates = [
            {
                "name": "payments",
                "publisher": "local",
                "install_count": 999_999,
                "source": "local_workspace",
                "tier": "A",
            },
            {
                "name": "payments",
                "publisher": "stripe",
                "install_count": 500,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        best = select_best(candidates, "payments")
        assert best["source"] == "local_workspace"

    def test_real_install_count_orders_registry_candidates(self) -> None:
        """Among registry candidates with no exact match, higher install
        count wins."""
        candidates = [
            {
                "name": "email-sender",
                "publisher": "foo",
                "install_count": 100,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "email-dispatch",
                "publisher": "bar",
                "install_count": 2500,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        best = select_best(candidates, "email")
        assert best["name"] == "email-dispatch"

    def test_empty_candidates_raises(self) -> None:
        """Empty candidate list is a programming error."""
        with pytest.raises(ValueError):
            select_best([], "anything")

    def test_single_candidate_returned_as_is(self) -> None:
        """One candidate is trivially the best."""
        candidates = [
            {
                "name": "only-one",
                "publisher": "acme",
                "install_count": 42,
                "source": "npx_search",
                "tier": "C",
            }
        ]
        best = select_best(candidates, "only-one")
        assert best["name"] == "only-one"

    def test_tier_a_breaks_tie_when_exact_match_and_counts_equal(self) -> None:
        """If two non-local candidates both exactly match the query and have
        the same install count, tier A (trusted official) wins over tier C."""
        candidates = [
            {
                "name": "auth",
                "publisher": "community",
                "install_count": 1000,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "auth",
                "publisher": "anthropics",
                "install_count": 1000,
                "source": "npx_search",
                "tier": "A",
            },
        ]
        best = select_best(candidates, "auth")
        assert best["tier"] == "A"
        assert best["publisher"] == "anthropics"


class TestFireflyFuzzyRankFix:
    """Tests for the 2026-04-22 disambiguation bug (fireflies/membranedev)."""

    def _fireflies_corpus(self) -> list[dict]:
        return [
            {
                "name": "fireflies",
                "publisher": "membranedev",
                "install_count": 120,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "game-development",
                "publisher": "miles990",
                "install_count": 232,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "flame-game-dev",
                "publisher": "miles990",
                "install_count": 180,
                "source": "npx_search",
                "tier": "C",
            },
        ]

    def test_exact_match_wins_over_popularity(self) -> None:
        """Query 'fireflies' must pick membranedev/fireflies over the
        more-popular game-development skill."""
        best = select_best(self._fireflies_corpus(), "fireflies")
        assert best["name"] == "fireflies"
        assert best["publisher"] == "membranedev"

    def test_em_dash_query_normalization(self) -> None:
        """'fireflies — membranedev' must parse to primary='fireflies'
        with publisher_hint='membranedev'."""
        primary, tokens, publisher = normalize_query("fireflies — membranedev")
        assert primary == "fireflies"
        assert tokens == ["fireflies"]
        assert publisher == "membranedev"

    def test_en_dash_and_pipe_and_slash_all_split(self) -> None:
        for q in [
            "fireflies – membranedev",
            "fireflies | membranedev",
            "membranedev/fireflies",
        ]:
            primary, _, publisher = normalize_query(q)
            # slash form has the publisher first; either order should end
            # up producing "fireflies" + "membranedev" tokens
            assert "fireflies" in (primary, publisher or "")
            assert "membranedev" in (primary, publisher or "")

    def test_publisher_hint_overrides_popularity(self) -> None:
        """'fireflies — membranedev' must resolve to membranedev/fireflies
        even though miles990 variants have higher install counts."""
        best = select_best(self._fireflies_corpus(), "fireflies — membranedev")
        assert best["name"] == "fireflies"
        assert best["publisher"] == "membranedev"

    def test_exact_mode_filters_strictly(self) -> None:
        """--exact equivalent: only exact slug matches survive."""
        candidates = [
            {
                "name": "contract-review",
                "publisher": "local",
                "install_count": 999_999,
                "source": "local_workspace",
                "tier": "C",
            },
            {
                "name": "review-contract",
                "publisher": "anthropics",
                "install_count": 780,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        best = select_best(candidates, "review-contract", exact=True)
        assert best["name"] == "review-contract"

        with pytest.raises(ValueError):
            select_best(candidates, "nonexistent", exact=True)

    def test_publisher_arg_filters_candidates(self) -> None:
        """Explicit publisher= filters before ranking."""
        best = select_best(
            self._fireflies_corpus(), "fireflies", publisher="membranedev"
        )
        assert best["publisher"] == "membranedev"

        with pytest.raises(ValueError):
            select_best(self._fireflies_corpus(), "fireflies", publisher="nobody")

    def test_confidence_high_on_exact_match(self) -> None:
        result = select_with_confidence(self._fireflies_corpus(), "fireflies")
        assert result.confidence == "high"
        assert result.candidate["publisher"] == "membranedev"

    def test_confidence_low_on_ambiguous_multi_token(self) -> None:
        """Ambiguous fuzzy query with no exact match and close scores =>
        low confidence (caller should prompt)."""
        candidates = [
            {
                "name": "game-development",
                "publisher": "miles990",
                "install_count": 232,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "flame-game-dev",
                "publisher": "miles990",
                "install_count": 180,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        result = select_with_confidence(candidates, "game dev")
        assert result.confidence == "low"

    def test_rank_candidates_returns_full_ordering(self) -> None:
        ranked = rank_candidates(self._fireflies_corpus(), "fireflies")
        assert len(ranked) == 3
        assert ranked[0]["name"] == "fireflies"
        assert ranked[0]["publisher"] == "membranedev"
