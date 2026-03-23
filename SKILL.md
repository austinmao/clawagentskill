---
name: clawagentskill
description: "Adopt a skill from the marketplace / port a Claude Code agent to OpenClaw / scan a skill for security issues / find available skills and agents"
version: "0.1.0"
permissions:
  filesystem: write
  network: true
triggers:
  - command: /clawagentskill
metadata:
  openclaw:
    emoji: "🔍"
    requires:
      bins: ["python3", "npx"]
      env: []
      os: ["darwin", "linux"]
---

# clawagentskill — Agent & Skill Discovery for OpenClaw

Discover, scan, and adopt skills from the marketplace or port Claude Code agents to OpenClaw format.

## Commands

```
/clawagentskill find "payment processing"     — Search skills.sh + agent repos
/clawagentskill adopt "stripe integration"     — Full pipeline: discover → scan → approve → install
/clawagentskill port <github-url> dept/name    — Port Claude Code agent to SOUL.md
/clawagentskill scan path/to/SKILL.md          — Run 4 security scanners
/clawagentskill status                         — Show recent adoption runs
```

## Security Pipeline

Every adoption runs 4 parallel security scanners:
1. **Pre-filter** — ClawHavoc toxic pattern detection (C2 IPs, malware domains)
2. **Permission** — Exfiltration risk analysis (filesystem:write + network:true)
3. **Config** — Gate compliance (undeclared env vars, hardcoded secrets)
4. **Injection** — Prompt injection detection (5 categories including role hijacking)

Optional: Snyk agent-scan integration when `SNYK_TOKEN` is set.

## Tier Classification

- **Tier A** — Trusted publishers (openclaw, anthropic): scanners skipped
- **Tier B** — Community trusted (>=10K installs): efficiency scan mode
- **Tier C** — Default: full quality scan mode

## Install

```bash
pip install clawagentskill
```
