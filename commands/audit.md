---
description: "0-100 account health audit for a client"
argument-hint: "<ClientName>"
allowed-tools: Bash(python:*), Read
---

Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account audit --client $ARGUMENTS`, then summarise the score, weakest dimension and top 3 fixes. Read-only.
