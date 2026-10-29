#!/usr/bin/env bash
# End-to-end run of the Embabel recipe: builds the example, runs the agent against a real
# OpenAI-compatible model and a real Future AGI collector, with content capture off and on.
#
# Required: FI_API_KEY, FI_SECRET_KEY, OPENAI_CUSTOM_BASE_URL (ends in /v1), OPENAI_CUSTOM_API_KEY,
#           OPENAI_CUSTOM_MODELS (first entry is the model used), Java 21 and Maven on PATH.
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME (default embabel-e2e),
#           VERIFY_LOCAL_STACK=1 to check what a self-hosted Future AGI in Docker stored,
#           RUN_LLM_FAILURE=1 to add a run whose model call fails (takes about 3 minutes: Embabel
#           retries the call and the action), MVN_ARGS for extra Maven flags.
set -euo pipefail
cd "$(dirname "$0")"

: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${OPENAI_CUSTOM_BASE_URL:?set OPENAI_CUSTOM_BASE_URL}" "${OPENAI_CUSTOM_API_KEY:?set OPENAI_CUSTOM_API_KEY}"
: "${OPENAI_CUSTOM_MODELS:?set OPENAI_CUSTOM_MODELS}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-embabel-e2e}"
export EMBABEL_MODELS_DEFAULT_LLM="${EMBABEL_MODELS_DEFAULT_LLM:-${OPENAI_CUSTOM_MODELS%%,*}}"
BASE_PROJECT="$FI_PROJECT_NAME"

BUILD_LOG="$(mktemp)"
# shellcheck disable=SC2086
mvn -q -B ${MVN_ARGS:-} package > "$BUILD_LOG" 2>&1 || { tail -60 "$BUILD_LOG"; exit 1; }
echo "build and tests: ok"
JAR=target/embabel-future-agi-tracing-0.1.0.jar
MARK="EMB$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"
echo "marker: $MARK"

run() {  # run <project> <capture-content> <station-id>; a failed agent run is not a script failure
  FI_PROJECT_NAME="$1" EMBABEL_CAPTURE_CONTENT="$2" java -jar "$JAR" \
    "--demo.station-id=$3" "--demo.question=Is it a good day for a walk near $MARK?" \
    > "target/run-$1-$3.log" 2>&1 || echo "  agent run exited non-zero (see target/run-$1-$3.log)"
  grep -h -o 'Agent finished.*\|Agent run failed.*' "target/run-$1-$3.log" | cut -c1-80 | sed 's/^/  /' || true
}

echo "1. content off (default) -> project $BASE_PROJECT"
run "$BASE_PROJECT" false "LIS-$MARK"
run "$BASE_PROJECT" false "offline-$MARK"   # the tool throws: an ERROR tool span
if [ "${RUN_LLM_FAILURE:-0}" = 1 ]; then
  echo "   model failure run (unknown model name)"
  OPENAI_CUSTOM_MODELS="$OPENAI_CUSTOM_MODELS,embabel-e2e-missing-model" \
    EMBABEL_MODELS_DEFAULT_LLM=embabel-e2e-missing-model run "$BASE_PROJECT" false "model-failure-$MARK"
fi

echo "2. content on (opt-in) -> project $BASE_PROJECT-optin"
run "$BASE_PROJECT-optin" true "LIS-$MARK"
run "$BASE_PROJECT-optin" true "offline-$MARK"

if [ "${VERIFY_LOCAL_STACK:-0}" = 1 ]; then
  sleep 10   # the collector writes asynchronously
  py="${PYTHON:-python3}"
  echo "3. stored traces"
  "$py" tools/check_trace.py --project "$BASE_PROJECT" --min-traces 2 --tool-error 1 --content-off
  "$py" tools/check_trace.py --project "$BASE_PROJECT-optin" --min-traces 2 --tool-error 1
  echo "4. privacy: content off stores no marker and no error text, opt-in stores both"
  "$py" tools/scan_local_stack.py --project "$BASE_PROJECT" --needle "marker=$MARK" --needle "error_text=is offline" \
    --needle "home=$HOME" --needle "user=$(id -un)" --needle "host=$(hostname -s)" \
    --needle "fi_api_key=$FI_API_KEY" --needle "fi_secret_key=$FI_SECRET_KEY" --needle "model_key=$OPENAI_CUSTOM_API_KEY"
  "$py" tools/scan_local_stack.py --project "$BASE_PROJECT-optin" --needle "marker=$MARK" --needle "error_text=is offline" --expect-found
  "$py" tools/scan_local_stack.py --project "$BASE_PROJECT-optin" --needle "home=$HOME" --needle "host=$(hostname -s)" \
    --needle "fi_api_key=$FI_API_KEY" --needle "fi_secret_key=$FI_SECRET_KEY" --needle "model_key=$OPENAI_CUSTOM_API_KEY"
fi
echo "done"
