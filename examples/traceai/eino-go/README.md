# CloudWeGo Eino Go example

This folder backs the [CloudWeGo Eino guide](../../../src/pages/docs/integrations/traceai/go/eino.mdx).
`main.go` runs an Eino ADK `ChatModelAgent` with the eino-ext OpenAI chat model and a `get_weather` tool through
`adk.Runner`. The maintained `github.com/future-agi/traceAI/go/eino` handler exports its spans to Future AGI using
the stock OpenTelemetry OTLP/HTTP exporter.

## Run the example

You need Go 1.26 or later, a Future AGI key pair and an OpenAI key. Set `OPENAI_BASE_URL` if you use an
OpenAI-compatible endpoint instead.

From the root of your docs repository checkout, initialize this example's module and install its dependencies:

```bash
cd examples/traceai/eino-go
go mod init example.com/eino-go-example
go get github.com/future-agi/traceAI/go/eino@v0.1.0 github.com/cloudwego/eino@v0.9.21
go get github.com/cloudwego/eino-ext/components/model/openai@v0.1.13
go get go.opentelemetry.io/otel/sdk@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.47.0
go mod tidy
```

If you already initialized the module, skip `go mod init`. Keep this directory selected for the remaining commands:

```bash
export FI_API_KEY="your-futureagi-api-key"
export FI_SECRET_KEY="your-futureagi-secret-key"
export FI_PROJECT_NAME="eino-go-example"
export OPENAI_API_KEY="your-openai-api-key"
export MODEL="gpt-4.1-mini"
go run . -stream -fail
```

`FI_BASE_URL` is optional and defaults to `https://api.futureagi.com`; set it to your collector when self-hosting.
The program prints one trace ID per question. Open **Observe → your project → Tracing** to see the request,
agent, graph, model and tool spans. `-stream` streams the reply; `-fail` adds a second run with a nonexistent
model to show an error trace.

Content is captured by default. Set `FI_HIDE_INPUTS=true` and `FI_HIDE_OUTPUTS=true` before running if inputs
and outputs must stay in the process. Message-specific switches do not sanitize Agentic or generic JSON
payloads; see the guide's [privacy section](../../../src/pages/docs/integrations/traceai/go/eino.mdx#privacy).

## Page contract tests

The offline tests check the page's Go snippets against `main.go` and its exporter configuration. From this directory:

```bash
python3 -m unittest discover -s tests -v
```
