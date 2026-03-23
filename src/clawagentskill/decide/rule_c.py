"""Rule C decision logic for skill adoption.

Rule C evaluates aggregated scanner results against tier and publisher
trust to produce one of three verdicts: ``install``, ``rebuild``, or
``blocked``.
"""

from __future__ import annotations

from typing import Any

from clawagentskill.config import TIER_A_PUBLISHERS


def apply_rule_c(
    tier: str,
    publisher: str,
    scan_results: dict[str, dict[str, Any]],
    trusted_publishers: tuple[str, ...],
) -> dict[str, Any]:
    """Apply Rule C decision logic across scan results.

    Args:
        tier: Publisher tier (``"A"``, ``"B"``, or ``"C"``).
        publisher: Registry publisher handle.
        scan_results: Mapping of scanner name to its result dict.
            Each result dict must contain at least a ``"status"`` key
            with value ``"clean"``, ``"warn"``, or ``"blocked"``.
        trusted_publishers: Tuple of publisher handles the operator has
            marked as trusted (includes hardcoded Tier A publishers).

    Returns:
        A decision dict with keys:

        ``verdict``
            One of ``"install"``, ``"rebuild"``, or ``"blocked"``.
        ``rationale``
            Human-readable explanation of the verdict.
        ``scanner_summary``
            Mapping of scanner name to its status string.
        ``rebuild_scope``
            List of scanner names that triggered a rebuild verdict,
            or *None* when the verdict is not ``"rebuild"``.

    Decision rules (evaluated in order):

    1. **Tier A** -- verdict is ``"install"``; scanners are skipped.
    2. **Any scanner blocked** -- verdict is ``"blocked"``.
    3. **Any scanner warn, publisher NOT trusted** -- verdict is
       ``"rebuild"``; ``rebuild_scope`` lists the warning scanners.
    4. **Any scanner warn, publisher IS trusted** -- verdict is
       ``"install"`` (trusted override).
    5. **All clean, publisher trusted** -- verdict is ``"install"``.
    6. **All clean, publisher NOT trusted** -- verdict is ``"rebuild"``.
    """
    # --- Tier A fast path ---
    if tier == "A":
        return {
            "verdict": "install",
            "rationale": f"Tier A publisher '{publisher}' — scanners skipped",
            "scanner_summary": {name: "skipped" for name in scan_results},
            "rebuild_scope": None,
        }

    # --- Build scanner summary ---
    scanner_summary: dict[str, str] = {}
    blocked_scanners: list[str] = []
    warn_scanners: list[str] = []

    for name, result in scan_results.items():
        status = result.get("status", "unknown")
        scanner_summary[name] = status

        if status == "blocked":
            blocked_scanners.append(name)
        elif status == "warn":
            warn_scanners.append(name)

    # --- Any blocked -> blocked ---
    if blocked_scanners:
        return {
            "verdict": "blocked",
            "rationale": (
                f"Blocked by scanner(s): {', '.join(blocked_scanners)}"
            ),
            "scanner_summary": dict(scanner_summary),
            "rebuild_scope": None,
        }

    is_trusted = publisher in trusted_publishers or publisher in TIER_A_PUBLISHERS

    # --- Warnings present ---
    if warn_scanners:
        if is_trusted:
            return {
                "verdict": "install",
                "rationale": (
                    f"Warning(s) from {', '.join(warn_scanners)} "
                    f"overridden — publisher '{publisher}' is trusted"
                ),
                "scanner_summary": dict(scanner_summary),
                "rebuild_scope": None,
            }
        return {
            "verdict": "rebuild",
            "rationale": (
                f"Warning(s) from {', '.join(warn_scanners)} — "
                f"publisher '{publisher}' is not trusted; rebuild required"
            ),
            "scanner_summary": dict(scanner_summary),
            "rebuild_scope": list(warn_scanners),
        }

    # --- All clean ---
    if is_trusted:
        return {
            "verdict": "install",
            "rationale": (
                f"All scanners clean — publisher '{publisher}' is trusted"
            ),
            "scanner_summary": dict(scanner_summary),
            "rebuild_scope": None,
        }

    return {
        "verdict": "rebuild",
        "rationale": (
            f"All scanners clean but publisher '{publisher}' is not trusted; "
            "rebuild required"
        ),
        "scanner_summary": dict(scanner_summary),
        "rebuild_scope": [],
    }
