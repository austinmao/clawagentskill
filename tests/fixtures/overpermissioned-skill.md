---
name: test-overpermissioned
description: "Test fixture — filesystem write + network true (exfil-risk pattern)"
version: "1.0.0"
permissions:
  filesystem: write
  network: true
triggers:
  - command: /test-overpermissioned
metadata:
  openclaw:
    emoji: "🧪"
    requires:
      bins: ["python3", "curl"]
      env: ["SOME_API_KEY"]
---

# Test Fixture: Overpermissioned Skill

This skill intentionally declares both `filesystem: write` and `network: true`
to trigger the `exfil-risk` finding in the permission scanner.

## Steps

1. Read configuration data from disk
2. Process it with some logic
3. Write results to an output file
4. POST the summary to a reporting endpoint using curl
