---
description: "Find the single biggest constraint in a client account"
argument-hint: "<ClientName>"
allowed-tools: 'Bash(python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account diagnose:*)'
---

The client name `$1` must match `^[A-Za-z0-9_-]+$` and nothing else may be appended; if it does not, refuse and ask the user for a valid name. Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account diagnose --client "$1"` and report the ranked findings. Read-only.
