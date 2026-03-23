"""Prompt injection scanner.

Detects five categories of prompt injection patterns:
1. ClawHavoc indicators (blocked)
2. Prompt overrides (warn)
3. Role hijacking (warn)
4. Covert exfiltration (warn)
5. Hidden instructions (warn)

Applies base64 decode attempt and basic unicode normalization before
scanning to catch obfuscated payloads.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Category 1: ClawHavoc indicators ─────────────────────────────────
_CLAWHAVOC_PATTERNS: tuple[str, ...] = (
    "91.92.242.30",
    "mediafire.com",
    "mega.nz",
    "clawdhub install",
    "atomic stealer",
    "amos stealer",
)

# ── Category 2: Prompt override phrases ──────────────────────────────
_PROMPT_OVERRIDE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s+follow", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous|above)", re.IGNORECASE),
    re.compile(r"override\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior|earlier)", re.IGNORECASE),
)

# ── Category 3: Role hijacking ───────────────────────────────────────
_ROLE_HIJACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\b", re.IGNORECASE),
    re.compile(r"pretend\s+to\s+be\b", re.IGNORECASE),
    re.compile(r"assume\s+the\s+role\b", re.IGNORECASE),
    re.compile(r"switch\s+to\s+(?:being|role)\b", re.IGNORECASE),
)

# ── Category 4: Covert exfiltration ──────────────────────────────────
_EXFIL_PATTERNS: tuple[re.Pattern[str], ...] = (
    # base64 encode/decode calls
    re.compile(r"base64[._](?:encode|decode|b64encode|b64decode)", re.IGNORECASE),
    # curl/wget to external hosts (not localhost/127.0.0.1)
    re.compile(
        r"(?:curl|wget)\s+(?!.*(?:localhost|127\.0\.0\.1|0\.0\.0\.0))\S*https?://",
        re.IGNORECASE,
    ),
    # eval with encoded content
    re.compile(r"eval\s*\(", re.IGNORECASE),
)

# ── Category 5: Hidden instruction patterns ──────────────────────────
_HIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # HTML comments containing instruction-like words
    re.compile(
        r"<!--\s*(?:.*?(?:instruction|command|execute|ignore|override|system).*?)\s*-->",
        re.IGNORECASE | re.DOTALL,
    ),
    # Zero-width characters (U+200B, U+200C, U+200D, U+FEFF, U+2060)
    re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]{3,}"),
    # CSS-hidden text patterns
    re.compile(
        r"(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0)",
        re.IGNORECASE,
    ),
)


def _normalize_content(content: str) -> str:
    """Apply unicode normalization (NFKC) to catch obfuscated text."""
    return unicodedata.normalize("NFKC", content)


def _try_base64_decode(content: str) -> str:
    """Attempt to find and decode base64 blobs in the content.

    Returns the original content with decoded base64 appended so that
    the scanner can check decoded payloads too.
    """
    # Match plausible base64 strings (min 40 chars, only valid base64 chars + padding)
    b64_pattern = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
    decoded_parts: list[str] = []

    for match in b64_pattern.finditer(content):
        candidate = match.group(0)
        try:
            decoded = base64.b64decode(candidate, validate=True).decode(
                "utf-8", errors="replace"
            )
            # Only include if it looks like readable text (>50% printable ASCII)
            printable_ratio = sum(1 for c in decoded if c.isprintable()) / max(
                len(decoded), 1
            )
            if printable_ratio > 0.5:
                decoded_parts.append(decoded)
        except Exception:  # intentional broad catch for decode attempts
            continue

    if decoded_parts:
        return content + "\n" + "\n".join(decoded_parts)
    return content


def _scan_category(
    content: str,
    patterns: tuple[str, ...] | tuple[re.Pattern[str], ...],
    code: str,
    severity: str,
    message_prefix: str,
) -> list[dict[str, str]]:
    """Scan content against a list of patterns (strings or compiled regexes)."""
    findings: list[dict[str, str]] = []

    for pattern in patterns:
        if isinstance(pattern, str):
            if pattern.lower() in content.lower():
                findings.append(
                    {
                        "code": code,
                        "severity": severity,
                        "matched": pattern,
                        "message": f"{message_prefix}: '{pattern}'",
                    }
                )
        else:
            match = pattern.search(content)
            if match:
                findings.append(
                    {
                        "code": code,
                        "severity": severity,
                        "matched": match.group(0)[:80],
                        "message": f"{message_prefix}: '{match.group(0)[:60]}'",
                    }
                )

    return findings


def scan_injection(path: Path) -> dict[str, Any]:
    """Scan *path* for prompt injection patterns across five categories.

    Category 1 (ClawHavoc) matches produce severity=blocked.
    Categories 2-5 produce severity=warn.
    """
    scanned_at = datetime.now(timezone.utc).isoformat()
    abs_path = str(path.resolve())

    try:
        raw_content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "scanner": "injection",
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

    # Pre-process: normalize unicode and attempt base64 decode
    normalized = _normalize_content(raw_content)
    content = _try_base64_decode(normalized)

    findings: list[dict[str, str]] = []

    # Cat 1: ClawHavoc indicators (blocked)
    findings.extend(
        _scan_category(
            content,
            _CLAWHAVOC_PATTERNS,
            code="clawhavoc-indicator",
            severity="blocked",
            message_prefix="ClawHavoc indicator detected",
        )
    )

    # Cat 2: Prompt overrides (warn)
    findings.extend(
        _scan_category(
            content,
            _PROMPT_OVERRIDE_PATTERNS,
            code="prompt-override",
            severity="warn",
            message_prefix="Prompt override attempt detected",
        )
    )

    # Cat 3: Role hijacking (warn)
    findings.extend(
        _scan_category(
            content,
            _ROLE_HIJACK_PATTERNS,
            code="role-hijacking",
            severity="warn",
            message_prefix="Role hijacking attempt detected",
        )
    )

    # Cat 4: Covert exfiltration (warn)
    findings.extend(
        _scan_category(
            content,
            _EXFIL_PATTERNS,
            code="covert-exfiltration",
            severity="warn",
            message_prefix="Covert exfiltration pattern detected",
        )
    )

    # Cat 5: Hidden instructions (warn)
    findings.extend(
        _scan_category(
            content,
            _HIDDEN_PATTERNS,
            code="hidden-instruction",
            severity="warn",
            message_prefix="Hidden instruction pattern detected",
        )
    )

    status = "blocked" if any(f["severity"] == "blocked" for f in findings) else (
        "warn" if findings else "clean"
    )

    return {
        "scanner": "injection",
        "status": status,
        "skill_path": abs_path,
        "scanned_at": scanned_at,
        "findings": findings,
    }
