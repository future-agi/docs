#!/usr/bin/env bash
# Run one real Oh My Pi (omp.sh) session with the Future AGI hook installed in a
# throwaway project, then print the marker string to search for in Future AGI.
#
# Required: omp on PATH (or OMP_BIN), a working model in your omp config,
#           FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME.
# Optional: FI_OTLP_ENDPOINT or FI_BASE_URL, FI_CAPTURE_CONTENT=true,
#           OMP_MODEL=<provider>/<model> (otherwise your default model).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
for name in FI_API_KEY FI_SECRET_KEY FI_PROJECT_NAME; do
  if [ -z "${!name:-}" ]; then echo "missing $name" >&2; exit 2; fi
done
omp="${OMP_BIN:-omp}"
command -v "$omp" >/dev/null || { echo "omp is not on PATH (install from https://omp.sh)" >&2; exit 2; }

project="$(mktemp -d "${TMPDIR:-/tmp}/omp-futureagi-XXXXXX")"
mkdir -p "$project/.omp/hooks/post"
cp "$here/futureagi-otlp.ts" "$project/.omp/hooks/post/futureagi-otlp.ts"
printf '# Demo project\n\nA throwaway folder used to check Oh My Pi tracing.\n' > "$project/README.md"
printf 'print("hello")\n' > "$project/main.py"

marker="OMP-MARKER-$(date +%s)-$RANDOM"
model_args=()
if [ -n "${OMP_MODEL:-}" ]; then model_args=(--model "$OMP_MODEL"); fi

echo "$("$omp" --version) in $project"
# -p runs the same agent session as the TUI (hooks included), prints the answer and exits.
(cd "$project" && "$omp" -p --no-title ${model_args[@]+"${model_args[@]}"} \
  "$marker List the files in this folder and read README.md, then summarize the project in one sentence." </dev/null)

echo
echo "marker=$marker"
echo "project=$FI_PROJECT_NAME capture_content=${FI_CAPTURE_CONTENT:-false}"
echo "With content capture off, searching the exported spans for the marker must find nothing."
