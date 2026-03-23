"""Decision logic for skill adoption — tier classification, trust scoring, and Rule C."""

from __future__ import annotations

from clawagentskill.decide.rule_c import apply_rule_c
from clawagentskill.decide.tier import classify_tier, derive_scan_mode
from clawagentskill.decide.trust import compute_trust_score

__all__ = [
    "apply_rule_c",
    "classify_tier",
    "compute_trust_score",
    "derive_scan_mode",
]
