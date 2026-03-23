"""Optional ClawSpec test audit integration.

Lights up when ClawSpec is importable, skips gracefully when absent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def audit(skill_path: Path, run_dir: Path) -> dict[str, Any]:
    """Run ClawSpec audit on installed skill.

    Returns:
        Dict with status (audited|skip) and optional details.
    """
    try:
        from clawspec.runner import run_scenarios  # type: ignore[import-not-found]
        scenarios_path = skill_path.parent / "tests" / "scenarios.yaml"
        if not scenarios_path.exists():
            return {"status": "skip", "reason": "No scenarios.yaml found"}
        result = run_scenarios(str(scenarios_path))
        return {"status": "audited", "result": result}
    except ImportError:
        print("ClawSpec not available — skipping audit", file=sys.stderr)
        return {"status": "skip", "reason": "ClawSpec not importable"}
    except Exception as exc:
        print(f"ClawSpec error: {exc} — skipping", file=sys.stderr)
        return {"status": "skip", "reason": str(exc)}
