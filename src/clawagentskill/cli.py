"""CLI interface for clawagentskill.

Provides 9 subcommands: find, adopt, port, scan, status,
skill-sync, state-init, validate-prereqs, get-field.
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


def _render_candidate_table(candidates: list[dict]) -> None:
    """Print a short candidate preview table to stderr for pre-install review."""
    if not candidates:
        return
    print(
        f"\n{'#':<3} {'Name':<30} {'Publisher':<18} {'Installs':>10} {'Tier':<5}",
        file=sys.stderr,
    )
    print("-" * 72, file=sys.stderr)
    for i, c in enumerate(candidates, 1):
        name = str(c.get("name", "?"))[:29]
        pub = str(c.get("publisher", "?"))[:17]
        installs = c.get("install_count", 0)
        tier = c.get("tier", "C")
        print(f"{i:<3} {name:<30} {pub:<18} {installs:>10} {tier:<5}", file=sys.stderr)


def _prompt_candidate_choice(
    candidates: list[dict], default: int = 1
) -> dict | None:
    """Prompt user to pick one candidate by number. Returns None on cancel."""
    try:
        raw = input(f"\nChoose [1-{len(candidates)}, or 'n' to cancel] (default {default}): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if raw.lower() in ("n", "no", "cancel"):
        return None
    if not raw:
        return candidates[default - 1]
    try:
        idx = int(raw)
    except ValueError:
        return None
    if idx < 1 or idx > len(candidates):
        return None
    return candidates[idx - 1]


def _cmd_adopt(args: argparse.Namespace) -> int:
    """Full pipeline: discover -> scan -> approve -> install.

    Supports disambiguation flags:
      --exact              require exact slug match, fail if absent
      --publisher <name>   restrict candidates to a specific publisher
      --dry-run            print resolution plan, exit without installing
      --show-top <N>       preview top-N candidates before install
    """
    from clawagentskill.config import load_config
    from clawagentskill.discover import local as local_discover
    from clawagentskill.discover import skills_sh
    from clawagentskill.pipeline import adopt_sync
    from clawagentskill.select import (
        normalize_query,
        rank_candidates,
        select_with_confidence,
    )

    query = args.query or ""
    exact = getattr(args, "exact", False)
    publisher = getattr(args, "publisher", None)
    dry_run = getattr(args, "dry_run", False)
    show_top = getattr(args, "show_top", 3)

    # Direct-URL adoption path: --url without query must be allowed so callers
    # that already know the upstream location (e.g., LLM tool use with skill_id)
    # can install without first running a search. Reject only when neither
    # query nor --url is provided.
    if not query and not args.url:
        print(
            "adopt: either a query or --url is required "
            "(e.g., 'clawagentskill adopt fireflies' or "
            "'clawagentskill adopt --url https://github.com/<org>/<repo>').",
            file=sys.stderr,
        )
        return 2

    # Resolve candidates up-front so we can honour --exact/--publisher/
    # --dry-run/--show-top without going through the install pipeline.
    # These knobs only take effect when the user did not pass --url.
    if not args.url and (exact or publisher or dry_run or show_top):
        config = load_config()
        workspace = Path.cwd()
        registry = skills_sh.search(query)
        local_results = local_discover.search(query, workspace)
        candidates: list[dict] = registry + local_results

        if not candidates:
            print(f"No candidates found for query: {query!r}", file=sys.stderr)
            return 1

        ranked = rank_candidates(candidates, query, publisher=publisher)
        if publisher and not ranked:
            print(
                f"No candidates match publisher={publisher!r} for query {query!r}",
                file=sys.stderr,
            )
            return 1

        preview = ranked[: max(1, show_top)]
        _render_candidate_table(preview)

        try:
            result = select_with_confidence(
                candidates, query, exact=exact, publisher=publisher
            )
        except ValueError as exc:
            print(f"Selection failed: {exc}", file=sys.stderr)
            return 1

        primary_slug, tokens, publisher_hint = normalize_query(query)
        effective_publisher = publisher or publisher_hint

        print(
            f"\nResolved: {result.candidate.get('publisher', '?')}/"
            f"{result.candidate.get('name', '?')}",
            file=sys.stderr,
        )
        # Publisher/name display looks like a GitHub org/repo slug — it isn't.
        # Print the real install_ref + install_url so LLMs and operators have
        # an unambiguous upstream identifier when they need to retry or
        # construct a direct-URL fallback. Regression: 2026-04-24 Ceremonia
        # tenant Telegram — LLM read "Resolved: membranedev/fireflies",
        # assumed github.com/membranedev/fireflies, and hallucinated a
        # non-existent repo. Real install_ref was
        # membranedev/application-skills@fireflies.
        install_ref = result.candidate.get("install_ref", "")
        install_url = result.candidate.get("install_url", "")
        if install_ref:
            print(f"  install_ref: {install_ref}", file=sys.stderr)
        if install_url:
            print(f"  install_url: {install_url}", file=sys.stderr)
        print(
            f"Confidence: {result.confidence} ({result.reason})",
            file=sys.stderr,
        )
        if effective_publisher:
            print(f"Publisher filter: {effective_publisher}", file=sys.stderr)

        if dry_run:
            print("\n(dry-run) no install performed.", file=sys.stderr)
            return 0

        # Low confidence + not --yes -> prompt; --yes alone should not
        # auto-install an ambiguous match (that's the original bug).
        # When a non-default --show-top is passed without --yes, also prompt.
        needs_prompt = result.confidence == "low" or (
            not args.yes and (exact or publisher or show_top != 3)
        )
        if needs_prompt:
            chosen = _prompt_candidate_choice(preview, default=1)
            if chosen is None:
                print("Cancelled.", file=sys.stderr)
                return 2
            # User explicitly confirmed; forward original query to pipeline
            # (pipeline re-searches and selects with its own ranking).
            forwarded_query = query
            forwarded_url = chosen.get("install_url") or args.url
        else:
            forwarded_query = query
            forwarded_url = args.url

        result_dict = adopt_sync(
            forwarded_query,
            url=forwarded_url,
            scan_mode=args.scan_mode,
            auto_approve=args.yes,
            force=args.force,
            target_root=Path(args.target) if getattr(args, "target", None) else None,
        )
    else:
        result_dict = adopt_sync(
            query,
            url=args.url,
            scan_mode=args.scan_mode,
            auto_approve=args.yes,
            force=args.force,
            target_root=Path(args.target) if getattr(args, "target", None) else None,
        )

    status = result_dict.get("status", "error")
    if status == "installed":
        print(f"\nInstalled: {result_dict.get('target_path')}")
        return 0
    elif status == "blocked":
        print(f"\nBLOCKED: {result_dict.get('message')}", file=sys.stderr)
        return 1
    elif status == "rejected":
        print(f"\nRejected: {result_dict.get('message')}", file=sys.stderr)
        return 2
    else:
        print(f"\nError: {result_dict.get('message')}", file=sys.stderr)
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


def _cmd_state_init(args: argparse.Namespace) -> int:
    """Create a run directory with meta.yaml and emit JSON envelope."""
    from clawagentskill.config import load_config
    from clawagentskill.state import StateManager

    config = load_config()
    base = Path(args.run_dir_base) if args.run_dir_base else Path.cwd() / config.run_dir
    state = StateManager.create_run(
        base, args.query, skill_url=args.skill_url, scan_mode=args.scan_mode,
    )
    print(json.dumps({"run_dir": str(state.run_dir)}))
    return 0


def _cmd_validate_prereqs(args: argparse.Namespace) -> int:
    """Check that required binaries (npx, python3) exist on PATH."""
    import shutil

    required_bins = ["npx", "python3"]
    missing = [b for b in required_bins if not shutil.which(b)]
    if missing:
        print(f"Missing: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


def _cmd_get_field(args: argparse.Namespace) -> int:
    """Read a single field from meta.yaml in a run directory."""
    from clawagentskill.state import StateManager

    state = StateManager(Path(args.run_dir))
    meta = state.load_meta()
    value = meta.get(args.key)
    if value is None:
        print(f"ERROR: key '{args.key}' not found", file=sys.stderr)
        return 1
    print(str(value))
    return 0


def _cmd_skill_sync(args: argparse.Namespace) -> int:
    """Sync skills from repo to agent workspace directories."""
    from clawagentskill.sync import sync_agent_skills

    repo_root = Path.cwd()
    result = sync_agent_skills(
        repo_root,
        agent_filter=args.agent,
        dry_run=args.dry_run,
        clean=args.clean,
    )

    status = result.get("status", "error")
    if status == "error":
        print(f"Error: {result.get('message')}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
        return 0

    # Human-readable output
    for agent_info in result.get("agents", []):
        agent_id = agent_info["agent"]
        actions = agent_info.get("actions", [])
        if not actions:
            print(f"  {agent_id}: OK ({agent_info['skills_declared']} skills)")
            continue
        print(f"  {agent_id}:")
        for a in actions:
            action = a["action"]
            skill = a["skill"]
            if action == "copied":
                print(f"    COPY: {skill}")
            elif action == "updated":
                print(f"    UPDATE: {skill}")
            elif action == "removed":
                print(f"    REMOVE: {skill}")
            elif action == "not_found":
                print(f"    WARN: {skill} not found in repo")

    totals = result.get("totals", {})
    prefix = "(dry-run) " if result.get("dry_run") else ""
    print(f"\n{prefix}Agents: {result.get('agents_synced', 0)}"
          f" | Copied: {totals.get('copied', 0)}"
          f" | Unchanged: {totals.get('unchanged', 0)}"
          f" | Missing: {totals.get('missing', 0)}"
          f" | Removed: {totals.get('removed', 0)}")
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
    p_adopt.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search query or skill name (optional if --url is provided)",
    )
    p_adopt.add_argument("--url", default="", help="Direct skills.sh or GitHub URL")
    p_adopt.add_argument("--scan-mode", choices=["quality", "efficiency", "simplicity"], default="quality")
    p_adopt.add_argument("--yes", "-y", action="store_true", default=False, help="Auto-approve")
    p_adopt.add_argument("--force", action="store_true", default=False, help="Install below thresholds")
    p_adopt.add_argument(
        "--exact", action="store_true", default=False,
        help="Require exact skill name match; fail if absent",
    )
    p_adopt.add_argument(
        "--publisher", default=None,
        help="Restrict candidates to a specific publisher (e.g. membranedev)",
    )
    p_adopt.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Print resolution plan and exit without installing",
    )
    p_adopt.add_argument(
        "--show-top", type=int, default=3,
        help="Number of top candidates to preview before install (default 3)",
    )
    p_adopt.add_argument(
        "--target", default=None,
        help="Override install target root (default: $OPENCLAW_WORKSPACE/skills or $HOME/.openclaw/skills)",
    )
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

    # skill-sync
    p_skill_sync = subparsers.add_parser(
        "skill-sync",
        help="Sync skills from repo to agent workspace directories",
    )
    p_skill_sync.add_argument(
        "--agent", default=None,
        help="Only sync this agent (e.g., executive/ceo)",
    )
    p_skill_sync.add_argument("--dry-run", action="store_true", default=False)
    p_skill_sync.add_argument(
        "--clean", action="store_true", default=False,
        help="Remove undeclared skills from agent workspaces",
    )
    p_skill_sync.add_argument(
        "--json", dest="json_output", action="store_true", default=False,
    )
    p_skill_sync.set_defaults(func=_cmd_skill_sync)

    # -- Lobster-compatible subcommands --

    # state-init
    p_state_init = subparsers.add_parser(
        "state-init", help="Create run directory with meta.yaml (Lobster compat)",
    )
    p_state_init.add_argument("--query", required=True, help="Search query")
    p_state_init.add_argument("--skill-url", default="", help="Direct skills.sh or GitHub URL")
    p_state_init.add_argument(
        "--scan-mode", default="quality",
        choices=["quality", "efficiency", "simplicity"],
        help="Scan mode override",
    )
    p_state_init.add_argument(
        "--run-dir-base", default=None,
        help="Base directory for runs (default: memory/skill-adopt-runs relative to cwd)",
    )
    p_state_init.set_defaults(func=_cmd_state_init)

    # validate-prereqs
    p_validate = subparsers.add_parser(
        "validate-prereqs", help="Check required binaries exist on PATH (Lobster compat)",
    )
    p_validate.add_argument("--run-dir", required=True, help="Path to run directory")
    p_validate.set_defaults(func=_cmd_validate_prereqs)

    # get-field
    p_get_field = subparsers.add_parser(
        "get-field", help="Read a field from meta.yaml in a run directory (Lobster compat)",
    )
    p_get_field.add_argument("--run-dir", required=True, help="Path to run directory")
    p_get_field.add_argument("--key", required=True, help="Field name to read from meta.yaml")
    p_get_field.set_defaults(func=_cmd_get_field)

    return parser


def main() -> int:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)
