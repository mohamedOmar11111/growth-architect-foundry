---
description: "Pull live Google/Meta campaigns for a client (read-only)"
argument-hint: "<ClientName>"
allowed-tools: Bash(python:*), Read
---

Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" live pull --client $ARGUMENTS`. If a platform shows FETCH FAILED, show the error and stop — do not treat it as an empty account. For pause/budget changes, use the foundry skill: show the exact change first and only add --confirm after the user explicitly approves.
