#!/usr/bin/env bash
# install.sh — install the Foundry skill into any agent's skills directory.
#
# Usage:
#   ./scripts/install.sh --dir ~/.claude/skills          # Claude Code
#   ./scripts/install.sh --dir /path/to/cursor/skills    # Cursor
#   ./scripts/install.sh --zip                           # Create uploadable zip
#
# The skill directory is self-contained: SKILL.md + references/ + foundry.py
# are all the agent needs. The engine (core/) is symlinked or copied alongside.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_NAME="growth-architect-foundry"
SKILL_SRC="$REPO_ROOT/skills/$SKILL_NAME"

usage() {
    echo "Usage: $0 --dir <target-dir> | --zip"
    echo ""
    echo "  --dir <dir>   Install skill into <dir>/$SKILL_NAME/"
    echo "  --zip         Create $SKILL_NAME.zip for manual upload"
    exit 1
}

TARGET_DIR=""
CREATE_ZIP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) TARGET_DIR="$2"; shift 2 ;;
        --zip) CREATE_ZIP=true; shift ;;
        *) usage ;;
    esac
done

if $CREATE_ZIP; then
    ZIP_PATH="$REPO_ROOT/$SKILL_NAME.zip"
    (cd "$REPO_ROOT" && zip -r "$ZIP_PATH" \
        "skills/$SKILL_NAME/" \
        "core/" \
        "foundry.py" \
        "01_Context_Vault/Agents/" \
        "02_Active_Clients/" \
        "hq.db" \
        "scripts/" \
        ".gitignore" \
        -x "*.pyc" "__pycache__/*" ".git/*")
    echo "Created $ZIP_PATH — upload to claude.ai or share directly."
    exit 0
fi

if [[ -z "$TARGET_DIR" ]]; then
    usage
fi

DEST="$TARGET_DIR/$SKILL_NAME"
mkdir -p "$DEST"
cp -r "$SKILL_SRC"/* "$DEST/"

# Symlink the engine so the skill can run commands
ln -sfn "$REPO_ROOT/core" "$DEST/core"
ln -sfn "$REPO_ROOT/foundry.py" "$DEST/foundry.py"
ln -sfn "$REPO_ROOT/01_Context_Vault" "$DEST/01_Context_Vault"
ln -sfn "$REPO_ROOT/02_Active_Clients" "$DEST/02_Active_Clients"
ln -sfn "$REPO_ROOT/hq.db" "$DEST/hq.db"
ln -sfn "$REPO_ROOT/scripts" "$DEST/scripts"

echo "Installed $SKILL_NAME to $DEST"
echo "Symlinked engine from $REPO_ROOT"
echo ""
echo "To use: open Claude Code / Cursor in any directory, or run:"
echo "  python $REPO_ROOT/foundry.py account audit --client Aurora_Skincare"