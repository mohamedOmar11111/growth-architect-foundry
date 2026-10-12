---
description: "0-100 account health audit for a client"
argument-hint: "<ClientName>"
allowed-tools: 'Bash(python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account audit:*)'
---

The client name `$1` must match `^[A-Za-z0-9_-]+$` and nothing else may be appended; if it does not, refuse and ask the user for a valid name. Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account audit --client "$1"`, then summarise the score, weakest dimension and top 3 fixes. Read-only.
