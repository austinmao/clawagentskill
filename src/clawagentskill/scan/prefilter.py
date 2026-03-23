"""ClawHavoc toxic pattern pre-filter.

Checks file content against known ClawHavoc supply-chain indicators.
Any match immediately produces a ``blocked`` verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Patterns sourced from docs/openclaw-ref.yaml  security.clawhavoc_supply_chain
_TOXIC_PATTERNS: tuple[tuple[str, str], ...] = (
    ("91.92.242.30", "ClawHavoc C2 IP address"),
    ("mediafire.com", "Malware distribution host (Mediafire)"),
    ("mega.nz", "Malware distribution host (Mega)"),
    ("clawdhub install", "ClawHub CLI install command"),
    (".clawhub/", "ClawHub origin tracking directory"),
    (".clawdhub/", "ClawHub origin tracking directory (alt)"),
)


def scan_prefilter(path: Path) -> dict[str, Any]:
    """Scan *path* for ClawHavoc toxic indicators.

    Returns a scanner result dict with ``status`` set to ``blocked`` if any
    pattern matches, ``clean`` otherwise.
    """
    scanned_at = datetime.now(timezone.utc).isoformat()
    abs_path = str(path.resolve())

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "scanner": "prefilter",
            "status": "error",
            "skill_path": abs_path,
            "scanned_at": scanned_at,
            "findings": [
                {
                    "code": "read-error",
                    "severity": "blocked",
                    "matched": str(exc),
                    "message": f"Failed to read file: {exc}",
                },
            ],
        }

    content_lower = content.lower()
    findings: list[dict[str, str]] = []

    for pattern, description in _TOXIC_PATTERNS:
        if pattern.lower() in content_lower:
            findings.append(
                {
                    "code": "clawhavoc-indicator",
                    "severity": "blocked",
                    "matched": pattern,
                    "message": description,
                }
            )

    status = "blocked" if findings else "clean"

    return {
        "scanner": "prefilter",
        "status": status,
        "skill_path": abs_path,
        "scanned_at": scanned_at,
        "findings": findings,
    }
