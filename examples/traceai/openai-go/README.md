# OpenAI Go example

This example uses the official OpenAI Go SDK (`github.com/openai/openai-go/v3`) and the released traceAI module (`github.com/future-agi/traceAI/go/openai`). For the full setup and tracing configuration, see the [OpenAI Go integration guide](../../../src/pages/docs/integrations/traceai/go/openai.mdx).

## Run the example

Use Go 1.26 or later. Set your Future AGI and OpenAI credentials, then create a module and install the published dependencies:

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-service OPENAI_API_KEY=...
mkdir openai-go-example
cd openai-go-example
curl -fLO https://raw.githubusercontent.com/future-agi/docs/main/examples/traceai/openai-go/main.go
go mod init example.com/openai-go-example
go get github.com/future-agi/traceAI/go/openai@v0.1.0 \
  github.com/openai/openai-go/v3@v3.78.0 \
  go.opentelemetry.io/otel/sdk@v1.47.0 \
  go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.47.0
go mod tidy
go run . -stream
```

The program sends a chat completion with a tool call, streams the final answer, and exports its spans to your Future AGI project. Set `OPENAI_BASE_URL` if you use a compatible endpoint other than OpenAI's default.
