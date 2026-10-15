#!/usr/bin/env bash
# Install the Future AGI hook emitter for the Antigravity IDE.
#
#   ./install.sh <project-dir>   workspace hooks: <project>/.agents/hooks.json
#   ./install.sh --user          global hooks:    ~/.gemini/config/hooks.json
#
# Copies emit.py + the Antigravity adapter next to the hooks file and writes
# hooks.json if there is none. An existing hooks.json is never modified: the
# script prints the entry to merge instead.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
# Antigravity runs hook commands in the folder that contains hooks.json, so one
# template (python3 fi-hook-to-otlp/emit.py ...) works for both locations.
TEMPLATE="$HERE/hooks.json"

if [[ "${1:-}" == "--user" ]]; then
  HOOKS_DIR="$HOME/.gemini/config"
elif [[ -n "${1:-}" ]]; then
  HOOKS_DIR="$(cd "$1" && pwd)/.agents"
else
  echo "usage: $0 <project-dir> | --user" >&2
  exit 2
fi

DEST="$HOOKS_DIR/fi-hook-to-otlp"
mkdir -p "$DEST/adapters"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/antigravity.py" "$DEST/adapters/"
echo "emitter: $DEST"

if [[ -e "$HOOKS_DIR/hooks.json" ]]; then
  echo "kept existing $HOOKS_DIR/hooks.json; add this entry to its top-level object:"
  cat "$TEMPLATE"
else
  cp "$TEMPLATE" "$HOOKS_DIR/hooks.json"
  echo "hooks:   $HOOKS_DIR/hooks.json"
fi

echo
echo "Credentials: put FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Apps started from the Dock do not see your shell env."
