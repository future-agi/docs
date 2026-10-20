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
#
# With --project, the workspace file holds this machine's home path, so it is
# also added to the repository's local exclude list (.git/info/exclude, which
# is never committed) unless git already ignores it. No tracked file such as
# .gitignore is changed.
set -euo pipefail

usage() { echo "usage: $0 [--project REPO]" >&2; exit 2; }

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
DEST="$HOME/.augment/fi-hook-to-otlp"
SETTINGS="$HOME/.augment/settings.json"
REPO=""
case "${1:-}" in
  "") [[ $# -eq 0 ]] || usage ;;
  --project)
    [[ $# -eq 2 && -d "$2" ]] || usage
    REPO="$(cd "$2" && pwd)"
    SETTINGS="$REPO/.augment/settings.local.json" ;;
  *) usage ;;
esac

# Keep <repo>/.augment/settings.local.json out of commits (see the header).
ignore_workspace_settings() {
  local repo="$1" rel=".augment/settings.local.json" pattern="**/.augment/settings.local.json" exclude
  if ! command -v git >/dev/null 2>&1 || ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "note:    $repo is not a git work tree; keep $rel out of version control"
    return 0
  fi
  if git -C "$repo" check-ignore -q -- "$rel"; then
    echo "ignored: $rel (already ignored by git)"
    return 0
  fi
  exclude="$(cd "$repo" && git rev-parse --git-path info/exclude)"
  case "$exclude" in /*) ;; *) exclude="$repo/$exclude" ;; esac
  mkdir -p "$(dirname "$exclude")"
  if [[ -s "$exclude" && -n "$(tail -c 1 "$exclude")" ]]; then echo >> "$exclude"; fi
  printf '%s\n' "# Future AGI Auggie hooks: personal settings with this machine's home path" "$pattern" >> "$exclude"
  if git -C "$repo" check-ignore -q -- "$rel"; then
    echo "ignored: $rel (added to $exclude)"
  else
    echo "warning: git still tracks $repo/$rel; do not commit it, it contains your home path" >&2
  fi
}

# settings.json with the wrapper path filled in. Built with json.dump, so any
# character in the home directory gives valid JSON. Auggie splits a command
# that contains a space, and runs one that contains a shell metacharacter
# through bash, so such a path is single-quoted (Auggie removes the quotes).
# Built before anything is copied, so a path that cannot be registered leaves
# no partial install behind.
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

mkdir -p "$DEST/adapters"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/augment.py" "$DEST/adapters/"
cp "$HERE/futureagi-hook.sh" "$DEST/futureagi-hook.sh"
chmod +x "$DEST/futureagi-hook.sh"
echo "emitter: $DEST"

if [[ -e "$SETTINGS" ]]; then
  echo "kept existing $SETTINGS; merge these entries into its \"hooks\" object:"
  echo "$HOOKS"
else
  mkdir -p "$(dirname "$SETTINGS")"
  echo "$HOOKS" > "$SETTINGS"
  echo "hooks:   $SETTINGS"
fi
if [[ -n "$REPO" ]]; then ignore_workspace_settings "$REPO"; fi

echo
echo "Credentials: put FI_API_KEY, FI_SECRET_KEY and FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600), or export them before starting auggie."
