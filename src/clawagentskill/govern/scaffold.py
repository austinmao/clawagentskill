"""Optional ClawScaffold catalog registration.

Lights up when ClawScaffold is importable, skips gracefully when absent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def register(skill_path: Path, run_dir: Path) -> dict[str, Any]:
    """Register installed skill in ClawScaffold catalog.

    Returns:
        Dict with status (registered|skip) and optional details.
    """
    try:
        from compiler.engine.cli import scaffold_adopt  # type: ignore[import-not-found]
        scaffold_adopt(str(skill_path))
        return {"status": "registered", "path": str(skill_path)}
    except ImportError:
        print("ClawScaffold not available — skipping catalog registration", file=sys.stderr)
        return {"status": "skip", "reason": "ClawScaffold not importable"}
    except Exception as exc:
        print(f"ClawScaffold error: {exc} — skipping", file=sys.stderr)
        return {"status": "skip", "reason": str(exc)}
