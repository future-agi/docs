#!/usr/bin/env bash
# Run one real OpenCode session with the Future AGI plugin installed in a
# throwaway project, then print the marker string to search for in Future AGI.
#
# Required: opencode on PATH, a working model provider in your OpenCode config,
#           FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME.
# Optional: FI_OTLP_ENDPOINT or FI_BASE_URL, FI_CAPTURE_CONTENT=true,
#           OPENCODE_MODEL=<provider>/<model> (otherwise your default model).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
for name in FI_API_KEY FI_SECRET_KEY FI_PROJECT_NAME; do
  if [ -z "${!name:-}" ]; then echo "missing $name" >&2; exit 2; fi
done
command -v opencode >/dev/null || { echo "opencode is not on PATH" >&2; exit 2; }

project="$(mktemp -d "${TMPDIR:-/tmp}/opencode-futureagi-XXXXXX")"
mkdir -p "$project/.opencode/plugins"
cp "$here/futureagi-otlp.ts" "$project/.opencode/plugins/futureagi-otlp.ts"
printf '# Demo project\n\nA throwaway folder used to check OpenCode tracing.\n' > "$project/README.md"
printf 'print("hello")\n' > "$project/main.py"
git -C "$project" init -q 2>/dev/null || true

marker="OPENCODE-MARKER-$(date +%s)-$RANDOM"
model_args=()
if [ -n "${OPENCODE_MODEL:-}" ]; then model_args=(--model "$OPENCODE_MODEL"); fi

echo "opencode $(opencode --version) in $project"
(cd "$project" && opencode run ${model_args[@]+"${model_args[@]}"} \
  "$marker List the files in this folder and read README.md, then summarize the project in one sentence.")

echo
echo "marker=$marker"
echo "project=$FI_PROJECT_NAME capture_content=${FI_CAPTURE_CONTENT:-false}"
echo "With content capture off, searching the exported spans for the marker must find nothing."
