#!/usr/bin/env bash
# Install the Future AGI hook emitter for Kiro IDE.
#
#   ./install.sh <project-dir>   project hooks: <project>/.kiro/hooks/fi-hook-to-otlp.json
#   ./install.sh --user          global hooks:  ~/.kiro/hooks/fi-hook-to-otlp.json
#
# Copies emit.py + the Kiro IDE adapter into .kiro/fi-hook-to-otlp/ and writes
# the hook file. An existing hook file with the same name is never modified.
#
# Kiro IDE and Kiro CLI V3 both load every .kiro/hooks/*.json file (project and
# ~/.kiro/hooks/), so the Kiro IDE and Kiro CLI recipes cannot both be installed
# where one session would load both: the installer refuses instead.
#
# Uninstall: delete the hook file first, then the emitter directory:
#   rm .kiro/hooks/fi-hook-to-otlp.json && rm -r .kiro/fi-hook-to-otlp
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

# Refuse when a Kiro CLI recipe is installed in this scope or globally: both
# files would fire in every Kiro IDE and Kiro CLI session (double export, and
# CLI sessions labelled as IDE ones).
for dir in "$KIRO_DIR/hooks" "$HOME/.kiro/hooks"; do
  for other in "$dir/fi-hook-to-otlp-kiro-cli.json" "$dir/fi-hook-to-otlp.json"; do
    if [[ -e "$other" ]] && grep -q 'kiro_cli' "$other"; then
      echo "refusing to install Kiro IDE hooks: $other is the Kiro CLI recipe." >&2
      echo "Kiro IDE and Kiro CLI both load it, so every session would be exported twice." >&2
      echo "Trace one Kiro surface per hook scope; see the Kiro IDE page, 'Kiro CLI in the same project'." >&2
      exit 1
    fi
  done
done
if [[ -e "$HOOK_FILE" ]] && ! grep -q 'kiro_ide' "$HOOK_FILE"; then
  echo "refusing to install: $HOOK_FILE exists and is not the Kiro IDE recipe." >&2
  exit 1
fi

DEST="$KIRO_DIR/fi-hook-to-otlp"
mkdir -p "$DEST/adapters" "$KIRO_DIR/hooks"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/kiro_ide.py" "$DEST/adapters/"
echo "emitter: $DEST"

if [[ -e "$HOOK_FILE" ]]; then
  echo "kept existing $HOOK_FILE"
  if ! cmp -s "$TEMPLATE" "$HOOK_FILE"; then
    echo "  it differs from the shipped template; replace it with $TEMPLATE to get the current guarded commands."
  fi
else
  cp "$TEMPLATE" "$HOOK_FILE"
  echo "hooks:   $HOOK_FILE"
fi

echo
echo "Credentials: put FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Kiro may not see variables exported in your shell; the env file works either way."
