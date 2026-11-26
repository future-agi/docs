# Temporal Go tracing example

Runnable source for the [Temporal Go integration guide](../../../src/pages/docs/integrations/frameworks/temporal-go.mdx). The example uses Temporal's official OpenTelemetry extension, not a custom interceptor. It exports only traces.

Requires Go 1.25.4 or later and a Temporal server. Set `FI_API_KEY`, `FI_SECRET_KEY`, and `FI_PROJECT_NAME` in both terminals. Set `TEMPORAL_ADDRESS` for a non-local cluster; the Temporal SDK defaults to localhost:7233. `FI_TRACES_URL` optionally replaces the default Future AGI traces URL. Then run `go run . worker` and `go run . starter Ada` in separate terminals.

Run `go test ./...` to test the provider and workflow/activity span parentage against a loopback OTLP/HTTP receiver using synthetic headers; no account or Temporal server is needed. The activity returns a static greeting. Instrument real model and tool calls inside your activities, not workflow code.
