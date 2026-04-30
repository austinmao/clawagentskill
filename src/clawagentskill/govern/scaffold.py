"""Optional ClawScaffold catalog registration.

Lights up when ClawScaffold is importable, skips gracefully when absent.
Registers installed skills/agents into the ClawScaffold adoption registry so
subsequent governance and compiler runs can locate them.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def register(skill_path: Path, run_dir: Path) -> dict[str, Any]:
    """Register installed skill in ClawScaffold adoption registry.

    Uses `compiler.engine.adopt.record_adoption_event` for a lightweight
    registry write. Avoids the full `handle_adopt` draft-spec generation
    which is reserved for operator-driven adoption flows.

    Returns:
        Dict with status (registered|skip|error) and optional details.
    """
    try:
        from compiler.engine.adopt import (
            find_adoption_entry,
            infer_target_from_runtime_path,
            record_adoption_event,
        )
    except ImportError as exc:
        print(f"ClawScaffold not available — skipping catalog registration ({exc})", file=sys.stderr)
        return {"status": "skip", "reason": f"ClawScaffold not importable: {exc}"}

    try:
        kind, target_id = infer_target_from_runtime_path(skill_path)
    except ValueError as exc:
        print(f"ClawScaffold: cannot infer target from {skill_path} — skipping ({exc})", file=sys.stderr)
        return {"status": "skip", "reason": f"Cannot infer target: {exc}"}

    existing = find_adoption_entry(kind, target_id)
    run_id = run_dir.name if run_dir else None

    try:
        registry_path = record_adoption_event(
            kind=kind,
            target_id=target_id,
            runtime_path=skill_path,
            action="adopt",
            run_id=run_id,
        )
    except Exception as exc:
        print(f"ClawScaffold registry write failed: {exc} — skipping", file=sys.stderr)
        return {"status": "error", "reason": str(exc)}

    return {
        "status": "registered",
        "kind": kind,
        "target_id": target_id,
        "registry_path": str(registry_path),
        "existing": bool(existing),
    }
