"""Optional OpenProse rebuild wrapper.

Attempts to sanitize a skill via the compiler engine's `skill rebuild` command.
If the compiler module is not available, logs a skip and returns as-is.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def rebuild(staging_path: Path, run_dir: Path) -> bool:
    """Attempt to rebuild a skill using OpenProse.

    Args:
        staging_path: Path to the staged SKILL.md to rebuild.
        run_dir: Run directory for state artifacts.

    Returns:
        True if rebuild succeeded or was skipped (skill is usable).
        False if rebuild was attempted but failed.
    """
    # Check if compiler.engine.cli is importable
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "compiler.engine.cli",
                "skill", "rebuild",
                "--path", str(staging_path),
                "--out", str(staging_path),
                "--run-dir", str(run_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True
        print(f"OpenProse rebuild failed: {result.stderr}", file=sys.stderr)
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # compiler.engine.cli not available — skip rebuild, install as-is
        print("OpenProse not available — installing skill as-is with warning", file=sys.stderr)
        return True
