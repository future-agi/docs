#!/usr/bin/env bash
# Install the Future AGI hook emitter for Kiro CLI.
#
#   ./install.sh <project-dir>     project hooks: <project>/.kiro/hooks/fi-hook-to-otlp-kiro-cli.json
#   ./install.sh --user            global hooks:  ${KIRO_HOME:-~/.kiro}/hooks/fi-hook-to-otlp-kiro-cli.json
#   ./install.sh --agent-profile   emitter only, in ${KIRO_HOME:-~/.kiro}/fi-hook-to-otlp-kiro-cli/;
#                                  prints the "hooks" entries to paste into a CLI agent profile
#
# Copies emit.py + the Kiro CLI adapter into .kiro/fi-hook-to-otlp-kiro-cli/ and
# writes the hook file. An existing hook file with the same name is never modified.
#
# Kiro CLI V3 and Kiro IDE both load every .kiro/hooks/*.json file (project and
# global), so this installer refuses where the Kiro IDE recipe is installed, and
# refuses a second copy of this recipe in the other scope (Kiro merges global and
# project hooks, which would export every event twice).
#
# Uninstall: delete the hook file first, then the emitter directory:
#   rm .kiro/hooks/fi-hook-to-otlp-kiro-cli.json && rm -r .kiro/fi-hook-to-otlp-kiro-cli
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
GLOBAL_DIR="${KIRO_HOME:-$HOME/.kiro}"
NAME="fi-hook-to-otlp-kiro-cli"

MODE="${1:-}"
case "$MODE" in
  --user|--agent-profile)
    KIRO_DIR="$GLOBAL_DIR"
    TEMPLATE="$HERE/$NAME.user.json"
    OTHER_SCOPE=""
    ;;
  "")
    echo "usage: $0 <project-dir> | --user | --agent-profile" >&2
    exit 2
    ;;
  *)
    KIRO_DIR="$(cd "$MODE" && pwd)/.kiro"
    TEMPLATE="$HERE/$NAME.json"
    OTHER_SCOPE="$GLOBAL_DIR/hooks/$NAME.json"
    ;;
esac

case "$GLOBAL_DIR" in
  *[\"\`\$\\]*) echo "KIRO_HOME must not contain quotes, backticks, \$ or backslashes: $GLOBAL_DIR" >&2; exit 2 ;;
esac

HOOK_FILE="$KIRO_DIR/hooks/$NAME.json"

if [[ "$MODE" != "--agent-profile" ]]; then
  # The Kiro IDE recipe's hook file fires in Kiro CLI sessions too (and this one in IDE sessions).
  for dir in "$KIRO_DIR/hooks" "$GLOBAL_DIR/hooks" "$HOME/.kiro/hooks"; do
    other="$dir/fi-hook-to-otlp.json"
    if [[ -e "$other" ]] && grep -q 'kiro_ide' "$other"; then
      echo "refusing to install Kiro CLI hooks: $other is the Kiro IDE recipe." >&2
      echo "Kiro CLI and Kiro IDE both load it, so every session would be exported twice." >&2
      echo "Use './install.sh --agent-profile' (hooks in a CLI agent profile) or trace one Kiro surface per scope." >&2
      exit 1
    fi
  done
  if [[ -n "$OTHER_SCOPE" && -e "$OTHER_SCOPE" ]]; then
    echo "refusing to install project hooks: $OTHER_SCOPE already traces every Kiro CLI session." >&2
    echo "Kiro runs global and project hooks side by side, so each event would be exported twice." >&2
    exit 1
  fi
fi

DEST="$KIRO_DIR/$NAME"
mkdir -p "$DEST/adapters"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/kiro_cli.py" "$DEST/adapters/"
echo "emitter: $DEST"

# Global templates name "$HOME/.kiro"; with KIRO_HOME set, point them at it instead.
render() {
  python3 -B - "$1" "$GLOBAL_DIR" "$HOME/.kiro" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8").read()
if sys.argv[2] != sys.argv[3]:
    text = text.replace('\\"$HOME/.kiro/', '\\"' + sys.argv[2] + "/")
sys.stdout.write(text)
PY
}

if [[ "$MODE" == "--agent-profile" ]]; then
  echo
  echo "Add these entries to the \"hooks\" array of the CLI agent profile you use"
  echo "(for example ~/.kiro/agents/<name>.json), then run: kiro-cli chat --agent <name>"
  render "$HERE/agent-profile-hooks.json"
elif [[ -e "$HOOK_FILE" ]]; then
  echo "kept existing $HOOK_FILE"
  if ! render "$TEMPLATE" | cmp -s - "$HOOK_FILE"; then
    echo "  it differs from the shipped template; replace it with $TEMPLATE to get the current guarded commands."
  fi
else
  mkdir -p "$KIRO_DIR/hooks"
  render "$TEMPLATE" > "$HOOK_FILE"
  echo "hooks:   $HOOK_FILE"
fi

echo
echo "Credentials: put FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Variables exported in the shell that runs kiro-cli also work."
