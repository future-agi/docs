#!/usr/bin/env bash
# Install the Future AGI hook emitter for Grok Build (the `grok` CLI/TUI).
#
#   ./install.sh
#
# Copies emit.py + the Grok Build adapter into ~/.grok/fi-hook-to-otlp/ and
# writes the personal hook file ~/.grok/hooks/futureagi.json if there is none.
# An existing file is never modified: the script prints the entries instead.
# Only ~/.grok/hooks/ is used, never a Claude Code or Cursor hook file, so
# sessions of those apps are not reported as Grok Build.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
GROK_DIR="$HOME/.grok"
DEST="$GROK_DIR/fi-hook-to-otlp"

mkdir -p "$DEST/adapters" "$GROK_DIR/hooks"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/grok_build.py" "$DEST/adapters/"
echo "emitter: $DEST"

if [[ -e "$GROK_DIR/hooks/futureagi.json" ]]; then
  echo "kept existing $GROK_DIR/hooks/futureagi.json; compare it with:"
  cat "$HERE/futureagi.json"
else
  cp "$HERE/futureagi.json" "$GROK_DIR/hooks/futureagi.json"
  echo "hooks:   $GROK_DIR/hooks/futureagi.json"
fi

echo
echo "Credentials: put FI_API_KEY, FI_SECRET_KEY and FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600), or export them before starting grok."
echo "Check the hooks loaded with: grok inspect"
