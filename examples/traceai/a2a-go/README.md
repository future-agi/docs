# A2A Go example

This application accompanies the [A2A Go guide](../../../src/pages/docs/integrations/traceai/go/a2a.mdx). It uses the released traceAI A2A v0.1.1 example: the maintained client constructor and server interceptor connect both sides of an A2A call in one trace.

## Run

You need Go 1.26.0 or later and a Future AGI key pair. From this directory:

```bash
go mod init example.com/a2a-go-example
go get github.com/future-agi/traceAI/go/a2a@v0.1.1 github.com/a2aproject/a2a-go/v2@v2.7.0
go get go.opentelemetry.io/otel/sdk@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.47.0
go mod tidy
export FI_API_KEY="your-futureagi-api-key"
export FI_SECRET_KEY="your-futureagi-secret-key"
export FI_PROJECT_NAME="a2a-go-example"
go run . -stream -fail
```

The application starts a local echo agent and exports to Future AGI. For self-hosting, set `FI_BASE_URL` to your API base URL. Open your project in Observe and find the printed trace ID.

- Omit `-stream` to send a single-response request.
- Use `-agent-url https://your-agent.example` to call your own agent. `-fail` is specific to the demo agent.
- Optionally set your own `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `MODEL` to let the demo call an OpenAI-compatible model instead of echoing.
- Set `FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_ERROR_DETAILS=true` before starting the application to redact message content and error details. Apply the same policy separately to a remote server.

## Maintainer checks

The `A2A Go documentation` GitHub workflow runs the page contracts, builds the example with the pinned dependencies, and runs the Go wire tests on a hosted runner. The wire tests use loopback A2A/OTLP servers and a fake model transport; they need no account or external service.

`run_e2e.sh` is an optional maintainer check against a configured Future AGI project. It uses traceAI v0.1.1 and a2a-go v2.7.0 by default and runs streamed, single-response and hidden-content cases. `TRACEAI_GO_A2A_REF` and `A2A_GO_VERSION` override those dependencies; keep them compatible. This script sends synthetic data to the configured project and requires your own keys.
