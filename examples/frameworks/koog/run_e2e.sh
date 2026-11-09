#!/usr/bin/env bash
# Runs the Koog -> Future AGI example end to end.
# Needs: JDK 17+, Gradle on PATH (or GRADLE=/path/to/gradle), python3,
#        FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL (default https://api.futureagi.com),
#        OPENAI_API_KEY and optionally OPENAI_BASE_URL (no /v1 suffix) and OPENAI_MODEL.
# Never prints the keys.
set -euo pipefail
cd "$(dirname "$0")"
: "${FI_PROJECT_NAME:=koog-example}"; export FI_PROJECT_NAME
GRADLE="${GRADLE:-gradle}"
G=("$GRADLE" -q --console=plain "-PkoogVersion=${KOOG_VERSION:-1.3.0}")

echo "== unit tests (no network: fake model, in-memory and local recording exporters)"
"${G[@]}" test
(cd tools && python3 -m unittest -q test_replay_fixture test_page)

M_OFF="KOOGOFF$RANDOM$RANDOM"; M_TERR="KOOGTERR$RANDOM$RANDOM"; M_MERR="KOOGMERR$RANDOM$RANDOM"; M_ON="KOOGON$RANDOM$RANDOM"
M_ONERR="KOOGONERR$RANDOM$RANDOM"
echo "== happy path, content off (default). marker: $M_OFF"
"${G[@]}" run --args="happy $M_OFF"
echo "== failure case 1: the tool throws. marker: $M_TERR"
"${G[@]}" run --args="tool-error $M_TERR"
echo "== failure case 2: unknown model id. marker: $M_MERR"
"${G[@]}" run --args="model-error $M_MERR"
echo "== content on (opt-in). marker: $M_ON"
FI_KOOG_CAPTURE_CONTENT=true "${G[@]}" run --args="happy $M_ON"
echo "== content on, the tool throws. marker: $M_ONERR"
FI_KOOG_CAPTURE_CONTENT=true "${G[@]}" run --args="tool-error $M_ONERR"
if [ "${KOOG_VERSION:-1.3.0}" = "1.3.0" ]; then
  echo "== the docs page quickstart as written (OpenAIModels.Chat.GPT5_6Luna, content off)"
  "${G[@]}" quickstart
else
  echo "== quickstart skipped: it uses OpenAIModels.Chat.GPT5_6Luna, new in Koog 1.3.0"
fi
echo "== replay the recorded fixture into ${FI_PROJECT_NAME}-replay (no JDK needed for this step)"
python3 tools/replay_fixture.py fixtures/koog-1.3.0-weather.otlp.json --project "${FI_PROJECT_NAME}-replay" \
  --base-url "${FI_BASE_URL:-https://api.futureagi.com}"

cat <<MSG
Done. In project "$FI_PROJECT_NAME" expect six traces:
  create_agent > invoke_agent > strategy single_run > node ... > chat <model> / execute_tool getWeather
  - the tool-error trace has execute_tool getWeather with status ERROR and an empty status message
  - the model-error trace has chat, node nodeCallLLM and invoke_agent with status ERROR (Koog leaves create_agent OK)
  - the quickstart trace (session user-42-chat-7) has the same tree as the happy path
  - $M_OFF, $M_TERR and $M_MERR are found NOWHERE in the stored spans
  - $M_ON appears in gen_ai.input.messages / gen_ai.output.messages / gen_ai.tool.call.* of the opt-in trace
  - $M_ONERR appears with the error text in the opt-in tool-error trace, and no stack trace ("\tat ...") is stored
And one replayed trace in "${FI_PROJECT_NAME}-replay".
MSG
