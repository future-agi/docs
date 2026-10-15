#!/bin/sh
# Auggie hook command for Future AGI. Auggie only runs hook scripts with a
# .sh extension, so this wrapper starts the Python emitter. stdout goes to
# /dev/null: Auggie adds SessionStart stdout to the agent's context, and
# this hook has nothing to tell the agent. It always exits 0.
HERE="$(cd "$(dirname "$0")" && pwd)"
EMIT="$HERE/emit.py"
[ -f "$EMIT" ] || EMIT="$HERE/../hook-to-otlp/emit.py"
python3 "$EMIT" augment >/dev/null 2>&1
exit 0
