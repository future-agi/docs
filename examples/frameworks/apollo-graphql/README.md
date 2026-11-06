# Apollo Server 4 to Future AGI (example)

Runnable companion of the page `src/pages/docs/integrations/frameworks/apollo-graphql.mdx`
(Trace Apollo Server 4). A monolith Apollo Server 4 app, traced with the stock
`@opentelemetry/instrumentation-graphql`, exported over OTLP/HTTP to Future AGI. There is no
Apollo plugin and no traceAI package in this recipe.

Tested: `@apollo/server` 4.13.0, `graphql` 16.14.2, `@opentelemetry/instrumentation-graphql` 0.71.0,
`@opentelemetry/instrumentation-http` 0.223.0, `@opentelemetry/sdk-node` 0.223.0, Node 26.8.1.

| File | What it is |
| --- | --- |
| `instrumentation.mjs` | OpenTelemetry setup. Imported first. |
| `fi-exporter.mjs` | Wraps the OTLP exporter: default export is structure only (see the page). |
| `app.mjs` | The Apollo server: schema, resolvers, one resolver that starts a child span. |
| `server.mjs` | Entrypoint. `./instrumentation.mjs` is imported before `@apollo/server`. |
| `tests/` | `npm test`: fixture tests (real Apollo over HTTP, local OTLP collector). No network, no Apollo account, no model. |
| `run_e2e.sh` | Real run against a Future AGI you can read back, with the privacy proof. |

## Run it

```bash
npm ci
export FI_BASE_URL=https://api.futureagi.com   # or http://localhost:14338 for self-hosted
export FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=apollo-server-4
npm start                                       # http://localhost:4000
curl -s localhost:4000 -H 'content-type: application/json' -d '{"query":"{ hello }"}'
```

Ctrl-C (SIGINT or SIGTERM) stops the server and flushes the last batch of spans.

## Test it

```bash
npm test                                         # fixture tests, AC-01 .. AC-13
VERIFY=/path/to/fi_verify.py ./run_e2e.sh all    # needs FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL of a self-hosted stack
```

## Not covered

Apollo Gateway, Apollo Router, Apollo Studio / GraphOS and Server 5 are out of scope. Do not add
`@opentelemetry/instrumentation-graphql` to a gateway process. No gateway fixture is run here.
