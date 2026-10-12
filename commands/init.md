---
description: "Create a new client (tenant) folder in your workspace"
argument-hint: "<ClientName>"
allowed-tools: Bash(python:*), Read
---

Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" setup init --client $ARGUMENTS` from the current directory (that directory is the workspace). Then walk the user through filling STRATEGY.md and .env. Never print secret values.
