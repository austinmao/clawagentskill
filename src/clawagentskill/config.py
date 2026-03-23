"""Configuration loader for clawagentskill.

Reads clawagentskill.yaml from workspace root with sensible defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Hardcoded Tier A publishers — security-critical, not configurable without confirmation
TIER_A_PUBLISHERS: list[str] = ["openclaw", "anthropic"]

DEFAULT_AGENT_REGISTRIES: list[dict[str, str]] = [
    {
        "repo": "VoltAgent/awesome-claude-code-subagents",
        "type": "claude-code",
        "path": "categories/",
    },
    {
        "repo": "nicobailon/mergisi",
        "type": "claude-code",
        "path": "agents/",
    },
]


@dataclass(frozen=True)
class Config:
    """Immutable configuration for clawagentskill."""

    trusted_publishers: tuple[str, ...] = tuple(TIER_A_PUBLISHERS)
    tier_b_installs: int = 10_000
    caution_installs: int = 1_000
    scrutiny_installs: int = 100
    agent_registries: tuple[dict[str, str], ...] = tuple(DEFAULT_AGENT_REGISTRIES)
    run_dir: str = "memory/skill-adopt-runs"
    scanners: tuple[str, ...] = ("prefilter", "permission", "config", "injection")
    workspace_root: Path = field(default_factory=Path.cwd)


def load_config(workspace_root: Path | None = None) -> Config:
    """Load configuration from clawagentskill.yaml or use defaults.

    Args:
        workspace_root: Root directory to search for config file.
                       Defaults to current working directory.
    """
    root = workspace_root or Path.cwd()
    config_path = root / "clawagentskill.yaml"

    raw: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    thresholds = raw.get("thresholds", {})

    # Merge config-provided publishers with hardcoded Tier A list
    config_publishers = raw.get("trusted_publishers", [])
    merged_publishers = list(TIER_A_PUBLISHERS)
    for pub in config_publishers:
        if pub not in merged_publishers:
            merged_publishers.append(pub)

    registries = raw.get("agent_registries", DEFAULT_AGENT_REGISTRIES)

    return Config(
        trusted_publishers=tuple(merged_publishers),
        tier_b_installs=thresholds.get("tier_b_installs", 10_000),
        caution_installs=thresholds.get("caution_installs", 1_000),
        scrutiny_installs=thresholds.get("scrutiny_installs", 100),
        agent_registries=tuple(registries),
        run_dir=raw.get("run_dir", "memory/skill-adopt-runs"),
        scanners=tuple(raw.get("scanners", ["prefilter", "permission", "config", "injection"])),
        workspace_root=root,
    )
