# Pi Coding Agent SDK tracing

Run a Pi SDK session and export its turns, model calls, and tools to Future AGI with the maintained `@traceai/pi-coding-agent` package. See the [integration guide](https://docs.futureagi.com/docs/integrations/coding-agents/pi-sdk) for the trace fields and integration options.

## Prerequisites

- Node.js 22.19 or newer.
- Future AGI API and secret keys.
- Your own model-provider credentials and a model configured in Pi. The script uses `~/.pi/agent`, or `PI_CODING_AGENT_DIR` when set. See [Pi model configuration](https://pi.dev/docs/latest/models).

## Run the application

From this example directory:

```bash
npm install
export FI_API_KEY="your-futureagi-api-key"
export FI_SECRET_KEY="your-futureagi-secret-key"
export FI_PROJECT_NAME="my-pi-agent"
node trace_session.mjs "List the files here"
```

`package.json` pins Pi SDK 1.2.0, `@traceai/pi-coding-agent` 0.1.0, and `@traceai/fi-core` 1.1.1. The script enables only the `read` and `ls` tools, prints the answer and session ID, flushes traces before exiting, and exits with code 1 if the model call failed or was aborted.

To inspect a different project or select a model explicitly:

```bash
PI_CWD="/path/to/your/project" \
PI_PROVIDER="your-provider-id" PI_MODEL="your-model-id" \
node trace_session.mjs "List the files in this folder and read README.md"
```

Set `PI_PROVIDER` and `PI_MODEL` together, using IDs from your Pi configuration. For an OpenAI-compatible endpoint, `models.example.json` shows the provider shape: replace the placeholder URL and model ID, add that provider to your Pi `models.json`, and export `MY_GATEWAY_API_KEY` in the same shell. Do not overwrite an existing configuration or store the key in that file.

For self-hosted Future AGI, set `FI_BASE_URL` to the collector base URL; the exporter appends `/tracer/v1/traces`. If your variables are in a local `.env` file, start with `node --env-file=.env trace_session.mjs "List the files here"` instead.

Open **Observe**, select `my-pi-agent`, and open the newest `invoke_agent pi` trace. Runs sharing a Pi session ID group under **Sessions**.

## Privacy

Prompts, tool arguments, tool results, assistant text, session names, compaction summaries, and error text are hidden by default. Error spans keep `ERROR` status and `error.type`, but have no status message.

- `FI_HIDE_INPUTS=false` captures prompts, tool arguments, tool-call arguments, and session names.
- `FI_HIDE_OUTPUTS=false` captures successful assistant output, tool results, and compaction summaries. It does not enable error text by itself.
- `FI_HIDE_ERROR_DETAILS=false` independently enables error status messages. With outputs hidden, these are limited summaries. Raw provider, failed-tool, and compaction error text requires both `FI_HIDE_OUTPUTS=false` and `FI_HIDE_ERROR_DETAILS=false`.

For ordinary content without error details:

```bash
export FI_HIDE_INPUTS=false
export FI_HIDE_OUTPUTS=false
export FI_HIDE_ERROR_DETAILS=true
node trace_session.mjs "List the files here"
```

Only `false` (case-insensitive, surrounding spaces ignored) enables capture; explicit instrumentation `traceConfig` options take precedence. Error text and captured content can contain source code, account details, and local file paths. Enable capture only for data you intend to send to Future AGI.

Use only one tracing integration per session. If your SDK app binds the Pi CLI tracing extension, disable it for this process to avoid duplicate traces. Do not separately instrument the provider SDK calls that Pi makes.
