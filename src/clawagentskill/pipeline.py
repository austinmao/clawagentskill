"""16-stage adoption pipeline orchestrator.

Stages: state-init → validate-prereqs → search → select → download → prefilter
→ parallel-scan → decide → approval-preview → install-or-rebuild → govern chain
→ sync → notify → complete.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawagentskill.adopt.install import (
    cleanup_staging,
    copy_local,
    download_to_staging,
    install_to_workspace,
)
from clawagentskill.adopt.rebuild import rebuild
from clawagentskill.config import TIER_A_PUBLISHERS, Config, load_config
from clawagentskill.decide.rule_c import apply_rule_c
from clawagentskill.decide.tier import classify_tier, derive_scan_mode
from clawagentskill.discover import local as local_discover
from clawagentskill.discover import skills_sh
from clawagentskill.govern import clawspec, clawwrap, paperclip, scaffold
from clawagentskill.scan.prefilter import scan_prefilter
from clawagentskill.scan.runner import run_scanners
from clawagentskill.select import select_best
from clawagentskill.state import StateManager, infer_publisher, slugify


def _resolve_install_base(
    *,
    target_root: Path | None,
    workspace_root: Path | None,
) -> Path:
    """Resolve the base directory under which skills/ will be written.

    Resolution order (first match wins):
      1. Explicit ``target_root`` kwarg (e.g. from --target CLI flag).
      2. Explicit ``workspace_root`` kwarg (back-compat with existing callers).
      3. ``$OPENCLAW_WORKSPACE`` env var — the bind-mounted workspace inside
         gateway containers (e.g. ``/home/node/.openclaw``).
      4. ``$HOME/.openclaw`` fallback.
      5. ``Path.cwd()`` as an absolute last resort.

    This avoids defaulting to the container image's ephemeral cwd (``/app``),
    which caused installed skills to be wiped on ``docker compose up -d``.
    """
    if target_root is not None:
        return target_root
    if workspace_root is not None:
        return workspace_root
    env_workspace = os.environ.get("OPENCLAW_WORKSPACE", "").strip()
    if env_workspace:
        return Path(env_workspace)
    home = os.environ.get("HOME", "").strip()
    if home:
        return Path(home) / ".openclaw"
    return Path.cwd()


async def run_adopt(
    query: str,
    *,
    url: str = "",
    scan_mode: str = "quality",
    auto_approve: bool = False,
    force: bool = False,
    workspace_root: Path | None = None,
    target_root: Path | None = None,
) -> dict[str, Any]:
    """Run the full 16-stage adoption pipeline.

    Args:
        query: Search query or skill name (e.g., "stripe integration" or "openclaw/resend").
        url: Direct URL to skip search.
        scan_mode: Scanner configuration (quality|efficiency|simplicity).
        auto_approve: Skip approval prompt.
        force: Install even if below quality thresholds.
        workspace_root: Workspace root for local discovery and run-dir base.
            Defaults to ``$OPENCLAW_WORKSPACE``, then ``$HOME/.openclaw``, then cwd.
        target_root: Explicit install-target base (e.g. from ``--target`` CLI flag).
            When set, overrides ``workspace_root`` and env fallbacks for target
            path resolution. See :func:`_resolve_install_base`.

    Returns:
        Dict with pipeline result including verdict, target_path, etc.
    """
    install_base = _resolve_install_base(
        target_root=target_root,
        workspace_root=workspace_root,
    )
    root = workspace_root or install_base
    config = load_config(root)

    # Stage 1: state-init
    run_dir_base = root / config.run_dir
    state = StateManager.create_run(run_dir_base, query, skill_url=url, scan_mode=scan_mode)
    meta = state.load_meta()

    # Stage 2: validate-prereqs
    if not shutil.which("npx") and not url:
        meta["stage_failed"] = "validate-prereqs"
        meta["stage_failed_reason"] = "npx not found on PATH"
        state.save_meta(meta)
        return {"status": "error", "stage": "validate-prereqs", "message": "npx not found"}

    # Determine publisher and tier
    publisher = meta["publisher"]
    if "/" in query and publisher == "unknown":
        publisher = query.split("/", 1)[0].strip().lower()
        meta["publisher"] = publisher

    tier = classify_tier(publisher, meta["install_count"], config.trusted_publishers)
    scan_mode_resolved = derive_scan_mode(tier, meta["install_count"], scan_mode)
    meta["tier"] = tier
    meta["scan_mode"] = scan_mode_resolved
    state.save_meta(meta)

    skill_slug = meta["skill_slug"]

    # Stage 3: search
    candidates: list[dict[str, Any]] = []

    if tier == "A":
        candidates = local_discover.search(query, root)
    elif url:
        skill_name = url.rstrip("/").split("/")[-1]
        candidates = [{
            "name": skill_name,
            "publisher": infer_publisher(url),
            "install_ref": url,
            "install_count": 0,
            "tier": tier,
            "source": "direct_url",
        }]
    else:
        registry_results = skills_sh.search(query)
        local_results = local_discover.search(query, root)
        # Registry first so rank_key stability biases toward external results
        # when keys tie. select_best applies real ranking, so order is not
        # semantically load-bearing anymore.
        candidates = registry_results + local_results

    if not candidates:
        meta["stage_failed"] = "search"
        state.save_meta(meta)
        return {"status": "error", "stage": "search", "message": "No candidates found"}

    state.write_yaml("search-candidates.yaml", {"candidates": candidates})

    # Stage 4: select — rank by exact match, real install count, tier, then
    # local-already-installed tiebreak. Replaces naive `candidates[0]` which
    # let synthetic local sentinel (999_999) beat real registry counts.
    selected = select_best(candidates, query)
    install_count = selected.get("install_count", 0)
    publisher = selected.get("publisher", publisher)

    # Re-classify with actual install count
    tier = classify_tier(publisher, install_count, config.trusted_publishers)
    scan_mode_resolved = derive_scan_mode(tier, install_count, scan_mode)

    # Derive target path — anchored on install_base (bind-mounted workspace
    # when running inside a gateway container), NOT on ``root`` which may be
    # the ephemeral container cwd (e.g. /app).
    target_path = (
        install_base
        / "skills"
        / "platform"
        / "governance"
        / slugify(selected["name"])
        / "SKILL.md"
    )
    if selected.get("target_path"):
        target_path = Path(selected["target_path"])

    meta.update({
        "skill_id": slugify(selected["name"]),
        "publisher": publisher,
        "tier": tier,
        "scan_mode": scan_mode_resolved,
        "install_count": install_count,
        "install_ref": selected.get("install_ref", ""),
        "target_path": str(target_path),
    })
    state.save_meta(meta)
    state.write_yaml("selection.yaml", selected)

    # Stage 5: download
    staging_path: Path
    if tier == "A" and selected.get("source") == "local_workspace":
        local_target = selected.get("target_path", "")
        if local_target and Path(local_target).exists():
            staging_base = Path("/tmp/skill-staging")
            staging_path = staging_base / skill_slug / "SKILL.md"
            copy_local(Path(local_target), staging_path)
        else:
            meta["stage_failed"] = "download"
            state.save_meta(meta)
            return {"status": "error", "stage": "download", "message": "Tier A skill not found locally"}
    else:
        try:
            staging_path = download_to_staging(selected.get("install_ref", ""), skill_slug)
        except RuntimeError as exc:
            meta["stage_failed"] = "download"
            state.save_meta(meta)
            return {"status": "error", "stage": "download", "message": str(exc)}

    meta["staging_path"] = str(staging_path)
    state.save_meta(meta)

    # Stage 6: prefilter
    prefilter_result = scan_prefilter(staging_path)
    state.write_yaml("prefilter.yaml", prefilter_result)

    if prefilter_result["status"] == "blocked":
        meta["stage_failed"] = "prefilter"
        state.save_meta(meta)
        cleanup_staging(skill_slug)
        return {
            "status": "blocked",
            "stage": "prefilter",
            "message": "ClawHavoc patterns detected",
            "findings": prefilter_result["findings"],
        }

    # Stage 7: parallel-scan (skip for Tier A)
    scan_results: dict[str, dict[str, Any]] = {}
    if tier != "A":
        scan_results = await run_scanners(staging_path, enabled=config.scanners)
        state.write_yaml("scan-results.yaml", scan_results)
    else:
        state.write_yaml("scan-results.yaml", {"note": "Tier A — scanners skipped"})

    # Stage 8: decide
    decision = apply_rule_c(tier, publisher, scan_results, config.trusted_publishers)
    state.write_yaml("decision.yaml", decision)

    verdict = decision["verdict"]

    if verdict == "blocked":
        meta["stage_failed"] = "decide"
        state.save_meta(meta)
        cleanup_staging(skill_slug)
        return {
            "status": "blocked",
            "stage": "decide",
            "message": decision["rationale"],
            "decision": decision,
        }

    # Stage 9: approval-preview
    if not auto_approve:
        _print_approval_preview(meta, decision, scan_results)
        if not force:
            try:
                response = input("\nApprove? [yes/no]: ").strip().lower()
                if response not in ("yes", "y"):
                    cleanup_staging(skill_slug)
                    return {"status": "rejected", "stage": "approval", "message": "Operator rejected"}
            except (EOFError, KeyboardInterrupt):
                cleanup_staging(skill_slug)
                return {"status": "rejected", "stage": "approval", "message": "No input — rejected"}

    # Stage 10: install-or-rebuild
    if verdict == "rebuild":
        if not rebuild(staging_path, state.run_dir):
            cleanup_staging(skill_slug)
            return {"status": "error", "stage": "rebuild", "message": "OpenProse rebuild failed"}

    installed_path = install_to_workspace(staging_path, target_path)
    meta["installed_at"] = datetime.now(timezone.utc).isoformat()
    state.save_meta(meta)

    # Stage 11-14: governance chain
    gov_results: dict[str, Any] = {}
    gov_results["scaffold"] = scaffold.register(installed_path, state.run_dir)
    gov_results["clawspec"] = clawspec.audit(installed_path, state.run_dir)
    gov_results["clawwrap"] = clawwrap.check(installed_path, root)
    gov_results["paperclip"] = paperclip.export(meta["skill_id"], state.run_dir)
    state.write_yaml("governance.yaml", gov_results)

    # Cleanup
    cleanup_staging(skill_slug)

    print(f"\nInstalled: {installed_path}", file=sys.stderr)

    return {
        "status": "installed",
        "target_path": str(installed_path),
        "verdict": verdict,
        "decision": decision,
        "governance": gov_results,
        "run_dir": str(state.run_dir),
    }


def _print_approval_preview(
    meta: dict[str, Any],
    decision: dict[str, Any],
    scan_results: dict[str, Any],
) -> None:
    """Print the approval preview to stderr."""
    skill_id = meta.get("skill_id", "unknown")
    install_ref = meta.get("install_ref", "unknown")
    install_count = meta.get("install_count", 0)
    tier = meta.get("tier", "C")
    scan_mode = meta.get("scan_mode", "quality")
    verdict = decision.get("verdict", "unknown")
    scanner_summary = decision.get("scanner_summary", {})

    tier_labels = {"A": "Trusted official", "B": "Community trusted", "C": "Community standard"}
    scan_labels = {"quality": "Quality (full audit)", "efficiency": "Efficiency (standard)", "simplicity": "Simplicity (Tier A)"}

    print(f"\nSkill Adoption Preview", file=sys.stderr)
    print(f"======================", file=sys.stderr)
    print(f"Skill:     {skill_id}", file=sys.stderr)
    print(f"Source:    {install_ref} ({install_count} installs)", file=sys.stderr)
    print(f"Tier:      {tier} ({tier_labels.get(tier, 'Unknown')})", file=sys.stderr)
    print(f"Scan mode: {scan_labels.get(scan_mode, scan_mode)}", file=sys.stderr)
    print(f"\nScanner verdicts:", file=sys.stderr)
    for scanner_name, status in scanner_summary.items():
        print(f"  {scanner_name:<12} {status}", file=sys.stderr)
    print(f"\nDecision: {verdict.upper()}", file=sys.stderr)


def adopt_sync(
    query: str,
    *,
    url: str = "",
    scan_mode: str = "quality",
    auto_approve: bool = False,
    force: bool = False,
    workspace_root: Path | None = None,
    target_root: Path | None = None,
) -> dict[str, Any]:
    """Sync wrapper for run_adopt.

    ``target_root`` is a pass-through kwarg for the ``--target`` CLI flag
    (owned by cli.py). See :func:`run_adopt` for resolution semantics.
    """
    return asyncio.run(run_adopt(
        query,
        url=url,
        scan_mode=scan_mode,
        auto_approve=auto_approve,
        force=force,
        workspace_root=workspace_root,
        target_root=target_root,
    ))
