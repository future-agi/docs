#!/usr/bin/env bash
# End-to-end run of the OpenAI Go page: builds main.go the way the page says
# (go mod init, go get, go run) and sends three traced runs to Future AGI.
#
#   A  default capture, tool call, streamed final answer, then one failing call
#   B  default capture, tool call, non-streamed final answer
#   C  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, then one failing call
#
# A unique marker goes into the prompts and the tool result of A (MARK_DEFAULT)
# and of C (MARK_HIDDEN). Search Future AGI for both: MARK_DEFAULT appears in the
# inputs and outputs of run A, MARK_HIDDEN appears nowhere.
#
# Required: FI_API_KEY, FI_SECRET_KEY, OPENAI_API_KEY, Go 1.26+ (or
# GOTOOLCHAIN=auto with network access).
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME,
# OPENAI_BASE_URL (any OpenAI-compatible endpoint), MODEL,
# TRACEAI_GO_OPENAI_REF (version or commit of github.com/future-agi/traceAI/go/openai,
# default latest), OPENAI_GO_VERSION (default v3.78.0).
# This script never prints a key.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-openai-go-example}"
MODEL="${MODEL:-gpt-4.1-mini}"
REF="${TRACEAI_GO_OPENAI_REF:-latest}"
OPENAI_GO_VERSION="${OPENAI_GO_VERSION:-v3.78.0}"
# The FI_HIDE_* switches are set per run below; start from the defaults.
unset FI_HIDE_INPUTS FI_HIDE_OUTPUTS FI_HIDE_INPUT_MESSAGES FI_HIDE_OUTPUT_MESSAGES \
  FI_HIDE_INPUT_TEXT FI_HIDE_OUTPUT_TEXT FI_HIDE_INPUT_IMAGES FI_HIDE_LLM_INVOCATION_PARAMETERS

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$HERE/main.go" "$WORK/"
cd "$WORK"

echo "== build: go get github.com/future-agi/traceAI/go/openai@$REF github.com/openai/openai-go/v3@$OPENAI_GO_VERSION"
go mod init example.com/openai-go-example >/dev/null 2>&1
go get "github.com/future-agi/traceAI/go/openai@$REF" "github.com/openai/openai-go/v3@$OPENAI_GO_VERSION"
go mod tidy
go build -o openai-go-example .
go version
grep -E 'future-agi/traceAI/go/openai |openai/openai-go/v3 |go.opentelemetry.io/otel/sdk ' go.mod

TS="$(date +%s)"
RND="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
MARK_DEFAULT="OAIGODEF${RND}"
MARK_HIDDEN="OAIGOHID${RND}"
echo "MARK_DEFAULT=$MARK_DEFAULT"
echo "MARK_HIDDEN=$MARK_HIDDEN"

echo "== run A: default capture, streamed, plus a failing call"
./openai-go-example -model "$MODEL" -stream -fail -session "openai-go-default-stream-$TS" \
  -question "What is the weather in Paris right now? Reference $MARK_DEFAULT. Answer in one sentence and end with the reference." \
  -tool-note "station note $MARK_DEFAULT"

echo "== run B: default capture, not streamed"
./openai-go-example -model "$MODEL" -session "openai-go-default-plain-$TS" \
  -question "What is the weather in Paris right now? Answer in one sentence."

echo "== run C: FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, plus a failing call"
FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true ./openai-go-example -model "$MODEL" -stream -fail \
  -session "openai-go-hidden-$TS" \
  -question "Call get_weather with city \"Paris $MARK_HIDDEN\". My reference is $MARK_HIDDEN, email $MARK_HIDDEN@example.com, file /Users/someone/$MARK_HIDDEN.txt. End your answer with the reference." \
  -tool-note "station note $MARK_HIDDEN"

echo "== done: open project $FI_PROJECT_NAME in Future AGI Observe"
