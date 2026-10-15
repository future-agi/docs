#!/usr/bin/env bash
# Install the Future AGI hook emitter for Kiro CLI.
#
#   ./install.sh <project-dir>   project hooks: <project>/.kiro/hooks/fi-hook-to-otlp.json
#   ./install.sh --user          global hooks:  ~/.kiro/hooks/fi-hook-to-otlp.json
#
# Copies emit.py + the Kiro CLI adapter into .kiro/fi-hook-to-otlp/ and writes
# the hook file. An existing hook file with the same name is never modified.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"

if [[ "${1:-}" == "--user" ]]; then
  KIRO_DIR="${KIRO_HOME:-$HOME/.kiro}"
  TEMPLATE="$HERE/fi-hook-to-otlp.user.json"
elif [[ -n "${1:-}" ]]; then
  KIRO_DIR="$(cd "$1" && pwd)/.kiro"
  TEMPLATE="$HERE/fi-hook-to-otlp.json"
else
  echo "usage: $0 <project-dir> | --user" >&2
  exit 2
fi

HOOK_FILE="$KIRO_DIR/hooks/fi-hook-to-otlp-kiro-cli.json"
if [[ -e "$KIRO_DIR/hooks/fi-hook-to-otlp.json" ]] && grep -q 'kiro_ide' "$KIRO_DIR/hooks/fi-hook-to-otlp.json"; then
  echo "refusing to install Kiro CLI hooks: $KIRO_DIR/hooks/fi-hook-to-otlp.json is configured for Kiro IDE" >&2
  echo "Use the CLI-only agent-profile hooks field when IDE hooks share this scope." >&2
  exit 1
fi
DEST="$KIRO_DIR/fi-hook-to-otlp-kiro-cli"
mkdir -p "$DEST/adapters" "$KIRO_DIR/hooks"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/kiro_cli.py" "$DEST/adapters/"
echo "emitter: $DEST"

if [[ -e "$HOOK_FILE" ]]; then
  echo "kept existing $HOOK_FILE"
else
  if [[ "${1:-}" == "--user" ]]; then
    cp "$TEMPLATE" "$HOOK_FILE"
  else
    sed "s#\.kiro/fi-hook-to-otlp#\.kiro/fi-hook-to-otlp-kiro-cli#g" "$TEMPLATE" > "$HOOK_FILE"
  fi
  echo "hooks:   $HOOK_FILE"
fi

echo
echo "Credentials: put FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Variables exported in the shell that runs kiro-cli also work."
echo "Install either --user or a project hook, not both: Kiro merges global and workspace hooks."
