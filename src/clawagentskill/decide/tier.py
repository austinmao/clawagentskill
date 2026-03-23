"""Tier classification and scan-mode derivation logic.

Publishers are classified into Tier A (hardcoded trusted), Tier B (high
install count), or Tier C (everything else).  Scan mode is derived from
the tier and install count to balance thoroughness against speed.
"""

from __future__ import annotations

from clawagentskill.config import TIER_A_PUBLISHERS

_VALID_TIERS = frozenset({"A", "B", "C"})
_VALID_SCAN_MODES = frozenset({"simplicity", "efficiency", "quality"})
_DEFAULT_TIER_B_THRESHOLD = 10_000
_EFFICIENCY_INSTALL_THRESHOLD = 1_000


def classify_tier(
    publisher: str,
    install_count: int,
    config_trusted: tuple[str, ...] = (),
) -> str:
    """Classify a publisher into Tier A, B, or C.

    Tier A
        Publisher appears in the hardcoded ``TIER_A_PUBLISHERS`` list.
        These are unconditionally trusted.

    Tier B
        ``install_count`` meets or exceeds the default threshold (10 000).
        Config-trusted publishers that are **not** in ``TIER_A_PUBLISHERS``
        still land here and require per-adoption confirmation.

    Tier C
        Everything else.

    Args:
        publisher: Registry publisher handle (e.g. ``"openclaw"``).
        install_count: Cumulative install count from the registry.
        config_trusted: Additional publishers the operator configured as
            trusted.  Publishers in this tuple that are *not* in
            ``TIER_A_PUBLISHERS`` are treated as Tier B, not Tier A.

    Returns:
        One of ``"A"``, ``"B"``, or ``"C"``.
    """
    if publisher in TIER_A_PUBLISHERS:
        return "A"

    if install_count >= _DEFAULT_TIER_B_THRESHOLD:
        return "B"

    # Config-trusted publishers that aren't hardcoded Tier A still get
    # Tier B (not A) — they require per-adoption confirmation.
    if publisher in config_trusted and publisher not in TIER_A_PUBLISHERS:
        return "B"

    return "C"


def derive_scan_mode(
    tier: str,
    install_count: int,
    override: str | None = None,
) -> str:
    """Derive the scan mode from tier and install count.

    The scan mode determines the trade-off between thoroughness and speed
    for security scanners.

    Rules (first match wins):
        1. If *override* is a valid scan mode it takes precedence.
        2. Tier A -> ``"simplicity"`` (trusted, minimal scanning).
        3. Tier B -> ``"efficiency"`` (balanced).
        4. ``install_count >= 1000`` -> ``"efficiency"``.
        5. Otherwise -> ``"quality"`` (full depth).

    Args:
        tier: Result of :func:`classify_tier` (``"A"``, ``"B"``, or ``"C"``).
        install_count: Cumulative install count from the registry.
        override: Optional explicit scan mode.  Must be one of
            ``"simplicity"``, ``"efficiency"``, or ``"quality"`` to be
            accepted; any other value is silently ignored.

    Returns:
        One of ``"simplicity"``, ``"efficiency"``, or ``"quality"``.
    """
    if override is not None and override in _VALID_SCAN_MODES:
        return override

    if tier == "A":
        return "simplicity"

    if tier == "B":
        return "efficiency"

    if install_count >= _EFFICIENCY_INSTALL_THRESHOLD:
        return "efficiency"

    return "quality"
