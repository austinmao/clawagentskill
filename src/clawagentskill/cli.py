"""CLI interface for clawagentskill.

Provides 5 subcommands: find, adopt, port, scan, status.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

from clawagentskill import __version__


def _cmd_find(args: argparse.Namespace) -> int:
    """Search skills.sh + agent repos for capabilities."""
    from clawagentskill.config import load_config
    from clawagentskill.decide.trust import compute_trust_score
    from clawagentskill.discover import github, local, skills_sh

    config = load_config()
    query = args.query
    max_results = args.max_results

    all_results: list[dict] = []

    # Local workspace search
    if not args.agents_only:
        local_results = local.search(query, config.workspace_root, max_results)
        all_results.extend(local_results)

    # skills.sh marketplace search
    if not args.agents_only:
        marketplace_results = skills_sh.search(query, max_results)
        all_results.extend(marketplace_results)

    # GitHub agent repos
    if not args.skills_only:
        agent_results = github.search(query, config.agent_registries, max_results)
        all_results.extend(agent_results)

    if not all_results:
        print("No results found.", file=sys.stderr)
        return 1

    # Deduplicate by name
    seen: set[str] = set()
    unique: list[dict] = []
    for r in all_results:
        name = r.get("name", "")
        if name not in seen:
            seen.add(name)
            unique.append(r)

    # Print results
    print(f"\n{'Name':<30} {'Publisher':<15} {'Installs':>10} {'Source':<15} {'Tier':<5}")
    print("-" * 80)
    for r in unique[:max_results]:
        name = r.get("name", "?")[:29]
        publisher = r.get("publisher", "?")[:14]
        installs = r.get("install_count", 0)
        source = r.get("source", "?")[:14]
        tier = r.get("tier", "C")
        print(f"{name:<30} {publisher:<15} {installs:>10} {source:<15} {tier:<5}")

    print(f"\n{len(unique)} result(s) found.")
    return 0


def _cmd_adopt(args: argparse.Namespace) -> int:
    """Full pipeline: discover -> scan -> approve -> install."""
    from clawagentskill.pipeline import adopt_sync

    result = adopt_sync(
        args.query,
        url=args.url,
        scan_mode=args.scan_mode,
        auto_approve=args.yes,
        force=args.force,
    )

    status = result.get("status", "error")
    if status == "installed":
        print(f"\nInstalled: {result.get('target_path')}")
        return 0
    elif status == "blocked":
        print(f"\nBLOCKED: {result.get('message')}", file=sys.stderr)
        return 1
    elif status == "rejected":
        print(f"\nRejected: {result.get('message')}", file=sys.stderr)
        return 2
    else:
        print(f"\nError: {result.get('message')}", file=sys.stderr)
        return 1


def _cmd_port(args: argparse.Namespace) -> int:
    """Port Claude Code agent to OpenClaw SOUL.md."""
    from clawagentskill.adopt.port_agent import port

    result = port(
        args.url,
        args.target,
        Path.cwd(),
        auto_approve=args.yes,
    )

    status = result.get("status", "error")
    if status == "installed":
        print(f"\nPorted: {result.get('target_path')}")
        return 0
    elif status == "blocked":
        print(f"\nBLOCKED: {result.get('message')}", file=sys.stderr)
        return 1
    else:
        print(f"\nError: {result.get('message')}", file=sys.stderr)
        return 1


def _cmd_scan(args: argparse.Namespace) -> int:
    """Run 4 security scanners on a local file."""
    from clawagentskill.scan.runner import run_scanners

    path = Path(args.path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    results = asyncio.run(run_scanners(path))

    if args.json_output:
        print(json.dumps(results, indent=2, default=str))
    else:
        has_issues = False
        print(f"\nScan results for: {path}")
        print("=" * 60)
        for scanner_name, result in results.items():
            status = result.get("status", "unknown")
            findings = result.get("findings", [])
            status_icon = {"clean": "CLEAN", "warn": "WARN", "blocked": "BLOCKED", "error": "ERROR", "skipped": "SKIP"}.get(status, status)
            print(f"\n  {scanner_name:<15} {status_icon}")
            if status in ("warn", "blocked"):
                has_issues = True
            for finding in findings:
                code = finding.get("code", "?")
                severity = finding.get("severity", "?")
                message = finding.get("message", "?")
                print(f"    [{severity}] {code}: {message}")

        print()
        if has_issues:
            return 1

    # Check if any scanner reported warn or blocked
    for result in results.values():
        if result.get("status") in ("warn", "blocked"):
            return 1

    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show recent adoption runs and their verdicts."""
    from clawagentskill.config import load_config

    config = load_config()
    run_base = Path.cwd() / config.run_dir

    if not run_base.exists():
        print("No adoption runs found.", file=sys.stderr)
        return 0

    runs: list[dict] = []
    for meta_path in sorted(run_base.rglob("meta.yaml"), reverse=True):
        with meta_path.open(encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}
        runs.append(meta)
        if len(runs) >= args.limit:
            break

    if not runs:
        print("No adoption runs found.", file=sys.stderr)
        return 0

    print(f"\n{'Run ID':<30} {'Skill':<20} {'Tier':>5} {'Status':<12} {'Started':<20}")
    print("-" * 90)
    for meta in runs:
        run_id = meta.get("run_id", "?")[:29]
        skill = meta.get("skill_id", "?")[:19]
        tier = meta.get("tier", "?")
        failed = meta.get("stage_failed")
        installed = meta.get("installed_at")
        status = "FAILED" if failed else ("INSTALLED" if installed else "IN_PROGRESS")
        started = meta.get("started_at", "?")[:19]
        print(f"{run_id:<30} {skill:<20} {tier:>5} {status:<12} {started:<20}")

    print(f"\n{len(runs)} run(s) shown.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="clawagentskill",
        description="Agent & skill discovery, security scanning, and adoption for OpenClaw",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # find
    p_find = subparsers.add_parser("find", help="Search skills.sh + agent repos")
    p_find.add_argument("query", help="Natural language search query")
    p_find.add_argument("--max-results", type=int, default=10)
    p_find.add_argument("--agents-only", action="store_true", default=False)
    p_find.add_argument("--skills-only", action="store_true", default=False)
    p_find.set_defaults(func=_cmd_find)

    # adopt
    p_adopt = subparsers.add_parser("adopt", help="Full pipeline: discover -> scan -> install")
    p_adopt.add_argument("query", help="Search query or skill name")
    p_adopt.add_argument("--url", default="", help="Direct skills.sh or GitHub URL")
    p_adopt.add_argument("--scan-mode", choices=["quality", "efficiency", "simplicity"], default="quality")
    p_adopt.add_argument("--yes", "-y", action="store_true", default=False, help="Auto-approve")
    p_adopt.add_argument("--force", action="store_true", default=False, help="Install below thresholds")
    p_adopt.set_defaults(func=_cmd_adopt)

    # port
    p_port = subparsers.add_parser("port", help="Port Claude Code agent to OpenClaw SOUL.md")
    p_port.add_argument("url", help="GitHub raw URL to agent markdown file")
    p_port.add_argument("target", help="Target as department/agent-name")
    p_port.add_argument("--yes", "-y", action="store_true", default=False)
    p_port.set_defaults(func=_cmd_port)

    # scan
    p_scan = subparsers.add_parser("scan", help="Run 4 security scanners on a local file")
    p_scan.add_argument("path", help="Path to SKILL.md or SOUL.md")
    p_scan.add_argument("--json", dest="json_output", action="store_true", default=False)
    p_scan.set_defaults(func=_cmd_scan)

    # status
    p_status = subparsers.add_parser("status", help="Show recent adoption runs")
    p_status.add_argument("--limit", type=int, default=10)
    p_status.set_defaults(func=_cmd_status)

    return parser


def main() -> int:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)
