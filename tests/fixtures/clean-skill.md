---
name: test-clean
description: "Test fixture — clean skill that passes all scanners"
version: "1.0.0"
permissions:
  filesystem: read
  network: false
triggers:
  - command: /test-clean
metadata:
  openclaw:
    emoji: "✅"
    requires:
      bins: ["python3"]
      env: []
---

# Test Fixture: Clean Skill

A minimal, clean skill that passes all security scanners.

## Steps

1. Read input from the configured path
2. Process the data
3. Return the result to the caller
