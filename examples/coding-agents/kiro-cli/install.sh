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
# global), and a session that uses an agent profile loads them as well as the
# profile's hooks. Each pairing below would export the same session twice:
#   - refused: the Kiro IDE recipe in the scope being installed (or in
#     ~/.kiro/hooks for --agent-profile), a project install when the global one
#     exists, and --agent-profile when the global one exists;
#   - warned:  pairings the installer can only see from the current directory
#     or an agent profile (it cannot see other projects).
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
GLOBAL_HOOKS=("$GLOBAL_DIR/hooks" "$HOME/.kiro/hooks")

# .kiro of the directory the installer runs from (checked by --user and --agent-profile),
# unless that is the global directory. Evaluated again after the install creates it.
cwd_kiro() {
  if ! [[ "$PWD/.kiro" -ef "$GLOBAL_DIR" || "$PWD/.kiro" -ef "$HOME/.kiro" ]]; then
    echo "$PWD/.kiro"
  fi
}
CWD_KIRO="$(cwd_kiro)"

refuse() {
  printf '%s\n' "$@" >&2
  exit 1
}

warn() {
  printf 'warning: %s\n' "$1" >&2
  shift
  printf '  %s\n' "$@" >&2
}

# The Kiro IDE recipe's hook file in a hooks directory, if it is installed there.
ide_recipe_in() {
  local file="$1/fi-hook-to-otlp.json"
  if [[ -e "$file" ]] && grep -q 'kiro_ide' "$file"; then
    echo "$file"
  fi
}

# Agent profiles (any format, nested directories too) whose hooks run this recipe's emitter.
profiles_running_emitter() {
  local dir
  for dir in "$@"; do
    if [[ -n "$dir" && -d "$dir" ]]; then
      grep -rlF -e "$NAME/emit.py" -- "$dir" 2>/dev/null || true
    fi
  done | sort -u
}

if [[ "$MODE" == "--agent-profile" ]]; then
  # A session that uses the agent still loads every standalone hook file.
  for dir in "${GLOBAL_HOOKS[@]}"; do
    other="$(ide_recipe_in "$dir")"
    if [[ -n "$other" ]]; then
      refuse "refusing to set up agent-profile hooks: $other is the Kiro IDE recipe." \
        "Kiro CLI loads it in every session, including sessions that use an agent profile, so each" \
        "session would be exported twice (as Kiro IDE and as Kiro CLI). Remove it first to trace Kiro CLI."
    fi
    if [[ -e "$dir/$NAME.json" ]]; then
      refuse "refusing to set up agent-profile hooks: $dir/$NAME.json already traces every Kiro CLI session," \
        "including sessions that use an agent profile, so the profile entries would export each event twice."
    fi
  done
  if [[ -n "$CWD_KIRO" ]]; then
    for other in "$(ide_recipe_in "$CWD_KIRO/hooks")" "$CWD_KIRO/hooks/$NAME.json"; do
      if [[ -n "$other" && -e "$other" ]]; then
        warn "$other runs in every Kiro session in $PWD." \
          "Sessions that use the agent there would be exported twice: use the agent in other projects," \
          "or remove that file."
      fi
    done
  fi
else
  # The Kiro IDE recipe's hook file fires in Kiro CLI sessions too (and this one in IDE sessions).
  for dir in "$KIRO_DIR/hooks" "${GLOBAL_HOOKS[@]}"; do
    other="$(ide_recipe_in "$dir")"
    if [[ -n "$other" ]]; then
      refuse "refusing to install Kiro CLI hooks: $other is the Kiro IDE recipe." \
        "Kiro CLI and Kiro IDE both load it, so every session would be exported twice." \
        "It already exports the Kiro CLI sessions it sees, as Kiro IDE sessions; remove it first to trace them as Kiro CLI."
    fi
  done
  if [[ -n "$OTHER_SCOPE" && -e "$OTHER_SCOPE" ]]; then
    refuse "refusing to install project hooks: $OTHER_SCOPE already traces every Kiro CLI session." \
      "Kiro runs global and project hooks side by side, so each event would be exported twice."
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
  echo "Sessions that use the agent still load .kiro/hooks/*.json: do not use it in a project that has"
  echo "the Kiro IDE recipe (.kiro/hooks/fi-hook-to-otlp.json) or .kiro/hooks/$NAME.json."
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

# Pairings visible only from the current directory or an agent profile. The new
# install is still wanted, so these warn and name the file that became redundant.
CWD_KIRO="$(cwd_kiro)"
if [[ "$MODE" == "--user" ]]; then
  if [[ -n "$CWD_KIRO" && -e "$CWD_KIRO/hooks/$NAME.json" ]]; then
    warn "$CWD_KIRO/hooks/$NAME.json is a project install of this recipe." \
      "Kiro runs it beside the global hooks, so every event in $PWD is exported twice:" \
      "remove it, then $CWD_KIRO/$NAME."
  fi
  other="$(ide_recipe_in "${CWD_KIRO:-/nonexistent}/hooks")"
  if [[ -n "$other" ]]; then
    warn "$other is the Kiro IDE recipe." \
      "With the global hooks, every Kiro session in $PWD is exported twice: remove one of them."
  fi
  echo
  echo "If you installed this recipe per project before, remove those projects' .kiro/hooks/$NAME.json:"
  echo "the global hooks already cover them, and each event there would be exported twice."
fi
if [[ "$MODE" != "--agent-profile" ]]; then
  if [[ "$MODE" == "--user" ]]; then
    project_agents="${CWD_KIRO:+$CWD_KIRO/agents}"
    where=""
  else
    project_agents="$KIRO_DIR/agents"
    where=" in $(dirname "$KIRO_DIR")"
  fi
  while IFS= read -r profile; do
    warn "$profile is an agent profile that runs this recipe's hooks too." \
      "Sessions that use that agent$where would be exported twice: remove its Future AGI entries."
  done < <(profiles_running_emitter "$GLOBAL_DIR/agents" "$HOME/.kiro/agents" "$project_agents")
fi

echo
echo "Credentials: put FI_API_KEY / FI_SECRET_KEY / FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600). Variables exported in the shell that runs kiro-cli also work."
