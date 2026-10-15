# Pi Coding Agent SDK tracing

Runnable example for [Pi Coding Agent SDK tracing](https://docs.futureagi.com/docs/integrations/coding-agents/pi-sdk): one `createAgentSession()` session, traced by [`@traceai/pi-coding-agent`](https://github.com/future-agi/traceAI/tree/main/typescript/packages/traceai_pi_coding_agent) and exported to Future AGI.

| File | What it is |
| --- | --- |
| `trace_session.mjs` | Creates a traced Pi session, runs one prompt, flushes spans |
| `models.example.json` | Pi `models.json` for an OpenAI-compatible endpoint |
| `run_e2e.sh` | Isolated end-to-end run with a throwaway project and a privacy marker |
| `package.json` | Pinned to the tested Pi SDK (1.2.0) |

```bash
npm install
FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=pi-sdk node trace_session.mjs "List the files here"
```

Content (prompts, tool arguments, tool results, answers) is off by default. Set `FI_HIDE_INPUTS=false` and/or `FI_HIDE_OUTPUTS=false` to include it.
