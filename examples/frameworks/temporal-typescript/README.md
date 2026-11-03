# Temporal TypeScript tracing example

Follow the [Temporal TypeScript guide](../../../src/pages/docs/integrations/frameworks/temporal-typescript.mdx).

Run `npm ci`, set `FI_API_KEY`, `FI_SECRET_KEY`, and `FI_PROJECT_NAME`, and start `temporal server start-dev`. In separate terminals, run `npm run worker` and `npm run start`. The Worker waits for the first workflow; stop it with Ctrl+C to flush buffered traces.

Use `FI_TRACES_URL` for a self-hosted Future AGI OTLP/HTTP endpoint, and `TEMPORAL_ADDRESS` to connect both processes to a non-default Temporal server. The workflow contains only deterministic operations; replace the activity body with your own model and tool calls and their own instrumentation.
