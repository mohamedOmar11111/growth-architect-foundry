---
description: "Create a new client (tenant) folder in your workspace"
argument-hint: "<ClientName>"
allowed-tools: 'Bash(python "${CLAUDE_PLUGIN_ROOT}/foundry.py" setup init:*)'
---

The client name `$1` must match `^[A-Za-z0-9_-]+$` and nothing else may be appended; if it does not, refuse and ask the user for a valid name. Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" setup init --client "$1"` from the current directory (that directory is the workspace). Then walk the user through filling STRATEGY.md and .env. Never print secret values.
