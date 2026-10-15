# Oh My Pi to Future AGI

An omp hook that exports one trace per Oh My Pi session to Future AGI over
OTLP/HTTP. Docs page: `src/pages/docs/integrations/coding-agents/oh-my-pi.mdx`.

Only the omp.sh fork is supported: binary `omp`, npm package
`@oh-my-pi/pi-coding-agent`, source `can1357/oh-my-pi`. Upstream Pi (`pi`) and
other oh-my-pi forks are not.

| File | Purpose |
| --- | --- |
| `futureagi-otlp.ts` | The hook. Copy it to `.omp/hooks/post/` in a project. No npm dependencies. |
| `futureagi-otlp.test.ts` | Contract tests (no network). `node --test futureagi-otlp.test.ts` on Node >= 22.18. |
| `fixtures/omp-18.11.0-print-session.json` | Event order and payload fields recorded from a real omp 18.11.0 run, text replaced with markers. |
| `run_e2e.sh` | Runs one real omp session (`omp -p`) in a throwaway project with the hook installed. |
| `models.yml` | The OpenAI-compatible model entry used for the end-to-end test. Any omp model works. |

Tested with omp 18.11.0.

## Quick start

```bash
mkdir -p .omp/hooks/post
cp futureagi-otlp.ts .omp/hooks/post/
export FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-omp-project
omp
```

Content (prompts, answers, tool arguments and results, tool intents, error text)
is off by default. Set `FI_CAPTURE_CONTENT=true` to export it, capped at 4 KiB per
field with common key patterns redacted.
