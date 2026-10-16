#!/usr/bin/env bash
# End-to-end run of the CloudWeGo Eino page: builds main.go the way the page
# says (go mod init, go get, go build) and sends three runs to Future AGI.
# Each run asks the trip_assistant agent (Eino ADK ChatModelAgent, eino-ext
# OpenAI chat model, get_weather tool) one question.
#
#   A  default capture, streamed, then one run whose model does not exist
#   B  default capture, not streamed
#   C  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, then the failing run
#
# A unique marker goes into the question of A (MARK_DEFAULT) and of C
# (MARK_HIDDEN). Search Future AGI for both: MARK_DEFAULT appears in the inputs
# of run A, MARK_HIDDEN appears nowhere.
#
# Required: FI_API_KEY, FI_SECRET_KEY, OPENAI_API_KEY, Go 1.26+ (or
# GOTOOLCHAIN=auto with network access).
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME,
# OPENAI_BASE_URL (any OpenAI-compatible endpoint), MODEL (default
# gpt-4.1-mini), TRACEAI_GO_EINO_REF (version or commit of
# github.com/future-agi/traceAI/go/eino, default latest), EINO_VERSION
# (default v0.9.21), EINO_EXT_OPENAI_VERSION (default v0.1.13).
# This script never prints a key.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-eino-go-example}"
MODEL="${MODEL:-gpt-4.1-mini}"
REF="${TRACEAI_GO_EINO_REF:-latest}"
EINO_VERSION="${EINO_VERSION:-v0.9.21}"
EINO_EXT_OPENAI_VERSION="${EINO_EXT_OPENAI_VERSION:-v0.1.13}"
# The FI_HIDE_* switches are set per run below; start from the defaults.
unset FI_HIDE_INPUTS FI_HIDE_OUTPUTS FI_HIDE_INPUT_MESSAGES FI_HIDE_OUTPUT_MESSAGES \
  FI_HIDE_INPUT_TEXT FI_HIDE_OUTPUT_TEXT FI_HIDE_INPUT_IMAGES FI_HIDE_LLM_INVOCATION_PARAMETERS

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$HERE/main.go" "$WORK/"
cd "$WORK"

echo "== build: go get github.com/future-agi/traceAI/go/eino@$REF github.com/cloudwego/eino@$EINO_VERSION github.com/cloudwego/eino-ext/components/model/openai@$EINO_EXT_OPENAI_VERSION"
go mod init example.com/eino-go-example >/dev/null 2>&1
go get "github.com/future-agi/traceAI/go/eino@$REF" "github.com/cloudwego/eino@$EINO_VERSION" \
  "github.com/cloudwego/eino-ext/components/model/openai@$EINO_EXT_OPENAI_VERSION"
go mod tidy
go build -o eino-go-example .
go version
grep -E 'future-agi/traceAI/go/eino |cloudwego/eino |cloudwego/eino-ext/components/model/openai |go.opentelemetry.io/otel/sdk ' go.mod

TS="$(date +%s)"
RND="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
MARK_DEFAULT="EINOGODEF${RND}"
MARK_HIDDEN="EINOGOHID${RND}"
echo "MARK_DEFAULT=$MARK_DEFAULT"
echo "MARK_HIDDEN=$MARK_HIDDEN"

echo "== run A: default capture, streamed, plus a run whose model does not exist"
./eino-go-example -model "$MODEL" -stream -fail -session "eino-go-default-stream-$TS" \
  -question "I am in Kyoto tomorrow, booking ref $MARK_DEFAULT. What should I pack? Repeat the booking ref at the end."

echo "== run B: default capture, not streamed"
./eino-go-example -model "$MODEL" -session "eino-go-default-plain-$TS" \
  -question "I am in Osaka tomorrow. What should I pack?"

echo "== run C: FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true, streamed, plus the failing run"
FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true ./eino-go-example -model "$MODEL" -stream -fail \
  -session "eino-go-hidden-$TS" \
  -question "I am in Kyoto tomorrow. Booking ref $MARK_HIDDEN, email $MARK_HIDDEN@example.com, itinerary /Users/someone/$MARK_HIDDEN.txt. What should I pack? Repeat the booking ref at the end."

echo "== done: open project $FI_PROJECT_NAME in Future AGI Observe"
