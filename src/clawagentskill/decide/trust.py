"""Trust-score computation for skill adoption decisions.

The trust score is a weighted composite of four factors that captures how
much confidence the operator should place in a skill before adoption.

Formula::

    trust = source(0.3) + scan(0.3) + reviewed(0.2) + history(0.2)

Blocked skills always evaluate to 0.0 regardless of other inputs.
"""

from __future__ import annotations

_WEIGHT_SOURCE = 0.3
_WEIGHT_SCAN = 0.3
_WEIGHT_REVIEWED = 0.2
_WEIGHT_HISTORY = 0.2
_HISTORY_FULL_DAYS = 30


def compute_trust_score(
    source_score: float,
    scan_score: float,
    reviewed: bool,
    install_days: int,
    is_blocked: bool = False,
) -> float:
    """Compute a trust score in the range ``[0.0, 1.0]``.

    Args:
        source_score: Origin quality factor (``0.0``--``1.0``).
            Typical values: ``local=1.0``, ``tier_a=1.0``,
            ``marketplace=0.5``, ``unknown=0.0``.
        scan_score: Security scan result factor (``0.0``--``1.0``).
            Typical values: ``clean=1.0``, ``warn=0.5``, ``blocked=0.0``.
        reviewed: Whether the operator has explicitly reviewed the skill.
            Contributes ``0.2`` when *True*, ``0.0`` when *False*.
        install_days: Number of days since the skill was first installed.
            Full credit (``0.2``) at 30+ days; proportional below that.
        is_blocked: If *True* the skill is unconditionally blocked and
            the return value is always ``0.0``.

    Returns:
        Trust score clamped to ``[0.0, 1.0]``.
    """
    if is_blocked:
        return 0.0

    source_component = _clamp(source_score) * _WEIGHT_SOURCE
    scan_component = _clamp(scan_score) * _WEIGHT_SCAN
    reviewed_component = _WEIGHT_REVIEWED if reviewed else 0.0

    if install_days >= _HISTORY_FULL_DAYS:
        history_component = _WEIGHT_HISTORY
    else:
        history_component = _WEIGHT_HISTORY * max(install_days, 0) / _HISTORY_FULL_DAYS

    total = source_component + scan_component + reviewed_component + history_component
    return round(_clamp(total), 4)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to the ``[lo, hi]`` interval."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
