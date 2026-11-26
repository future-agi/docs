#!/bin/sh
# Auggie hook command for Future AGI.
#
# Augment documents a hook command as the path to a script with a .sh
# extension, which Auggie runs with the event JSON on stdin. The settings
# therefore name this script, and the guard that other coding-agent pages put
# in the hook command lives here:
# - the emitter runs in the canonical guarded subshell, so a missing emit.py,
#   a missing python3 or a crash still exits 0;
# - stdout goes to /dev/null: Auggie adds plain-text SessionStart output to the
#   agent's context and reads a Stop {"decision": "block"} as "keep working",
#   and this hook has nothing to tell the agent;
# - stderr goes to /dev/null, so no Python error text reaches Auggie's logs;
# - -B keeps __pycache__ out of the install folder.
# It uses no external commands, so it works with an empty PATH too.
case "$0" in
  */*) HERE="${0%/*}" ;;
  *) HERE=. ;;
esac
EMIT="$HERE/emit.py"
[ -f "$EMIT" ] || EMIT="$HERE/../hook-to-otlp/emit.py"
(python3 -B "$EMIT" augment 2>/dev/null || true) >/dev/null
exit 0
