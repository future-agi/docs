#!/usr/bin/env bash
# Install the Future AGI hook emitter for Cursor.
#
#   ./install.sh <project-dir>   project hooks: <project>/.cursor/hooks.json
#   ./install.sh --user          user hooks:    ~/.cursor/hooks.json
#
# Copies emit.py + the Cursor adapter into .cursor/hooks/fi-hook-to-otlp/ and
# writes hooks.json if there is none. An existing hooks.json is never
# modified: the script prints the entries to merge instead.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"

if [[ "${1:-}" == "--user" ]]; then
  CURSOR_DIR="$HOME/.cursor"
  TEMPLATE="$HERE/hooks.user.json"
elif [[ -n "${1:-}" ]]; then
  CURSOR_DIR="$(cd "$1" && pwd)/.cursor"
  TEMPLATE="$HERE/hooks.json"
else
  echo "usage: $0 <project-dir> | --user" >&2
  exit 2
fi

DEST="$CURSOR_DIR/hooks/fi-hook-to-otlp"
mkdir -p "$DEST/adapters"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/cursor.py" "$DEST/adapters/"
echo "emitter: $DEST"

if [[ -e "$CURSOR_DIR/hooks.json" ]]; then
  echo "kept existing $CURSOR_DIR/hooks.json; merge these entries into its \"hooks\" object:"
  cat "$TEMPLATE"
else
  cp "$TEMPLATE" "$CURSOR_DIR/hooks.json"
  echo "hooks:   $CURSOR_DIR/hooks.json"
fi

echo
echo "Credentials: export FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in the environment"
echo "that starts Cursor, or put them in ~/.config/fi-hook-to-otlp/env (chmod 600)."
