# OpenCode to Future AGI

An OpenCode plugin that exports one trace per OpenCode session to Future AGI over
OTLP/HTTP. Docs page: `src/pages/docs/integrations/coding-agents/opencode.mdx`.

| File | Purpose |
| --- | --- |
| `futureagi-otlp.ts` | The plugin. Copy it to `.opencode/plugins/` in a project. No npm dependencies. |
| `futureagi-otlp.test.ts` | Contract tests (no network). `node --test futureagi-otlp.test.ts` on Node >= 23.6. |
| `fixtures/opencode-1.19.0-session.json` | Event and hook order recorded from a real OpenCode 1.19.0 run, bodies replaced with markers. |
| `run_e2e.sh` | Runs one real OpenCode session in a throwaway project with the plugin installed. |

Tested with OpenCode 1.19.0 (`opencode-ai` on npm).

## Quick start

```bash
mkdir -p .opencode/plugins
cp futureagi-otlp.ts .opencode/plugins/
export FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-opencode-project
opencode
```

Content (prompts, answers, tool arguments and output, error text, session titles,
the project directory) is off by default. Set `FI_CAPTURE_CONTENT=true` to export it,
capped at 4096 UTF-8 bytes per field with common key patterns redacted.

Spans are sent each time a session goes idle, together with a fresh copy of the
session span. At a normal exit, `dispose` sends whatever is still open.
