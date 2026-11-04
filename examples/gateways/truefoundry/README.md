# TrueFoundry client tracing example

Trace an OpenAI-compatible request through your TrueFoundry gateway with the maintained `traceai-openai` instrumentor. See the [client tracing guide](../../../src/pages/docs/integrations/gateways/truefoundry.mdx) for setup and span fields.

## Install

Use Python 3.10 to 3.13. From this directory:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Set `FI_API_KEY` and `FI_SECRET_KEY` for Future AGI. Set `TFY_API_KEY` to your TrueFoundry token and `TFY_MODEL` to an authorized `provider_account/model_name` from the Playground code snippet.

`TFY_BASE_URL` defaults to `https://gateway.truefoundry.ai`. For a self-hosted gateway, copy the base URL from the Playground. For self-hosted Future AGI, set `FI_BASE_URL` to its host; the SDK uses `/tracer/v1/traces` on that host.

Prompts, responses, tool arguments and error details are captured by default. To hide them from traceAI spans, set these before running:

```bash
export FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true
export FI_HIDE_INPUT_MESSAGES=true FI_HIDE_OUTPUT_MESSAGES=true
export FI_HIDE_LLM_INVOCATION_PARAMETERS=true FI_HIDE_ERROR_DETAILS=true
```

Model ids, usage and tool names remain visible. These controls do not scrub your own logs, arbitrary custom attributes or gateway-side telemetry.

## Run

```bash
python client_example.py
python client_example.py --stream "What is the capital of France?"
```

The first command runs an order assistant with a tool call. The second consumes a streamed response and requests usage. Open **Observe** and select `truefoundry-gateway`, or the name you set with `FI_PROJECT_NAME`.

## Tests and development fixtures

```bash
pip install -r requirements-test.txt
pytest tests -q
```

The tests use real released Python clients, fake gateway transports and loopback OTLP receivers. They check client model fields, sync/async streaming and failures, content/error hiding, the exact guide snippet, and protobuf/JSON serialization with and without gzip. They do not contact a vendor or establish native gateway-to-Future-AGI compatibility.

`standin_gateway.py`, `native/`, `tools/` and `run_e2e.sh` are development fixtures, not a customer gateway-export setup. `native/replay_spans.py` re-encodes Query Spans API data; replayed data is not a native export. Do not point development fixtures at production services or commit captured payloads.

For gateway-wide telemetry, start with TrueFoundry's [native OpenTelemetry export documentation](https://www.truefoundry.com/docs/ai-gateway/export-opentelemetry-data). The client recipe does not join or deduplicate client and gateway traces.
