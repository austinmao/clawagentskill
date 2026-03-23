"""Run-scoped state manager for adoption pipelines.

Extracted from scripts/lobster-skill-run.py — handles run directory creation,
meta.yaml read/write, envelope emit/parse, and slugification.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def slugify(text: str) -> str:
    """Convert arbitrary text to a filename-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:64]


def infer_publisher(skill_url: str) -> str:
    """Extract publisher name from a skills.sh URL."""
    if not skill_url:
        return "unknown"
    parts = skill_url.replace("https://", "").replace("http://", "").split("/")
    if len(parts) >= 2 and "skills.sh" in parts[0]:
        return parts[1]
    return "unknown"


class StateManager:
    """Manages run-scoped state for a single pipeline execution."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self._run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    # ── YAML helpers ─────────────────────────────────────────────

    def read_yaml(self, filename: str) -> dict[str, Any]:
        """Read a YAML file from the run directory."""
        path = self._run_dir / filename
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def write_yaml(self, filename: str, data: dict[str, Any]) -> None:
        """Write data to a YAML file in the run directory."""
        path = self._run_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def load_meta(self) -> dict[str, Any]:
        """Load meta.yaml from the run directory."""
        return self.read_yaml("meta.yaml")

    def save_meta(self, meta: dict[str, Any]) -> None:
        """Save meta.yaml to the run directory."""
        self.write_yaml("meta.yaml", meta)

    # ── Envelope helpers ─────────────────────────────────────────

    def emit_envelope(self) -> str:
        """Return the compact JSON envelope for stdin-chaining."""
        return json.dumps({"run_dir": str(self._run_dir)})

    @staticmethod
    def parse_envelope(data: str) -> Path:
        """Parse run_dir from a compact JSON envelope."""
        obj = json.loads(data)
        return Path(obj["run_dir"])

    # ── Factory ──────────────────────────────────────────────────

    @classmethod
    def create_run(
        cls,
        base_dir: Path,
        query: str,
        *,
        skill_url: str = "",
        scan_mode: str = "quality",
    ) -> "StateManager":
        """Create a new run directory with initial meta.yaml."""
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d-%H%M%S")

        if skill_url:
            skill_slug = slugify(skill_url.rstrip("/").split("/")[-1])
        elif "/" in query:
            skill_slug = slugify(query.split("/", 1)[1].strip())
        else:
            skill_slug = slugify(query)

        publisher = "unknown"
        if skill_url:
            publisher = infer_publisher(skill_url)
        elif "/" in query:
            publisher = query.split("/", 1)[0].strip().lower()

        run_dir = base_dir / f"{skill_slug}-{ts}"
        manager = cls(run_dir)

        meta: dict[str, Any] = {
            "run_id": f"skill-adopt-{ts}",
            "query": query,
            "skill_url": skill_url,
            "skill_slug": skill_slug,
            "skill_id": "",
            "publisher": publisher,
            "tier": "",
            "scan_mode": scan_mode,
            "install_count": 0,
            "install_ref": skill_url or "",
            "target_path": "",
            "staging_path": "",
            "test_mode": False,
            "stage_failed": None,
            "started_at": now.isoformat(),
            "installed_at": None,
            "clawwrap_status": None,
            "paperclip_status": None,
        }
        manager.save_meta(meta)
        return manager
