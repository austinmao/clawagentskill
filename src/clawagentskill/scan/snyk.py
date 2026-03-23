"""Optional Snyk wrapper scanner.

Runs ``uvx snyk-agent-scan@latest`` on the target file when both the
``uvx`` binary and ``SNYK_TOKEN`` environment variable are available.
Returns status=skipped when prerequisites are missing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _prerequisites_met() -> tuple[bool, str]:
    """Check if uvx binary and SNYK_TOKEN env var are available.

    Returns (ok, reason) where reason explains why prerequisites are unmet.
    """
    if not shutil.which("uvx"):
        return False, "uvx binary not found on PATH"
    if not os.environ.get("SNYK_TOKEN"):
        return False, "SNYK_TOKEN environment variable not set"
    return True, ""


def scan_snyk(path: Path) -> dict[str, Any]:
    """Run Snyk agent scan on *path* if prerequisites are met.

    Returns status=skipped when ``uvx`` or ``SNYK_TOKEN`` is unavailable,
    status=error on subprocess failure, otherwise parses Snyk output.
    """
    scanned_at = datetime.now(timezone.utc).isoformat()
    abs_path = str(path.resolve())

    ok, reason = _prerequisites_met()
    if not ok:
        return {
            "scanner": "snyk",
            "status": "skipped",
            "skill_path": abs_path,
            "scanned_at": scanned_at,
            "findings": [],
            "skip_reason": reason,
        }

    try:
        result = subprocess.run(
            ["uvx", "snyk-agent-scan@latest", str(path.resolve())],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "scanner": "snyk",
            "status": "error",
            "skill_path": abs_path,
            "scanned_at": scanned_at,
            "findings": [
                {
                    "code": "snyk-timeout",
                    "severity": "warn",
                    "matched": "",
                    "message": "Snyk scan timed out after 120 seconds",
                },
            ],
        }
    except OSError as exc:
        return {
            "scanner": "snyk",
            "status": "error",
            "skill_path": abs_path,
            "scanned_at": scanned_at,
            "findings": [
                {
                    "code": "snyk-error",
                    "severity": "warn",
                    "matched": str(exc),
                    "message": f"Snyk scan failed: {exc}",
                },
            ],
        }

    if result.returncode != 0:
        return {
            "scanner": "snyk",
            "status": "error",
            "skill_path": abs_path,
            "scanned_at": scanned_at,
            "findings": [
                {
                    "code": "snyk-error",
                    "severity": "warn",
                    "matched": result.stderr[:200] if result.stderr else "",
                    "message": (
                        f"Snyk exited with code {result.returncode}: "
                        f"{result.stderr[:200] if result.stderr else 'no stderr'}"
                    ),
                },
            ],
        }

    # Attempt to parse JSON output from Snyk
    findings: list[dict[str, str]] = []
    try:
        snyk_output = json.loads(result.stdout)
        vulnerabilities = snyk_output.get("vulnerabilities", [])
        for vuln in vulnerabilities:
            findings.append(
                {
                    "code": f"snyk-{vuln.get('severity', 'unknown')}",
                    "severity": "warn" if vuln.get("severity") != "critical" else "blocked",
                    "matched": vuln.get("id", ""),
                    "message": vuln.get("title", "Snyk vulnerability detected"),
                }
            )
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Non-JSON output — treat stdout as informational
        if result.stdout.strip():
            findings.append(
                {
                    "code": "snyk-raw",
                    "severity": "warn",
                    "matched": "",
                    "message": result.stdout[:300].strip(),
                }
            )

    status = "blocked" if any(f["severity"] == "blocked" for f in findings) else (
        "warn" if findings else "clean"
    )

    return {
        "scanner": "snyk",
        "status": status,
        "skill_path": abs_path,
        "scanned_at": scanned_at,
        "findings": findings,
    }
