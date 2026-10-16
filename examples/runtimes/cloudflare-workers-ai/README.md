# Cloudflare Workers AI tracing recipe (example)

Companion of `src/pages/docs/integrations/runtimes/cloudflare-workers-ai.mdx`. One request is one trace
(`worker.fetch` -> `workers_ai.run`), exported from inside the Worker isolate and awaited before the `Response` returns.

- `src/tracing.ts`, `src/index.ts`: the recipe (copy these).
- `src/e2e-entry.ts`: STANDIN. Replaces `env.AI` for local runs; forwards to an OpenAI-compatible endpoint. Test-only.
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
