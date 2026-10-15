#!/usr/bin/env bash
# Install the Future AGI hook emitter for Augment's Auggie CLI.
#
#   ./install.sh
#
# Copies emit.py, the Augment adapter and the futureagi-hook.sh wrapper into
# ~/.augment/fi-hook-to-otlp/ and writes ~/.augment/settings.json if there is
# none. An existing settings.json is never modified: the script prints the
# "hooks" entries to merge instead. No metadata flags are set, so Auggie does
# not add user context or conversation data to the hook input.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
AUGMENT_DIR="$HOME/.augment"
DEST="$AUGMENT_DIR/fi-hook-to-otlp"

mkdir -p "$DEST/adapters"
cp "$EMITTER/emit.py" "$DEST/emit.py"
cp "$EMITTER/adapters/__init__.py" "$EMITTER/adapters/base.py" "$EMITTER/adapters/augment.py" "$DEST/adapters/"
cp "$HERE/futureagi-hook.sh" "$DEST/futureagi-hook.sh"
chmod +x "$DEST/futureagi-hook.sh"
echo "emitter: $DEST"

SETTINGS="$(sed "s#/Users/you/.augment/fi-hook-to-otlp/futureagi-hook.sh#$DEST/futureagi-hook.sh#g" "$HERE/settings.json")"
if [[ -e "$AUGMENT_DIR/settings.json" ]]; then
  echo "kept existing $AUGMENT_DIR/settings.json; merge these entries into its \"hooks\" object:"
  echo "$SETTINGS"
else
  echo "$SETTINGS" > "$AUGMENT_DIR/settings.json"
  echo "hooks:   $AUGMENT_DIR/settings.json"
fi

echo
echo "Credentials: put FI_API_KEY, FI_SECRET_KEY and FI_PROJECT_NAME in"
echo "~/.config/fi-hook-to-otlp/env (chmod 600), or export them before starting auggie."
