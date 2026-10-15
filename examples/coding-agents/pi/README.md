# Pi to Future AGI

A Pi extension that exports one trace per Pi session to Future AGI over
OTLP/HTTP. Docs page: `src/pages/docs/integrations/coding-agents/pi.mdx`.

| File | Purpose |
| --- | --- |
| `futureagi-otlp.ts` | The extension. Copy it to `~/.pi/agent/extensions/` or a trusted project's `.pi/extensions/`. No npm dependencies. |
| `futureagi-otlp.test.ts` | Contract tests (no network). `node --test futureagi-otlp.test.ts` on Node >= 22.18. |
| `fixtures/pi-1.2.0-session.jsonl` | Extension event stream recorded from a real Pi 1.2.0 `pi -p` run, bodies replaced with markers. |
| `run_e2e.sh` | Runs one real Pi session in a throwaway project with the extension installed. |
| `models.example.json` | Example `models.json` for an OpenAI-compatible endpoint, used with `PI_MODELS_JSON`. |

Tested with Pi 1.2.0 (`@earendil-works/pi-coding-agent` on npm). This is for
upstream Pi (`pi`), not Oh My Pi (`omp`) and not the Pi SDK.

## Quick start

```bash
mkdir -p ~/.pi/agent/extensions
cp futureagi-otlp.ts ~/.pi/agent/extensions/
export FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-pi-project
pi
```

Content (prompts, answers, tool arguments and results, session names) is off by
default. Set `FI_CAPTURE_CONTENT=true` to export it, capped at 4 KiB per field
with common key patterns redacted.
