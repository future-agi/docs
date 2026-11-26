#!/usr/bin/env bash
# TH-8265 local spike. NOT a supported setup: it shows what the third-party @loongsuite/dsh-plugin exports
# when pointed at a local Future AGI. Everything lives under $WORK (default: a fresh temp dir); no global
# config is touched. Secrets are read from the environment and never printed.
#
# needs: node >= 20, npm, a local Future AGI collector, and an OpenAI-compatible endpoint that serves $MODEL
# env  : FI_API_KEY FI_SECRET_KEY FI_BASE_URL (collector, e.g. http://localhost:14338)
#        OPENAI_COMPAT_BASE_URL OPENAI_COMPAT_API_KEY   (any OpenAI-compatible endpoint)
#        MODEL (default gpt-6-luna)  PROJECT (default th8103-rest-deepseek-harness)
#        DSH_VERSION (default 0.2.1-alpha.4)  PLUGIN_VERSION (default 0.1.3)
#        CAPTURE=on|off (default off)  MARKER (default: a unique string)  PROMPT (override)
set -euo pipefail
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}" "${OPENAI_COMPAT_BASE_URL:?}" "${OPENAI_COMPAT_API_KEY:?}"
MODEL="${MODEL:-gpt-6-luna}"; PROJECT="${PROJECT:-th8103-rest-deepseek-harness}"
DSH_VERSION="${DSH_VERSION:-0.2.1-alpha.4}"; PLUGIN_VERSION="${PLUGIN_VERSION:-0.1.3}"
CAPTURE="${CAPTURE:-off}"; MARKER="${MARKER:-MK$(date +%s)$$}"
WORK="${WORK:-$(mktemp -d)}"; mkdir -p "$WORK/install" "$WORK/cwd"
export DSH_HOME="$WORK/home" DSH_TELEMETRY_MODE=DISABLED

if [ ! -x "$WORK/install/node_modules/.bin/dsh" ]; then
  (cd "$WORK/install" && npm init -y >/dev/null && npm install --silent "@deepseek-ai/dsh@$DSH_VERSION" "@loongsuite/dsh-plugin@$PLUGIN_VERSION")
fi
DSH="$WORK/install/node_modules/.bin/dsh"
"$DSH" plugin --profile headless add "@loongsuite/dsh-plugin@$PLUGIN_VERSION" >/dev/null

# custom OpenAI-compatible provider + default model (the key stays in an env var, never in the file)
cat > "$DSH_HOME/profiles/headless/cordis.patch.yml" <<YML
- id: llm-pi-ai
  config:
    providers:
      local:
        apiKeyEnv: OPENAI_COMPAT_API_KEY
        api: openai-completions
        baseURL: !!js process.env.OPENAI_COMPAT_BASE_URL
        models:
          - id: $MODEL
- id: agent-default-model
  config:
    provider: local
    model: $MODEL
YML

# the plugin appends /v1/traces itself only for a BASE endpoint; use the traces-specific variable and
# turn metrics off, because the Future AGI collector accepts traces only
export OTEL_SERVICE_NAME=dsh-spike OTEL_METRICS_EXPORTER=none
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="$FI_BASE_URL/v1/traces"
export OTEL_EXPORTER_OTLP_TRACES_HEADERS="X-Api-Key=$FI_API_KEY,X-Secret-Key=$FI_SECRET_KEY"
export OTEL_RESOURCE_ATTRIBUTES="project_name=$PROJECT"
if [ "$CAPTURE" = on ]; then export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY
else unset OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT; fi

PROMPT="${PROMPT:-Run the shell command: echo ${MARKER}-toolout . Then reply with only its output. Marker ${MARKER}-prompt}"
cd "$WORK/cwd"
"$DSH" --profile headless "$PROMPT" > "$WORK/out.txt" 2> "$WORK/err.txt" || echo "dsh exited $?"
echo "marker=$MARKER capture=$CAPTURE work=$WORK stdout_bytes=$(wc -c < "$WORK/out.txt") stderr_bytes=$(wc -c < "$WORK/err.txt")"
echo "next: python3 e2e/fi_verify.py --project $PROJECT --wait 120 --min-spans 2   (then scan stored rows for $MARKER)"
