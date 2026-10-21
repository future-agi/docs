# Pi Coding Agent SDK tracing

Runnable example for [Pi Coding Agent SDK tracing](https://docs.futureagi.com/docs/integrations/coding-agents/pi-sdk): one `createAgentSession()` session, traced by [`@traceai/pi-coding-agent`](https://github.com/future-agi/traceAI/tree/main/typescript/packages/traceai_pi_coding_agent) and exported to Future AGI.

| File | What it is |
| --- | --- |
| `trace_session.mjs` | Creates a traced Pi session, runs one prompt, flushes spans |
| `models.example.json` | Pi `models.json` for an OpenAI-compatible endpoint, with a placeholder gateway URL and model id |
| `run_e2e.sh` | Isolated end-to-end run with a throwaway project and a privacy marker |
| `package.json` | Pinned to the tested Pi SDK (1.2.0) |

`run_e2e.sh` installs `@traceai/pi-coding-agent` from npm. To test a local build instead, pass its `pnpm pack` tarball as `TRACEAI_PI_PACKAGE=/abs/path/traceai-pi-coding-agent-0.1.0.tgz`.

Edit `models.example.json` (gateway `baseUrl` and model `id`) or point `PI_MODELS_JSON` at your own Pi `models.json`, then:

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=pi-sdk-e2e \
PI_PROVIDER=my-gateway PI_MODEL=your-model-id MY_GATEWAY_API_KEY=... \
./run_e2e.sh
```

To run the script directly against your own Pi setup (`~/.pi/agent` or `PI_CODING_AGENT_DIR`):

```bash
npm install
FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=pi-sdk node trace_session.mjs "List the files here"
```

`trace_session.mjs` exits with code 1 when the model call failed or was aborted. Content (prompts, tool arguments, tool results, answers, error text) is off by default. Set `FI_HIDE_INPUTS=false` and/or `FI_HIDE_OUTPUTS=false` to include it.
