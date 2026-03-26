# clawagentskill

Agent & skill discovery, security scanning, and adoption for OpenClaw.

## Why not just `npx skills add`?

`npx skills add` downloads and installs a skill — but it doesn't scan it for supply chain attacks, classify the publisher's trust level, enforce approval gates, or integrate with your governance toolchain. After ClawHavoc compromised ~20% of ClawHub (824+ malicious skills), blind installation is a security risk.

`clawagentskill` wraps the install step with:
- **4 parallel security scanners** (ClawHavoc detection, permission analysis, config gate compliance, prompt injection)
- **Tier classification** (trusted publishers skip scans; community skills get full audits)
- **Approval gates** (preview before install; auto-approve for CI)
- **Agent porting** (Claude Code agents → OpenClaw SOUL.md with injection scanning)
- **Governance chain** (optional ClawScaffold/ClawSpec/ClawWrap/Paperclip integration)

## Install

```bash
pip install clawagentskill
```

## Quick Start

```bash
# Discover available skills and agents
python3 -m clawagentskill find "payment processing"

# Adopt a skill with full security pipeline
python3 -m clawagentskill adopt "stripe integration"

# Port a Claude Code agent to OpenClaw
python3 -m clawagentskill port \
  https://raw.githubusercontent.com/VoltAgent/awesome-claude-code-subagents/main/categories/09-meta-orchestration/error-coordinator.md \
  platform/error-coordinator

# Scan a local skill for security issues
python3 -m clawagentskill scan path/to/SKILL.md

# View recent adoption runs
python3 -m clawagentskill status
```

## Usage

### `find` — Search for skills and agents

```bash
python3 -m clawagentskill find "email delivery"
python3 -m clawagentskill find "error handling" --agents-only
python3 -m clawagentskill find "stripe" --skills-only --max-results 5
```

Searches skills.sh marketplace, configured GitHub agent repositories, and the local workspace. Returns ranked results with publisher, install count, and trust tier.

### `adopt` — Install with security scanning

```bash
python3 -m clawagentskill adopt "stripe integration"
python3 -m clawagentskill adopt "resend" --url https://skills.sh/wshobson/agents/stripe-integration
python3 -m clawagentskill adopt "openclaw/resend"  # Tier A — scanners skipped
python3 -m clawagentskill adopt "some-skill" --yes --scan-mode efficiency
```

Runs the 16-stage adoption pipeline: search → download → prefilter → parallel scan → decide → approval → install/rebuild → governance.

### `port` — Convert Claude Code agents to OpenClaw

```bash
python3 -m clawagentskill port <github-raw-url> department/agent-name
```

Fetches the agent, translates via SkillKit (with built-in fallback), runs injection scanning, and installs to `agents/<dept>/<name>/SOUL.md`.

### `scan` — Security audit a local file

```bash
python3 -m clawagentskill scan skills/my-skill/SKILL.md
python3 -m clawagentskill scan skills/my-skill/SKILL.md --json
```

Runs all 4 scanners and reports findings. Exit 0 if clean, exit 1 if warnings or blocks found.

### `status` — View adoption history

```bash
python3 -m clawagentskill status
python3 -m clawagentskill status --limit 5
```

## Security Pipeline

| Scanner | Detects | Severity |
|---------|---------|----------|
| Pre-filter | ClawHavoc C2 IPs, malware domains, ClawHub CLI | BLOCKED |
| Permission | filesystem:write + network:true exfiltration risk | WARN |
| Config | Undeclared env vars, hardcoded secrets, ClawHub origin files | WARN/BLOCKED |
| Injection | Prompt overrides, role hijacking, covert exfiltration, hidden instructions | WARN/BLOCKED |
| Snyk (optional) | Known vulnerabilities via `snyk-agent-scan` | WARN |

## Tier Classification

| Tier | Criteria | Scan Mode |
|------|----------|-----------|
| A | Publisher in hardcoded trusted list (openclaw, anthropic) | Simplicity (skipped) |
| B | >= 10,000 marketplace installs | Efficiency |
| C | Everything else | Quality (full audit) |

## Configuration

Create `clawagentskill.yaml` in your workspace root (optional — sensible defaults apply):

```yaml
trusted_publishers:
  - openclaw
  - anthropic

thresholds:
  tier_b_installs: 10000

agent_registries:
  - repo: VoltAgent/awesome-claude-code-subagents
    type: claude-code
    path: categories/

run_dir: memory/skill-adopt-runs

scanners:
  - prefilter
  - permission
  - config
  - injection
```

## Integrations (Optional)

These governance modules activate automatically when their dependencies are present:

- **ClawScaffold** — catalog registration
- **ClawSpec** — test scenario auditing
- **ClawWrap** — outbound target validation
- **Paperclip** — governance issue tracking

## OpenClaw Gateway Plugin

ClawAgentSkill ships with a gateway plugin that registers the `clawagentskill` tool directly in the OpenClaw gateway. The plugin delegates all actions to the Python CLI via `child_process`.

### Installation

1. Copy the `extensions/clawagentskill/` directory into your OpenClaw workspace:

```bash
cp -r extensions/clawagentskill/ ~/.openclaw/extensions/clawagentskill/
```

2. Register the plugin in your `~/.openclaw/openclaw.json`:

```json
{
  "extensions": {
    "clawagentskill": {
      "repoRoot": "/path/to/your/workspace",
      "timeoutMs": 60000
    }
  }
}
```

3. Restart the gateway:

```bash
openclaw gateway restart
```

### Plugin Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `repoRoot` | string | `$OPENCLAW_WORKSPACE` or `cwd` | Workspace root containing the clawagentskill package |
| `pythonBin` | string | `<repoRoot>/clawpipe/.venv/bin/python` | Path to Python binary |
| `timeoutMs` | integer | `60000` | CLI execution timeout in milliseconds |

### Supported Actions

`find`, `adopt`, `port`, `scan`, `status`, `state-init`, `validate-prereqs`, `get-field`

See the [openclaw.plugin.json](extensions/clawagentskill/openclaw.plugin.json) for the full config schema.

## ClawSuite

This package is part of **ClawSuite** — the OpenClaw agent infrastructure toolkit.

| Package | Description | Repo |
|---|---|---|
| **ClawPipe** | Config-driven pipeline orchestration | [austinmao/clawpipe](https://github.com/austinmao/clawpipe) |
| **ClawSpec** | Contract-first testing for skills & agents | [austinmao/clawspec](https://github.com/austinmao/clawspec) |
| **ClawWrap** | Outbound policy & conformance engine | [austinmao/clawwrap](https://github.com/austinmao/clawwrap) |
| **ClawAgentSkill** | Skill discovery, scanning & adoption | [austinmao/clawagentskill](https://github.com/austinmao/clawagentskill) |
| **ClawScaffold** | Agent/skill scaffold interviews | [austinmao/clawscaffold](https://github.com/austinmao/clawscaffold) |
| **ClawInterview** | Pipeline interview compilation & execution | *(coming soon)* |

All packages include OpenClaw gateway plugins for autonomous agent access.

## License

Apache 2.0
