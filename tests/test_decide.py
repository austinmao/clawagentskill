"""Unit tests for the decision modules (tier, trust, rule_c)."""

from __future__ import annotations

import pytest

from clawagentskill.decide.rule_c import apply_rule_c
from clawagentskill.decide.tier import classify_tier, derive_scan_mode
from clawagentskill.decide.trust import compute_trust_score


# ── Tier classification ───────────────────────────────────────────


class TestClassifyTier:
    def test_tier_a_for_openclaw(self):
        """Hardcoded publisher 'openclaw' is always Tier A."""
        assert classify_tier("openclaw", 0) == "A"

    def test_tier_a_for_anthropic(self):
        """Hardcoded publisher 'anthropic' is always Tier A."""
        assert classify_tier("anthropic", 0) == "A"

    def test_tier_a_regardless_of_installs(self):
        """Tier A publishers stay A even with zero installs."""
        assert classify_tier("openclaw", 0) == "A"
        assert classify_tier("anthropic", 999_999) == "A"

    def test_tier_b_high_installs(self):
        """Non-trusted publisher with >= 10000 installs is Tier B."""
        assert classify_tier("random", 15_000) == "B"

    def test_tier_b_exact_threshold(self):
        """Exactly 10000 installs qualifies as Tier B."""
        assert classify_tier("random", 10_000) == "B"

    def test_tier_c_default(self):
        """Non-trusted publisher with low installs is Tier C."""
        assert classify_tier("random", 500) == "C"

    def test_tier_c_zero_installs(self):
        """Zero installs for unknown publisher is Tier C."""
        assert classify_tier("unknown", 0) == "C"

    def test_config_trusted_gets_tier_b(self):
        """Config-trusted (but not hardcoded) publisher gets Tier B."""
        assert classify_tier("acme", 0, config_trusted=("acme",)) == "B"


# ── Scan mode derivation ─────────────────────────────────────────


class TestDeriveScanMode:
    def test_derive_scan_mode_tier_a(self):
        """Tier A always gets 'simplicity' scan mode."""
        assert derive_scan_mode("A", 0) == "simplicity"

    def test_derive_scan_mode_tier_b(self):
        """Tier B gets 'efficiency' scan mode."""
        assert derive_scan_mode("B", 0) == "efficiency"

    def test_derive_scan_mode_tier_c_high_installs(self):
        """Tier C with >= 1000 installs gets 'efficiency'."""
        assert derive_scan_mode("C", 1_000) == "efficiency"

    def test_derive_scan_mode_tier_c_low_installs(self):
        """Tier C with < 1000 installs gets 'quality'."""
        assert derive_scan_mode("C", 500) == "quality"

    def test_derive_scan_mode_override(self):
        """Explicit override takes precedence over tier logic."""
        assert derive_scan_mode("A", 0, override="quality") == "quality"
        assert derive_scan_mode("C", 0, override="simplicity") == "simplicity"

    def test_derive_scan_mode_invalid_override_ignored(self):
        """Invalid override value is silently ignored."""
        assert derive_scan_mode("A", 0, override="bogus") == "simplicity"

    def test_derive_scan_mode_none_override_ignored(self):
        """None override falls through to tier logic."""
        assert derive_scan_mode("B", 500, override=None) == "efficiency"


# ── Trust score ───────────────────────────────────────────────────


class TestComputeTrustScore:
    def test_trust_score_blocked_is_zero(self):
        """Blocked skill always evaluates to 0.0."""
        score = compute_trust_score(
            source_score=1.0,
            scan_score=1.0,
            reviewed=True,
            install_days=365,
            is_blocked=True,
        )
        assert score == 0.0

    def test_trust_score_perfect(self):
        """All max values produce a trust score of 1.0."""
        score = compute_trust_score(
            source_score=1.0,
            scan_score=1.0,
            reviewed=True,
            install_days=30,
        )
        assert score == 1.0

    def test_trust_score_partial(self):
        """Specific inputs produce the expected weighted result.

        source=0.5 * 0.3 = 0.15
        scan=1.0 * 0.3   = 0.30
        reviewed=False    = 0.00
        days=15 / 30 * 0.2 = 0.10
        total             = 0.55
        """
        score = compute_trust_score(
            source_score=0.5,
            scan_score=1.0,
            reviewed=False,
            install_days=15,
        )
        assert score == 0.55

    def test_trust_score_zero_everything(self):
        """All zero inputs produce 0.0."""
        score = compute_trust_score(
            source_score=0.0,
            scan_score=0.0,
            reviewed=False,
            install_days=0,
        )
        assert score == 0.0

    def test_trust_score_negative_days_clamped(self):
        """Negative install_days are clamped to 0."""
        score = compute_trust_score(
            source_score=1.0,
            scan_score=1.0,
            reviewed=True,
            install_days=-5,
        )
        # history component = 0.2 * max(-5, 0) / 30 = 0.0
        # total = 0.3 + 0.3 + 0.2 + 0.0 = 0.8
        assert score == 0.8

    def test_trust_score_above_max_days(self):
        """Days beyond 30 still yield full history credit."""
        score_30 = compute_trust_score(
            source_score=1.0,
            scan_score=1.0,
            reviewed=True,
            install_days=30,
        )
        score_365 = compute_trust_score(
            source_score=1.0,
            scan_score=1.0,
            reviewed=True,
            install_days=365,
        )
        assert score_30 == score_365 == 1.0


