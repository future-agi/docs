#!/usr/bin/env bash
# Runs the Google ADK for Java tracing example against a Future AGI endpoint.
# Needs: JDK 17+, Maven, FI_BASE_URL, FI_API_KEY, FI_SECRET_KEY, and an OpenAI-compatible model
# (OPENAI_BASE_URL, OPENAI_API_KEY, optional OPENAI_MODEL). Never prints the keys.
set -euo pipefail
cd "$(dirname "$0")"
: "${FI_PROJECT_NAME:=adk-java-example}"; export FI_PROJECT_NAME
ADK_VERSION="${ADK_VERSION:-1.12.0}"
MVN=(mvn -q -B "-Dadk.version=${ADK_VERSION}")

echo "== unit tests (no network, no model)"
"${MVN[@]}" test

M_OFF="ADKOFF$RANDOM$RANDOM"; M_ON="ADKON$RANDOM$RANDOM"; M_ERR="ADKERR$RANDOM$RANDOM"
echo "== happy path, content off (default). marker: $M_OFF"
"${MVN[@]}" exec:java "-Dexec.args=happy $M_OFF"
echo "== failure case (unknown model). marker: $M_ERR"
"${MVN[@]}" exec:java "-Dexec.args=error $M_ERR"
echo "== content on (opt-in). marker: $M_ON"
FI_ADK_CAPTURE_CONTENT=true "${MVN[@]}" exec:java "-Dexec.args=happy $M_ON"
echo "== negative control: ADK class loaded before register"
"${MVN[@]}" exec:java "-Dexec.args=late ADKLATE$RANDOM"

cat <<MSG
Done. In project "$FI_PROJECT_NAME" expect:
  - traces for the happy runs (invocation > invoke_agent > call_llm > execute_tool), one with status ERROR for the failure run
  - $M_OFF and $M_ERR found NOWHERE in stored spans
  - $M_ON found in the gcp.vertex.agent.* span attributes
  - no trace for the 'late' run
MSG
