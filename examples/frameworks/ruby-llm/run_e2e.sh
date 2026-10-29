#!/usr/bin/env bash
# End-to-end run of the Ruby LLM recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   OPENAI_API_KEY=... OPENAI_API_BASE=http://127.0.0.1:8317/v1 MODEL_ID=gpt-5.6-terra ./run_e2e.sh
#
# 1. bundle install (into ./.bundle-vendor) and print the gem versions
# 2. rake test: WebMock stand-in for the model and for Future AGI; no network needed
# 3. app.rb scenarios (chat stream tool agent session error), real model, real Future AGI
#      metadata only (default)        project $FI_PROJECT_NAME
#      FI_CAPTURE_CONTENT=1 (opt-in)  project $FI_PROJECT_NAME-content
#
# Needs Ruby >= 3.2 on PATH. Knobs: RUBY_LLM_VERSION (default 1.16.0), SCENARIOS, SKIP_TESTS=1,
# MARKER (text planted in prompt, tool argument and tool result for the privacy scan).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-https://api.futureagi.com}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-ruby-llm-e2e}"
export MARKER="${MARKER:-RLLM$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')}"
SCENARIOS="${SCENARIOS:-chat stream tool agent session error}"
export BUNDLE_PATH="${BUNDLE_PATH:-$HERE/.bundle-vendor}"

bundle install --quiet
bundle exec ruby -e 'require "ruby_llm"; require "opentelemetry-instrumentation-ruby_llm"; require "opentelemetry/sdk"; require "opentelemetry/exporter/otlp"
  puts "versions: ruby #{RUBY_VERSION} ruby_llm #{RubyLLM::VERSION} instrumentation #{OpenTelemetry::Instrumentation::RubyLLM::VERSION} sdk #{OpenTelemetry::SDK::VERSION} exporter-otlp #{OpenTelemetry::Exporter::OTLP::VERSION}"'
[ "${SKIP_TESTS:-0}" = "1" ] || bundle exec rake test

fail=0
run_scenario() {  # the error scenario is expected to report ok=false
  local out want
  out="$(bundle exec ruby app.rb "$1" 2>/dev/null | grep '^RESULT' || true)"
  echo "${out:-RESULT missing for $1}"
  if [ "$1" = "error" ]; then want='"ok":false'; else want='"ok":true'; fi
  echo "$out" | grep -q "$want" || fail=1
}
echo "== metadata only (default): project=$FI_PROJECT_NAME marker=$MARKER  traces -> $FI_BASE_URL"
for s in $SCENARIOS; do run_scenario "$s"; done
echo "== content opt-in (FI_CAPTURE_CONTENT=1): project=$FI_PROJECT_NAME-content"
export FI_CAPTURE_CONTENT=1 FI_PROJECT_NAME="$FI_PROJECT_NAME-content"
for s in $SCENARIOS; do run_scenario "$s"; done
exit $fail
