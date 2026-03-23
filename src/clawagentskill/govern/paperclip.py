"""Optional Paperclip governance export.

Registers the installed skill in Paperclip when the API is reachable.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


PAPERCLIP_URL = "http://localhost:3100/api"


def export(skill_id: str, run_dir: Path) -> dict[str, Any]:
    """Register skill in Paperclip governance system.

    Returns:
        Dict with status (registered|skip).
    """
    try:
        resp = httpx.get(f"{PAPERCLIP_URL}/health", timeout=5)
        if resp.status_code != 200:
            return {"status": "skip", "reason": "Paperclip unhealthy"}
    except httpx.HTTPError:
        print("Paperclip not reachable — skipping governance export", file=sys.stderr)
        return {"status": "skip", "reason": "Paperclip unreachable"}

    try:
        resp = httpx.post(
            f"{PAPERCLIP_URL}/issues",
            json={
                "title": f"Skill adopted: {skill_id}",
                "type": "governance",
                "source": "clawagentskill",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return {"status": "registered", "skill_id": skill_id}
        return {"status": "skip", "reason": f"Paperclip returned {resp.status_code}"}
    except httpx.HTTPError as exc:
        print(f"Paperclip export error: {exc}", file=sys.stderr)
        return {"status": "skip", "reason": str(exc)}
