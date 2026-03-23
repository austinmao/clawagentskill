"""Optional ClawWrap outbound target check.

Checks if an installed skill uses outbound.submit and verifies
targets.yaml registration when ClawWrap config is available.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def check(skill_path: Path, workspace_root: Path) -> dict[str, Any]:
    """Check if skill uses outbound.submit and verify target registration.

    Returns:
        Dict with status (clean|skip|requires_registration).
    """
    targets_yaml = workspace_root / "clawwrap" / "config" / "targets.yaml"
    if not targets_yaml.exists():
        return {"status": "skip", "reason": "ClawWrap targets.yaml not found"}

    if not skill_path.exists():
        return {"status": "skip", "reason": "Skill file not found"}

    content = skill_path.read_text(encoding="utf-8")
    if "outbound.submit" not in content:
        return {"status": "clean", "message": "No outbound.submit calls detected"}

    # Check if target is registered
    try:
        with targets_yaml.open(encoding="utf-8") as fh:
            targets = yaml.safe_load(fh) or {}

        skill_name = skill_path.parent.name
        registered_targets = targets.get("targets", {})

        if skill_name in registered_targets:
            return {"status": "clean", "message": f"Target '{skill_name}' already registered"}

        print(f"ClawWrap: outbound.submit detected — manual target registration required", file=sys.stderr)
        return {
            "status": "requires_registration",
            "message": f"Edit {targets_yaml} to add a target entry for '{skill_name}'",
        }
    except Exception as exc:
        print(f"ClawWrap check error: {exc}", file=sys.stderr)
        return {"status": "skip", "reason": str(exc)}
