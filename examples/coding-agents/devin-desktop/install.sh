#!/usr/bin/env bash
# Install the Future AGI hook emitter for Devin Desktop's Cascade agent.
#
#   ./install.sh
#
# Copies emit.py + the Devin Desktop adapter into
# ~/.codeium/windsurf/fi-hook-to-otlp/ and writes the user-level Cascade hook
# file ~/.codeium/windsurf/hooks.json if there is none. An existing hooks.json
# is never modified: the script prints the entries to merge instead.
# post_cascade_response_with_transcript is never registered.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
HOOK_DIR="$HOME/.codeium/windsurf"
DEST="$HOOK_DIR/fi-hook-to-otlp"

mkdir -p "$DEST/adapters"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/devin_desktop.py" "$DEST/adapters/"
echo "emitter: $DEST"

if [[ -e "$HOOK_DIR/hooks.json" ]]; then
  echo "kept existing $HOOK_DIR/hooks.json; merge these entries into its \"hooks\" object:"
  cat "$HERE/hooks.json"
else
  cp "$HERE/hooks.json" "$HOOK_DIR/hooks.json"
  echo "hooks:   $HOOK_DIR/hooks.json"
fi

echo
echo "Credentials: put FI_API_KEY, FI_SECRET_KEY and FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Devin Desktop started from the"
echo "Dock may not see variables exported in your shell."
echo "To uninstall: remove the entries from $HOOK_DIR/hooks.json first, then delete $DEST."
