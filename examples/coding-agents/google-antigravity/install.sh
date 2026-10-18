#!/usr/bin/env bash
# Install the Future AGI hook emitter for the Antigravity IDE and Antigravity CLI (agy).
#
#   ./install.sh <project-dir>   workspace hooks: <project>/.agents/hooks.json
#   ./install.sh --user          global hooks:    ~/.gemini/config/hooks.json
#
# Copies emit.py + the Antigravity adapter next to the hooks file and writes
# hooks.json if there is none. An existing hooks.json is never modified: the
# script prints the "fi-hook-to-otlp" entry to add to it instead.
#
# Uninstall: remove the "fi-hook-to-otlp" entry from hooks.json (or delete the
# file if it holds nothing else) first, then the fi-hook-to-otlp/ directory.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"

if [[ "${1:-}" == "--user" ]]; then
  HOOKS_DIR="$HOME/.gemini/config"
  # Absolute ("$HOME/...") so the command works whatever the working directory.
  TEMPLATE="$HERE/hooks.user.json"
elif [[ -n "${1:-}" ]]; then
  HOOKS_DIR="$(cd "$1" && pwd)/.agents"
  # Antigravity runs hook commands in the folder that contains hooks.json, so the
  # workspace file uses a path relative to .agents/ and can be committed.
  TEMPLATE="$HERE/hooks.json"
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
  echo "kept existing $HOOKS_DIR/hooks.json"
  python3 -B - "$HOOKS_DIR/hooks.json" "$TEMPLATE" <<'PY'
import json, sys
existing_path, template_path = sys.argv[1], sys.argv[2]
entry = json.load(open(template_path, encoding="utf-8"))["fi-hook-to-otlp"]
try:
    existing = json.load(open(existing_path, encoding="utf-8"))
except ValueError:
    existing = None
if isinstance(existing, dict) and "fi-hook-to-otlp" in existing:
    if existing["fi-hook-to-otlp"] != entry:
        print("  its \"fi-hook-to-otlp\" entry differs from the shipped one; replace it with:")
        print(json.dumps({"fi-hook-to-otlp": entry}, indent=2)[2:-2])
else:
    print("  add this member to its top-level object (next to your other named hooks):")
    print(json.dumps({"fi-hook-to-otlp": entry}, indent=2)[2:-2])
PY
else
  cp "$TEMPLATE" "$HOOKS_DIR/hooks.json"
  echo "hooks:   $HOOKS_DIR/hooks.json"
fi

echo
echo "Credentials: put FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Antigravity may not see variables exported in your shell; the env file works either way."
