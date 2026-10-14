# Cursor hook-to-OTLP

This example exports Cursor Agent sessions and tool events through Cursor's command hooks to Future AGI's OTLP/HTTP collector.

## Run the contract test

```bash
./run_contract.sh
```

The test starts a loopback receiver, invokes the same hook command with fixture payloads, and checks:

- `/tracer/v1/traces` is used;
- `X-Api-Key`, `X-Secret-Key`, `project_name`, and `project_type=observe` are present;
- session and tool metadata are exported;
- prompt, tool arguments, tool results, and error text are absent by default;
- opt-in content is capped and secret-like values are redacted.

No Cursor installation, vendor account, API key, or external request is required for the contract test.

## Install in a project

Copy `hooks.json` to `.cursor/hooks.json` and `emit.py` to `.cursor/hooks/emit.py`. Project hooks run from the project root, so the command paths in the example intentionally start with `.cursor/`.

Set these variables in the environment that launches Cursor:

```bash
export FI_OTLP_ENDPOINT=https://api.futureagi.com/tracer/v1/traces
export FI_API_KEY='[REDACTED]'
export FI_SECRET_KEY='[REDACTED]'
export FI_PROJECT_NAME='my-cursor-project'
```

The script does not read Cursor's local database or log files. It receives only the JSON payload Cursor sends to the hook.

## Privacy contract

Content capture is off unless `CURSOR_CAPTURE_CONTENT=true` is set. In the default mode the exporter records session IDs, model/status metadata, tool names, byte counts and SHA-256 digests, not prompt, tool, response, or exception bodies. Captured content is capped at 4 KiB and common key/token formats are redacted before export.

Keep hook output and collector access private. The collector headers are read from environment variables and are never copied into span attributes or logs.

## Unsupported paths

- Cursor Enterprise metrics/logs export is not this integration; it does not provide the application session/tool span tree required here.
- Cursor Tab completion telemetry is not included. Add `beforeTabFileRead`/`afterTabFileEdit` handlers only after defining a separate event mapping.
- Prompt-based hooks are not supported by this recipe; use command hooks so the payload and export path are deterministic.
- This recipe does not claim coverage for Cursor SDK tracing, extension APIs, or provider calls made outside Cursor's hook events.
- A hook can observe only events Cursor emits. If a Cursor version changes payload fields, the exporter keeps the stable metadata and drops unknown content rather than forwarding the payload wholesale.
