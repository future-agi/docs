#!/usr/bin/env bash
# Install the Future AGI hook emitter for Augment's Auggie CLI (macOS, Linux).
#
#   ./install.sh                  hooks for every Auggie session (~/.augment/settings.json)
#   ./install.sh --project REPO   hooks for one repository only (REPO/.augment/settings.local.json)
#
# Copies emit.py, the Augment adapter and the futureagi-hook.sh wrapper into
# ~/.augment/fi-hook-to-otlp/. Then writes the hooks file if it does not exist.
# An existing settings file is never modified: the script prints the "hooks"
# entries to merge instead. No metadata flags are set, so Auggie does not add
# user context or conversation data to the hook input.
set -euo pipefail

usage() { echo "usage: $0 [--project REPO]" >&2; exit 2; }

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
DEST="$HOME/.augment/fi-hook-to-otlp"
SETTINGS="$HOME/.augment/settings.json"
case "${1:-}" in
  "") [[ $# -eq 0 ]] || usage ;;
  --project)
    [[ $# -eq 2 && -d "$2" ]] || usage
    SETTINGS="$(cd "$2" && pwd)/.augment/settings.local.json" ;;
  *) usage ;;
esac

mkdir -p "$DEST/adapters"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/augment.py" "$DEST/adapters/"
cp "$HERE/futureagi-hook.sh" "$DEST/futureagi-hook.sh"
chmod +x "$DEST/futureagi-hook.sh"
echo "emitter: $DEST"

# settings.json with the wrapper path filled in. Built with json.dump, so any
# character in the home directory gives valid JSON. Auggie splits a command
# that contains a space, and runs one that contains a shell metacharacter
# through bash, so such a path is single-quoted (Auggie removes the quotes).
HOOKS="$(python3 - "$HERE/settings.json" "$DEST/futureagi-hook.sh" <<'PY'
import json, re, sys
template, wrapper = sys.argv[1], sys.argv[2]
if not re.fullmatch(r"[A-Za-z0-9_./+@:,=%-]+", wrapper):
    if "'" in wrapper:
        sys.exit(f"cannot register a hook path that contains a single quote: {wrapper}")
    wrapper = f"'{wrapper}'"
with open(template, encoding="utf-8") as f:
    settings = json.load(f)
for groups in settings["hooks"].values():
    for group in groups:
        for hook in group["hooks"]:
            hook["command"] = wrapper
print(json.dumps(settings, indent=2))
PY
)"
if [[ -e "$SETTINGS" ]]; then
  echo "kept existing $SETTINGS; merge these entries into its \"hooks\" object:"
  echo "$HOOKS"
else
  mkdir -p "$(dirname "$SETTINGS")"
  echo "$HOOKS" > "$SETTINGS"
  echo "hooks:   $SETTINGS"
fi

echo
echo "Credentials: put FI_API_KEY, FI_SECRET_KEY and FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600), or export them before starting auggie."
