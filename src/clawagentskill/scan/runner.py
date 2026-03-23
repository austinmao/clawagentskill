"""Scanner runner — dispatches all enabled scanners in parallel.

Wraps synchronous scanner functions in ``asyncio.to_thread`` and gathers
results concurrently.  On scanner exception, synthesizes an error result
instead of propagating.
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from clawagentskill.scan.config import scan_config
from clawagentskill.scan.injection import scan_injection
from clawagentskill.scan.permission import scan_permission
from clawagentskill.scan.prefilter import scan_prefilter
from clawagentskill.scan.snyk import scan_snyk

# Registry mapping scanner name to its sync function
_SCANNER_REGISTRY: dict[str, Callable[[Path], dict[str, Any]]] = {
    "prefilter": scan_prefilter,
    "permission": scan_permission,
    "config": scan_config,
    "injection": scan_injection,
    "snyk": scan_snyk,
}


def _error_result(scanner_name: str, path: Path, exc: BaseException) -> dict[str, Any]:
    """Synthesize an error result for a scanner that threw an exception."""
    return {
        "scanner": scanner_name,
        "status": "error",
        "skill_path": str(path.resolve()),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "findings": [
            {
                "code": "scanner-exception",
                "severity": "warn",
                "matched": type(exc).__name__,
                "message": f"Scanner '{scanner_name}' raised {type(exc).__name__}: {exc}",
            },
        ],
        "traceback": traceback.format_exception(exc),
    }


async def _run_one(
    name: str, scanner_fn: Callable[[Path], dict[str, Any]], path: Path
) -> tuple[str, dict[str, Any]]:
    """Run a single scanner in a thread and return (name, result)."""
    try:
        result = await asyncio.to_thread(scanner_fn, path)
    except Exception as exc:  # intentional broad catch for fault isolation
        result = _error_result(name, path, exc)
    return name, result


async def run_scanners(
    path: Path,
    enabled: tuple[str, ...] = ("prefilter", "permission", "config", "injection"),
) -> dict[str, dict[str, Any]]:
    """Run all *enabled* scanners against *path* concurrently.

    Args:
        path: File to scan (typically a SKILL.md or SOUL.md).
        enabled: Tuple of scanner names to run.  Defaults to the four
                built-in scanners (excludes snyk which requires external
                tooling).

    Returns:
        Dict keyed by scanner name, each value is a scanner result dict.
    """
    tasks = []
    for name in enabled:
        scanner_fn = _SCANNER_REGISTRY.get(name)
        if scanner_fn is None:
            # Unknown scanner name — synthesize a skip result
            tasks.append(
                asyncio.ensure_future(
                    _make_skip_result(name, path)
                )
            )
        else:
            tasks.append(
                asyncio.ensure_future(
                    _run_one(name, scanner_fn, path)
                )
            )

    pairs = await asyncio.gather(*tasks)
    return dict(pairs)


async def _make_skip_result(name: str, path: Path) -> tuple[str, dict[str, Any]]:
    """Create a skip result for an unknown scanner name."""
    return name, {
        "scanner": name,
        "status": "skipped",
        "skill_path": str(path.resolve()),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "findings": [],
        "skip_reason": f"Unknown scanner '{name}'",
    }
