"""Config gate scanner.

Detects undeclared environment variable usage, hardcoded secrets,
ClawHub origin files, and ClawHub CLI references.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Regex patterns for environment variable references in body text
_ENV_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\$\{([A-Z][A-Z0-9_]+)\}"),       # ${ENV_VAR}
    re.compile(r"\$([A-Z][A-Z0-9_]+)\b"),          # $ENV_VAR
    re.compile(r"os\.environ\[?['\"]([A-Z][A-Z0-9_]+)['\"]\]?"),   # os.environ["X"]
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]+)"),                 # process.env.X
    re.compile(r"process\.env\[?['\"]([A-Z][A-Z0-9_]+)['\"]\]?"),  # process.env["X"]
)

# Keywords that suggest a long hex/alnum string is a secret
_SECRET_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "key",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "auth",
    "credential",
)

# Minimum length for a suspicious alnum run to be considered a potential secret
_SECRET_MIN_LENGTH = 32

# Pattern for long alphanumeric strings that may be secrets
_LONG_ALNUM = re.compile(r"[A-Za-z0-9]{32,}")


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split ``---`` delimited YAML frontmatter from body text."""
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return {}, content

    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, parts[2]


def _declared_env_vars(frontmatter: dict[str, Any]) -> frozenset[str]:
    """Extract declared env vars from metadata.openclaw.requires.env."""
    metadata = frontmatter.get("metadata", {})
    openclaw = metadata.get("openclaw", {})
    requires = openclaw.get("requires", {})
    env_list = requires.get("env", [])
    if isinstance(env_list, list):
        return frozenset(str(v) for v in env_list)
    return frozenset()


def _find_undeclared_env(body: str, declared: frozenset[str]) -> list[dict[str, str]]:
    """Find env var references in body that are not in the declared set."""
    found: dict[str, str] = {}  # var_name -> matched_text (deduplicated)

    for pattern in _ENV_PATTERNS:
        for match in pattern.finditer(body):
            var_name = match.group(1)
            if var_name not in declared and var_name not in found:
                found[var_name] = match.group(0)

    return [
        {
            "code": "undeclared-env",
            "severity": "warn",
            "matched": matched_text,
            "message": (
                f"Environment variable '{var_name}' is referenced but not "
                f"declared in metadata.openclaw.requires.env"
            ),
        }
        for var_name, matched_text in sorted(found.items())
    ]


def _find_hardcoded_secrets(body: str) -> list[dict[str, str]]:
    """Detect long alphanumeric strings near secret-related keywords."""
    findings: list[dict[str, str]] = []
    lines = body.splitlines()

    for line_num, line in enumerate(lines, start=1):
        line_lower = line.lower()
        has_keyword = any(kw in line_lower for kw in _SECRET_CONTEXT_KEYWORDS)
        if not has_keyword:
            continue

        for match in _LONG_ALNUM.finditer(line):
            candidate = match.group(0)
            # Skip purely numeric strings (could be IDs, hashes, etc.)
            if candidate.isdigit():
                continue
            findings.append(
                {
                    "code": "hardcoded-secret",
                    "severity": "warn",
                    "matched": candidate[:40] + ("..." if len(candidate) > 40 else ""),
                    "message": (
                        f"Possible hardcoded secret on line {line_num} "
                        f"near keyword context"
                    ),
                }
            )

    return findings


def _find_clawhub_indicators(content: str) -> list[dict[str, str]]:
    """Detect ClawHub origin files and CLI references."""
    findings: list[dict[str, str]] = []
    content_lower = content.lower()

    # .clawhub/origin.json or .clawdhub/
    if ".clawhub/origin.json" in content_lower or ".clawdhub/" in content_lower:
        findings.append(
            {
                "code": "clawhub-origin",
                "severity": "warn",
                "matched": (
                    ".clawhub/origin.json"
                    if ".clawhub/origin.json" in content_lower
                    else ".clawdhub/"
                ),
                "message": (
                    "ClawHub origin tracking detected; skill may have been "
                    "installed from untrusted registry"
                ),
            }
        )

    # clawdhub CLI references (but not the patterns already caught above)
    clawhub_cli = re.compile(r"\bclawdhub\b", re.IGNORECASE)
    for match in clawhub_cli.finditer(content):
        # Skip matches that are part of the directory paths already caught
        context_start = max(0, match.start() - 1)
        if content[context_start : match.start()] == ".":
            continue
        findings.append(
            {
                "code": "clawhub-cli",
                "severity": "blocked",
                "matched": match.group(0),
                "message": "ClawHub CLI reference detected; never use ClawHub commands",
            }
        )
        # One finding is sufficient
        break

    return findings


def scan_config(path: Path) -> dict[str, Any]:
    """Scan *path* for configuration gate violations.

    Checks undeclared env vars, hardcoded secrets, and ClawHub indicators.
    """
    scanned_at = datetime.now(timezone.utc).isoformat()
    abs_path = str(path.resolve())

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "scanner": "config",
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
    declared = _declared_env_vars(frontmatter)

    findings: list[dict[str, str]] = []
    findings.extend(_find_undeclared_env(body, declared))
    findings.extend(_find_hardcoded_secrets(body))
    findings.extend(_find_clawhub_indicators(content))

    status = "blocked" if any(f["severity"] == "blocked" for f in findings) else (
        "warn" if findings else "clean"
    )

    return {
        "scanner": "config",
        "status": status,
        "skill_path": abs_path,
        "scanned_at": scanned_at,
        "findings": findings,
    }
