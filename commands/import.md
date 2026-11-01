---
description: "Import an Ads Manager CSV export for a client (no ad-account login), then audit it"
argument-hint: "<ClientName> <path-to-export.csv>"
allowed-tools: 'Bash(python "${CLAUDE_PLUGIN_ROOT}/foundry.py" campaigns import:*), Bash(python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account audit:*), Bash(python "${CLAUDE_PLUGIN_ROOT}/foundry.py" setup init:*)'
---

The client name `$1` must match `^[A-Za-z0-9_-]+$` and nothing else may be appended; if it does not, refuse and ask the user for a valid name. `$2` must be a path to an existing `.csv` or `.txt` export file; if it is missing or the file does not exist, ask the user for it.

1. If the client folder `02_Active_Clients/$1` does not exist in the current directory, run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" setup init --client "$1"` first.
2. Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" campaigns import --client "$1" --file "$2"`. Show any warnings it prints (missing columns, mixed currencies, Meta "Results" basis) in plain words.
3. Run `python "${CLAUDE_PLUGIN_ROOT}/foundry.py" account audit --client "$1"` and summarise the score, the call per campaign, and the top 3 fixes.
4. Offer `/foundry:report $1 ar` or `/foundry:report $1 en` for the client-ready version.

Read-only: this never touches a live ad account. Do not invent numbers the audit did not print.
