#!/usr/bin/env bash
# Install the Future AGI hook emitter for Kiro IDE.
#
#   ./install.sh <project-dir>   project hooks: <project>/.kiro/hooks/fi-hook-to-otlp.json
#   ./install.sh --user          global hooks:  ~/.kiro/hooks/fi-hook-to-otlp.json
#
# Copies emit.py + the Kiro IDE adapter into .kiro/fi-hook-to-otlp/ and writes
# the hook file. An existing hook file with the same name is never modified.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"

if [[ "${1:-}" == "--user" ]]; then
  KIRO_DIR="$HOME/.kiro"
  TEMPLATE="$HERE/fi-hook-to-otlp.user.json"
elif [[ -n "${1:-}" ]]; then
  KIRO_DIR="$(cd "$1" && pwd)/.kiro"
  TEMPLATE="$HERE/fi-hook-to-otlp.json"
else
  echo "usage: $0 <project-dir> | --user" >&2
  exit 2
fi

HOOK_FILE="$KIRO_DIR/hooks/fi-hook-to-otlp.json"
if [[ -e "$HOOK_FILE" ]] && grep -q 'kiro_cli' "$HOOK_FILE"; then
  echo "refusing to install Kiro IDE hooks: $HOOK_FILE is configured for Kiro CLI" >&2
  echo "Use one Kiro adapter per hook scope, or add the IDE hooks manually under a separate project scope." >&2
  exit 1
fi
DEST="$KIRO_DIR/fi-hook-to-otlp"
mkdir -p "$DEST/adapters" "$KIRO_DIR/hooks"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/kiro_ide.py" "$DEST/adapters/"
echo "emitter: $DEST"

if [[ -e "$KIRO_DIR/hooks/fi-hook-to-otlp.json" ]]; then
  echo "kept existing $KIRO_DIR/hooks/fi-hook-to-otlp.json"
else
  cp "$TEMPLATE" "$KIRO_DIR/hooks/fi-hook-to-otlp.json"
  echo "hooks:   $KIRO_DIR/hooks/fi-hook-to-otlp.json"
fi

echo
echo "Credentials: put FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Kiro started from the Dock does not see your shell env."
