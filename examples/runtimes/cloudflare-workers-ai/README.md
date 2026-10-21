# Cloudflare Workers AI tracing recipe (example)

Companion of `src/pages/docs/integrations/runtimes/cloudflare-workers-ai.mdx`. One request is one trace
(`worker.fetch` -> `workers_ai.run`), exported from inside the Worker isolate and awaited before the `Response` returns.

- `src/tracing.ts`, `src/index.ts`: the recipe (copy these).
- `src/e2e-entry.ts`: STANDIN. Replaces `env.AI` for local runs; forwards to an OpenAI-compatible endpoint. Test-only.
- `src/live-entry.ts` + `wrangler.live.jsonc`: live vendor verification (2026-10-19). `env.AI` is backed by the real Workers AI REST API (`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` in `.dev.vars`), same handler. Also serves `/bad-model` for a real vendor error. Not part of the recipe.
- `wrangler.jsonc`: the Worker as deployed (real `ai` binding). `wrangler.e2e.jsonc`: the local run.
- `test/handler.test.ts`: 14 unit tests, fake `env.AI` and fake `fetch`, no network.
- `run_e2e.sh`: real `workerd` (via `wrangler dev --local`) against a local Future AGI. Never deploys, never calls Cloudflare.

```bash
npm install
npm test            # unit tests, no network
npm run typecheck
# end to end (needs a local Future AGI you can read back, and an OpenAI-compatible endpoint for the stand-in):
VERIFY=/path/to/fi_verify.py ./run_e2e.sh
```

## Live vendor verification (2026-10-19)

Run against the real Workers AI API (`@cf/meta/llama-3.1-8b-instruct`) through `src/live-entry.ts` (REST-backed `env.AI`; the real `ai`
binding needs a Workers-scripts token for `wrangler dev`). Real `usage` (prompt/completion tokens) stored on the span; a bad model id gives
ERROR spans and a 502; marker/username/hostname/path/token absent from every stored column by default. Finding: against a slow collector
the 2 s `FLUSH_BUDGET_MS` can drop the trace (request still 200); raise it if needed. Use `127.0.0.1`, not `localhost`, for a local collector.
