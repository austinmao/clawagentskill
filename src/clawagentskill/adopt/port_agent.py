"""Port a Claude Code agent to OpenClaw SOUL.md format.

Fetches agent from GitHub, translates via SkillKit or built-in converter,
runs injection scan on the result, and installs to agents/ directory.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx

from clawagentskill.scan.runner import run_scanners
from clawagentskill.translate.skillkit import translate


async def run_port(
    url: str,
    target: str,
    workspace_root: Path,
    *,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Port a Claude Code agent to OpenClaw SOUL.md.

    Args:
        url: GitHub raw URL to the agent markdown file.
        target: Target as "department/agent-name".
        workspace_root: Workspace root directory.
        auto_approve: Skip approval prompt.

    Returns:
        Dict with status, target_path, and any findings.
    """
    # Parse target
    parts = target.split("/", 1)
    if len(parts) != 2:
        return {"status": "error", "message": f"Invalid target format: {target!r}. Expected 'department/agent-name'"}

    dept, agent_name = parts

    # Fetch agent content
    try:
        raw_url = url
        if "github.com" in raw_url and "/blob/" in raw_url:
            raw_url = raw_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        async with httpx.AsyncClient() as client:
            resp = await client.get(raw_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text
    except httpx.HTTPError as exc:
        return {"status": "error", "message": f"Failed to fetch agent: {exc}"}

    # Translate to SOUL.md
    try:
        soul_content = translate(content)
    except ValueError as exc:
        return {"status": "error", "message": f"Translation failed: {exc}"}

    # Write to temp file for scanning
    target_dir = workspace_root / "agents" / dept / agent_name
    target_dir.mkdir(parents=True, exist_ok=True)
    soul_path = target_dir / "SOUL.md"

    # Write temporary for scanning
    soul_path.write_text(soul_content, encoding="utf-8")

    # Run injection scan only (most relevant for ported agents)
    scan_results = await run_scanners(soul_path, enabled=("injection",))

    injection_result = scan_results.get("injection", {})
    injection_status = injection_result.get("status", "clean")

    if injection_status == "blocked":
        # Remove the written file
        soul_path.unlink(missing_ok=True)
        if not any(target_dir.iterdir()):
            target_dir.rmdir()
        return {
            "status": "blocked",
            "message": "Injection scan blocked — SOUL.md not installed",
            "findings": injection_result.get("findings", []),
        }

    if injection_status == "warn" and not auto_approve:
        print(f"\nWARNING: Injection scan found warnings in ported agent.", file=sys.stderr)
        print(f"Target: {soul_path}", file=sys.stderr)
        for finding in injection_result.get("findings", []):
            print(f"  - [{finding.get('code')}] {finding.get('message')}", file=sys.stderr)

    return {
        "status": "installed",
        "target_path": str(soul_path),
        "findings": injection_result.get("findings", []),
    }


def port(
    url: str,
    target: str,
    workspace_root: Path,
    *,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Sync wrapper for run_port."""
    return asyncio.run(run_port(url, target, workspace_root, auto_approve=auto_approve))
