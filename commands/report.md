---
description: "Decision-first client report (EN or AR)"
argument-hint: "<ClientName> [en|ar]"
allowed-tools: 'Bash(python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account report:*)'
---

The client name `$1` must match `^[A-Za-z0-9_-]+$` and nothing else may be appended; if it does not, refuse and ask the user for a valid name. If `$2` is exactly `en` or `ar`, run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account report --client "$1" --lang "$2"`; otherwise ask the user which language the client reads, then run it. Read-only.
