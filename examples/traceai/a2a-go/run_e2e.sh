#!/usr/bin/env bash
# End-to-end run of the A2A Go page: builds main.go the way the page says
# (go mod init, go get, go build) and sends three traced runs to Future AGI.
# Each run starts the demo A2A agent (a2a-go's own server package) on 127.0.0.1.
#
#   A  default capture, streamed, then one call the agent fails
#   B  default capture, not streamed (SendMessage)
#   C  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, then one failed call
#
# A unique marker goes into the message of A (MARK_DEFAULT) and of C
# (MARK_HIDDEN). Search Future AGI for both: MARK_DEFAULT appears in the inputs
# and outputs of run A, MARK_HIDDEN appears nowhere.
#
# Required: FI_API_KEY, FI_SECRET_KEY, Go 1.26+ (or GOTOOLCHAIN=auto with
# network access).
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME,
# OPENAI_API_KEY + OPENAI_BASE_URL + MODEL (the demo agent answers with that
# model; without a key it echoes), TRACEAI_GO_A2A_REF (version or commit of
# github.com/future-agi/traceAI/go/a2a, default latest), A2A_GO_VERSION
# (default v2.6.0).
# This script never prints a key.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-a2a-go-example}"
MODEL="${MODEL:-gpt-4.1-mini}"
REF="${TRACEAI_GO_A2A_REF:-latest}"
A2A_GO_VERSION="${A2A_GO_VERSION:-v2.6.0}"
# The FI_HIDE_* switches are set per run below; start from the defaults.
unset FI_HIDE_INPUTS FI_HIDE_OUTPUTS FI_HIDE_INPUT_MESSAGES FI_HIDE_OUTPUT_MESSAGES \
  FI_HIDE_INPUT_TEXT FI_HIDE_OUTPUT_TEXT FI_HIDE_INPUT_IMAGES FI_HIDE_LLM_INVOCATION_PARAMETERS

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$HERE/main.go" "$WORK/"
cd "$WORK"

echo "== build: go get github.com/future-agi/traceAI/go/a2a@$REF github.com/a2aproject/a2a-go/v2@$A2A_GO_VERSION"
go mod init example.com/a2a-go-example >/dev/null 2>&1
go get "github.com/future-agi/traceAI/go/a2a@$REF" "github.com/a2aproject/a2a-go/v2@$A2A_GO_VERSION"
go mod tidy
go build -o a2a-go-example .
go version
grep -E 'future-agi/traceAI/go/a2a |a2aproject/a2a-go/v2 |go.opentelemetry.io/otel/sdk ' go.mod

TS="$(date +%s)"
RND="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
MARK_DEFAULT="A2AGODEF${RND}"
MARK_HIDDEN="A2AGOHID${RND}"
echo "MARK_DEFAULT=$MARK_DEFAULT"
echo "MARK_HIDDEN=$MARK_HIDDEN"

echo "== run A: default capture, streamed, plus a failed task"
./a2a-go-example -model "$MODEL" -stream -fail -session "a2a-go-default-stream-$TS" \
  -question "Plan one day in Kyoto in two short bullets. Reference $MARK_DEFAULT; end your answer with the reference."

echo "== run B: default capture, not streamed"
./a2a-go-example -model "$MODEL" -session "a2a-go-default-plain-$TS" \
  -question "Plan one morning in Osaka in one sentence."

echo "== run C: FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, plus a failed task"
FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true ./a2a-go-example -model "$MODEL" -stream -fail \
  -session "a2a-go-hidden-$TS" \
  -question "Plan one day in Kyoto. My reference is $MARK_HIDDEN, email $MARK_HIDDEN@example.com, file /Users/someone/$MARK_HIDDEN.txt. End your answer with the reference."

echo "== done: open project $FI_PROJECT_NAME in Future AGI Observe"
