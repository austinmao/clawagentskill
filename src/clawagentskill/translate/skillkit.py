"""SkillKit translate wrapper with 3-tier fallback.

1. Try `skillkit translate --to openclaw`
2. Fall back to `skillkit translate --to clawdbot`
3. Fall back to built-in converter
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from clawagentskill.translate.builtin import translate as builtin_translate


def _try_skillkit(content: str, target_format: str) -> str | None:
    """Try SkillKit translation with the given target format.

    Returns translated content or None if SkillKit unavailable/failed.
    """
    if not shutil.which("skillkit"):
        return None

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["skillkit", "translate", "--to", target_format, tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return None


def translate(content: str) -> str:
    """Translate content using SkillKit with 3-tier fallback.

    1. skillkit translate --to openclaw
    2. skillkit translate --to clawdbot
    3. Built-in CC→SOUL.md converter

    Args:
        content: Raw Claude Code agent markdown content.

    Returns:
        Translated SOUL.md content.

    Raises:
        ValueError: If all translation methods fail.
    """
    # Tier 1: SkillKit openclaw format
    result = _try_skillkit(content, "openclaw")
    if result:
        return result

    # Tier 2: SkillKit clawdbot format
    result = _try_skillkit(content, "clawdbot")
    if result:
        return result

    # Tier 3: Built-in converter
    return builtin_translate(content)
