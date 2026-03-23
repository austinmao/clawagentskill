"""Permission scope scanner.

Parses YAML frontmatter to extract declared permissions and detects
mismatches between declared scope and actual body content.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Body keywords that imply network usage
_NETWORK_KEYWORDS: tuple[str, ...] = (
    "curl",
    "wget",
    "httpx",
    "requests.get",
    "requests.post",
    "fetch(",
    "http://",
    "https://",
)


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split ``---`` delimited YAML frontmatter from body text.

    Returns (frontmatter_dict, body_text).  If no valid frontmatter is
    found, returns an empty dict and the full content as body.
    """
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return {}, content

    # Find the closing --- marker (must be on its own line)
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}, content

    raw_yaml = parts[1]
    body = parts[2]

    try:
        frontmatter = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, body


def scan_permission(path: Path) -> dict[str, Any]:
    """Scan *path* for permission scope mismatches.

    Checks declared ``permissions.filesystem`` / ``permissions.network``
    against actual body content.
    """
    scanned_at = datetime.now(timezone.utc).isoformat()
    abs_path = str(path.resolve())

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "scanner": "permission",
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

    frontmatter, body = _parse_frontmatter(content)
    body_lower = body.lower()
    findings: list[dict[str, str]] = []

    permissions = frontmatter.get("permissions", {})
    fs_perm = str(permissions.get("filesystem", "none")).lower()
    net_perm = permissions.get("network", False)
    # Normalize: "true"/"True"/True → True
    if isinstance(net_perm, str):
        net_perm = net_perm.lower() == "true"

    # Check 1: filesystem:write + network:true → exfiltration risk
    if fs_perm == "write" and net_perm is True:
        findings.append(
            {
                "code": "exfil-risk",
                "severity": "warn",
                "matched": f"filesystem:{fs_perm} + network:{net_perm}",
                "message": (
                    "Skill declares both filesystem write and network access, "
                    "which enables data exfiltration"
                ),
            }
        )

    # Check 2: shell.execute or shell:execute in body
    shell_pattern = re.compile(r"shell[.:]execute", re.IGNORECASE)
    shell_match = shell_pattern.search(body)
    if shell_match:
        findings.append(
            {
                "code": "shell-declaration",
                "severity": "warn",
                "matched": shell_match.group(0),
                "message": "Skill body references shell execution capability",
            }
        )

    # Check 3: network keywords in body without declared network permission
    if not net_perm:
        for keyword in _NETWORK_KEYWORDS:
            if keyword.lower() in body_lower:
                findings.append(
                    {
                        "code": "undeclared-network",
                        "severity": "warn",
                        "matched": keyword,
                        "message": (
                            f"Body references '{keyword}' but permissions.network is false"
                        ),
                    }
                )
                # Report first undeclared network keyword only to avoid noise
                break

    status = "blocked" if any(f["severity"] == "blocked" for f in findings) else (
        "warn" if findings else "clean"
    )

    return {
        "scanner": "permission",
        "status": status,
        "skill_path": abs_path,
        "scanned_at": scanned_at,
        "findings": findings,
    }
