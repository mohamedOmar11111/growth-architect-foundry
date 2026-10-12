---
description: "Decision-first client report (EN or AR)"
argument-hint: "<ClientName> [--lang ar]"
allowed-tools: Bash(python:*), Read
---

Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account report --client $ARGUMENTS`. If no --lang was given, ask the user whether the client reads English or Arabic. Read-only.