# ── Rule C ────────────────────────────────────────────────────────


class TestApplyRuleC:
    """Tests for Rule C decision logic."""

    CLEAN_RESULTS = {
        "prefilter": {"status": "clean"},
        "permission": {"status": "clean"},
        "config": {"status": "clean"},
        "injection": {"status": "clean"},
    }

    WARN_RESULTS = {
        "prefilter": {"status": "clean"},
        "permission": {"status": "warn"},
        "config": {"status": "clean"},
        "injection": {"status": "clean"},
    }

    BLOCKED_RESULTS = {
        "prefilter": {"status": "blocked"},
        "permission": {"status": "clean"},
        "config": {"status": "clean"},
        "injection": {"status": "clean"},
    }

    def test_rule_c_tier_a_installs(self):
        """Tier A -> verdict=install, scanners skipped."""
        decision = apply_rule_c(
            tier="A",
            publisher="openclaw",
            scan_results=self.CLEAN_RESULTS,
            trusted_publishers=("openclaw", "anthropic"),
        )
        assert decision["verdict"] == "install"
        # All scanners should be marked as skipped for Tier A
        for status in decision["scanner_summary"].values():
            assert status == "skipped"

    def test_rule_c_blocked_scanner(self):
        """Any blocked scanner -> verdict=blocked."""
        decision = apply_rule_c(
            tier="C",
            publisher="shady-pub",
            scan_results=self.BLOCKED_RESULTS,
            trusted_publishers=("openclaw", "anthropic"),
        )
        assert decision["verdict"] == "blocked"
        assert decision["rebuild_scope"] is None

    def test_rule_c_warn_untrusted_rebuilds(self):
        """Warn + untrusted publisher -> verdict=rebuild."""
        decision = apply_rule_c(
            tier="C",
            publisher="unknown-pub",
            scan_results=self.WARN_RESULTS,
            trusted_publishers=("openclaw", "anthropic"),
        )
        assert decision["verdict"] == "rebuild"
        assert "permission" in decision["rebuild_scope"]

    def test_rule_c_warn_trusted_installs(self):
        """Warn + trusted publisher -> verdict=install (trusted override)."""
        decision = apply_rule_c(
            tier="B",
            publisher="trusted-pub",
            scan_results=self.WARN_RESULTS,
            trusted_publishers=("openclaw", "anthropic", "trusted-pub"),
        )
        assert decision["verdict"] == "install"
        assert decision["rebuild_scope"] is None

    def test_rule_c_clean_untrusted_rebuilds(self):
        """All clean + untrusted publisher -> verdict=rebuild."""
        decision = apply_rule_c(
            tier="C",
            publisher="untrusted-pub",
            scan_results=self.CLEAN_RESULTS,
            trusted_publishers=("openclaw", "anthropic"),
        )
        assert decision["verdict"] == "rebuild"
        assert decision["rebuild_scope"] == []

    def test_rule_c_clean_trusted_installs(self):
        """All clean + trusted publisher -> verdict=install."""
        decision = apply_rule_c(
            tier="B",
            publisher="trusted-pub",
            scan_results=self.CLEAN_RESULTS,
            trusted_publishers=("openclaw", "anthropic", "trusted-pub"),
        )
        assert decision["verdict"] == "install"
        assert decision["rebuild_scope"] is None

    def test_rule_c_tier_a_overrides_blocked(self):
        """Tier A skips scanners entirely, even if results contain blocked."""
        decision = apply_rule_c(
            tier="A",
            publisher="openclaw",
            scan_results=self.BLOCKED_RESULTS,
            trusted_publishers=("openclaw", "anthropic"),
        )
        assert decision["verdict"] == "install"

    def test_rule_c_scanner_summary_present(self):
        """Decision always includes scanner_summary mapping."""
        decision = apply_rule_c(
            tier="C",
            publisher="test-pub",
            scan_results=self.CLEAN_RESULTS,
            trusted_publishers=(),
        )
        assert "scanner_summary" in decision
        assert set(decision["scanner_summary"].keys()) == set(self.CLEAN_RESULTS.keys())

    def test_rule_c_rationale_present(self):
        """Decision always includes a rationale string."""
        decision = apply_rule_c(
            tier="C",
            publisher="test-pub",
            scan_results=self.CLEAN_RESULTS,
            trusted_publishers=(),
        )
        assert isinstance(decision["rationale"], str)
        assert len(decision["rationale"]) > 0
