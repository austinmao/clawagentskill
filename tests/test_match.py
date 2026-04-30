"""Tests for token-aware matching + publisher filtering.

Dedicated test module for the disambiguation layer added in response to
the 2026-04-22 Ceremonia prod incident where `clawagentskill adopt
"fireflies — membranedev"` silently installed miles990/game-development
instead of membranedev/fireflies.
"""

from __future__ import annotations

import pytest

from clawagentskill.select import (
    SelectionResult,
    normalize_query,
    rank_candidates,
    select_best,
    select_with_confidence,
)


@pytest.fixture
def mixed_corpus() -> list[dict]:
    return [
        {
            "name": "fireflies",
            "publisher": "membranedev",
            "install_count": 120,
            "source": "npx_search",
            "tier": "C",
        },
        {
            "name": "fireflies",
            "publisher": "observer-labs",
            "install_count": 3000,
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
    ]


class TestPublisherFilter:
    def test_publisher_filter(self, mixed_corpus: list[dict]) -> None:
        """--publisher filters to a single publisher before ranking."""
        best = select_best(mixed_corpus, "fireflies", publisher="membranedev")
        assert best["publisher"] == "membranedev"
        assert best["name"] == "fireflies"

    def test_publisher_filter_case_insensitive(
        self, mixed_corpus: list[dict]
    ) -> None:
        best = select_best(mixed_corpus, "fireflies", publisher="MembraneDev")
        assert best["publisher"] == "membranedev"

    def test_publisher_filter_excludes_other_publishers(
        self, mixed_corpus: list[dict]
    ) -> None:
        best = select_best(
            mixed_corpus, "fireflies", publisher="observer-labs"
        )
        assert best["publisher"] == "observer-labs"
        assert best["install_count"] == 3000

    def test_publisher_filter_no_match_raises(
        self, mixed_corpus: list[dict]
    ) -> None:
        with pytest.raises(ValueError):
            select_best(mixed_corpus, "fireflies", publisher="bogus-publisher")

    def test_publisher_hint_from_em_dash_query(
        self, mixed_corpus: list[dict]
    ) -> None:
        """Publisher hint inside query string acts like --publisher."""
        best = select_best(mixed_corpus, "fireflies — membranedev")
        assert best["publisher"] == "membranedev"


class TestTokenOverlap:
    def test_all_tokens_present_beats_partial(self) -> None:
        """Candidate with all query tokens beats one with only some."""
        candidates = [
            {
                "name": "send-slack-message",
                "publisher": "community",
                "install_count": 100,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "message-queue",
                "publisher": "popular",
                "install_count": 5000,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        # Full-token match should beat higher-install partial match
        best = select_best(candidates, "send slack message")
        assert best["name"] == "send-slack-message"

    def test_token_splitter_handles_kebab_and_underscore(self) -> None:
        primary, tokens, _ = normalize_query("send_slack-message")
        assert set(tokens) == {"send", "slack", "message"}
        assert primary == "send-slack-message"


class TestRankCandidatesAndConfidence:
    def test_rank_candidates_orders_by_score(
        self, mixed_corpus: list[dict]
    ) -> None:
        ranked = rank_candidates(mixed_corpus, "fireflies")
        # Both fireflies entries tie on exact match; the higher-install one
        # wins the tie-break.
        assert ranked[0]["name"] == "fireflies"
        assert ranked[-1]["name"] == "game-development"

    def test_rank_candidates_applies_publisher_filter(
        self, mixed_corpus: list[dict]
    ) -> None:
        ranked = rank_candidates(
            mixed_corpus, "fireflies", publisher="membranedev"
        )
        assert len(ranked) == 1
        assert ranked[0]["publisher"] == "membranedev"

    def test_selection_result_is_frozen_dataclass(
        self, mixed_corpus: list[dict]
    ) -> None:
        result = select_with_confidence(mixed_corpus, "fireflies")
        assert isinstance(result, SelectionResult)
        with pytest.raises(Exception):
            # frozen dataclass should reject mutation
            result.confidence = "low"  # type: ignore[misc]

    def test_low_confidence_reason_mentions_ambiguity(self) -> None:
        candidates = [
            {
                "name": "foo-bar",
                "publisher": "a",
                "install_count": 10,
                "source": "npx_search",
                "tier": "C",
            },
            {
                "name": "foo-baz",
                "publisher": "b",
                "install_count": 11,
                "source": "npx_search",
                "tier": "C",
            },
        ]
        result = select_with_confidence(candidates, "foo")
        assert result.confidence == "low"
        assert "ambiguous" in result.reason.lower()
