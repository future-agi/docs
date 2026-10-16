#!/usr/bin/env bash
# End-to-end run of the Gemini Go page: builds main.go the way the page says
# (go mod init, go get, go run) and sends three traced runs to Future AGI.
#
#   A  default capture, function call, streamed final answer, then one failing call
#   B  default capture, function call, non-streamed final answer
#   C  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, then one failing call
#
# A unique marker goes into the prompts and the tool result of A (MARK_DEFAULT)
# and of C (MARK_HIDDEN). Search Future AGI for both: MARK_DEFAULT appears in the
# inputs and outputs of run A, MARK_HIDDEN appears nowhere.
#
# Required: FI_API_KEY, FI_SECRET_KEY, GEMINI_API_KEY (Gemini Developer API),
# Go 1.26+ (or GOTOOLCHAIN=auto with network access).
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME,
# MODEL (default gemini-3.8-flash), TRACEAI_GO_GENAI_REF (version or commit of
# github.com/future-agi/traceAI/go/genai, default latest), GENAI_VERSION
# (google.golang.org/genai, default v1.75.0), PAUSE (seconds to wait between
# runs, default 0; the free Gemini tier allows only a few requests per minute,
# so use PAUSE=60 there).
# This script never prints a key.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${GEMINI_API_KEY:?set GEMINI_API_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-gemini-go-example}"
MODEL="${MODEL:-gemini-3.8-flash}"
REF="${TRACEAI_GO_GENAI_REF:-latest}"
GENAI_VERSION="${GENAI_VERSION:-v1.75.0}"
PAUSE="${PAUSE:-0}"
# The FI_HIDE_* switches are set per run below; start from the defaults.
unset FI_HIDE_INPUTS FI_HIDE_OUTPUTS FI_HIDE_INPUT_MESSAGES FI_HIDE_OUTPUT_MESSAGES \
  FI_HIDE_INPUT_TEXT FI_HIDE_OUTPUT_TEXT FI_HIDE_INPUT_IMAGES FI_HIDE_LLM_INVOCATION_PARAMETERS
# Only GEMINI_API_KEY should reach the SDK (it prefers GOOGLE_API_KEY when both are set).
unset GOOGLE_API_KEY GOOGLE_GENAI_USE_VERTEXAI

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$HERE/main.go" "$WORK/"
cd "$WORK"

echo "== build: go get github.com/future-agi/traceAI/go/genai@$REF google.golang.org/genai@$GENAI_VERSION"
go mod init example.com/gemini-go-example >/dev/null 2>&1
go get "github.com/future-agi/traceAI/go/genai@$REF" "google.golang.org/genai@$GENAI_VERSION"
go mod tidy
go build -o gemini-go-example .
go version
grep -E 'future-agi/traceAI/go/genai |google.golang.org/genai |go.opentelemetry.io/otel/sdk ' go.mod

TS="$(date +%s)"
RND="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
MARK_DEFAULT="GEMGODEF${RND}"
MARK_HIDDEN="GEMGOHID${RND}"
echo "MARK_DEFAULT=$MARK_DEFAULT"
echo "MARK_HIDDEN=$MARK_HIDDEN"

echo "== run A: default capture, streamed, plus a failing call"
./gemini-go-example -model "$MODEL" -stream -fail -session "gemini-go-default-stream-$TS" \
  -question "What is the weather in Paris right now? Reference $MARK_DEFAULT. Answer in one sentence and end with the reference." \
  -tool-note "station note $MARK_DEFAULT"

sleep "$PAUSE"
echo "== run B: default capture, not streamed"
./gemini-go-example -model "$MODEL" -session "gemini-go-default-plain-$TS" \
  -question "What is the weather in Paris right now? Answer in one sentence."

sleep "$PAUSE"
echo "== run C: FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, plus a failing call"
FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true ./gemini-go-example -model "$MODEL" -stream -fail \
  -session "gemini-go-hidden-$TS" \
  -question "Call get_weather with city \"Paris $MARK_HIDDEN\". My reference is $MARK_HIDDEN, email $MARK_HIDDEN@example.com, file /Users/someone/$MARK_HIDDEN.txt. End your answer with the reference." \
  -tool-note "station note $MARK_HIDDEN"

echo "== done: open project $FI_PROJECT_NAME in Future AGI Observe"
