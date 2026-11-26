# Gemini Go example

The complete program for the [Gemini Go guide](https://docs.futureagi.com/docs/integrations/traceai/go/gemini): a small
weather agent on the Google Gen AI Go SDK (`google.golang.org/genai`, Gemini Developer API) traced with
`github.com/future-agi/traceAI/go/genai`.

One run is one trace: an agent span, an LLM span that asks for `get_weather`, the tool span, and the final answer
(streamed with `-stream`). `-fail` adds one call to a model that does not exist, to show an ERROR span.

Custom agent and tool spans carry only identity, session and status metadata, not prompts, answers, tool arguments
or results. The traced client's content follows the guide's privacy settings. In v0.1.1, text-only hiding does not
redact arbitrary `input.value` or `output.value` attributes passed to `TraceConfig.SetAttributes`; this example
omits them. Privacy switches affect telemetry, not the answer printed to your terminal.

## Run it

Needs Go 1.26 or later, a Future AGI key pair and a Gemini Developer API key.

```bash
go mod init example.com/gemini-go-example
go get github.com/future-agi/traceAI/go/genai@v0.1.1 google.golang.org/genai@latest
go get go.opentelemetry.io/otel/sdk go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp
go mod tidy

export FI_API_KEY="your-futureagi-api-key"
export FI_SECRET_KEY="your-futureagi-secret-key"
export FI_PROJECT_NAME="gemini-go-example"
export GEMINI_API_KEY="your-gemini-api-key"
go run . -stream -fail
```

`FI_BASE_URL` is optional (default `https://api.futureagi.com`). `-model` (or `GEMINI_MODEL`) picks the model.
