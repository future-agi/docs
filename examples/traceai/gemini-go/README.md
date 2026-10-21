# Gemini Go example

This folder backs [`src/pages/docs/integrations/traceai/go/gemini.mdx`](../../../src/pages/docs/integrations/traceai/go/gemini.mdx).
`main.go` is the program the page walks through: a small weather agent on the Google Gen AI Go SDK
(`google.golang.org/genai`, Gemini Developer API) traced with `github.com/future-agi/traceAI/go/genai`. It is the same
program as `go/genai/example/main.go` in traceAI.

| File | What it does |
| --- | --- |
| `main.go` | Agent span, a `GenerateContent` call that asks for `get_weather`, the tool span, and the final answer (streamed with `-stream`). `-fail` adds one call to a model that does not exist, to show an ERROR span. The Gemini client gets `traceaigenai.NewHTTPClient(...)` as `ClientConfig.HTTPClient`. Exports with the stock OTLP/HTTP exporter: both Future AGI headers, `project_name`, no gzip, flush on exit. |
| `run_e2e.sh` | Builds `main.go` the way the page says (`go mod init`, `go get`, `go build`) in a temporary module and sends three runs: default capture with a stream and a failing call, default capture without a stream, and `FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true` with a stream and a failing call. Prints each trace id and the two privacy markers. Never prints a key. |
| `tests/` | Checks that every Go snippet on the page is an excerpt of `main.go`, that the exporter settings Future AGI needs are present, and that the page states the tested versions, the privacy switches, the backend and how it differs from the other Google GenAI integrations. No network, no Go toolchain. |

## Run it

Needs Go 1.26 or later (or `GOTOOLCHAIN=auto` with network access), a Future AGI key pair and a Gemini Developer API
key.

```bash
export FI_API_KEY=... FI_SECRET_KEY=... GEMINI_API_KEY=...
export FI_PROJECT_NAME=gemini-go-example          # optional
export FI_BASE_URL=https://api.futureagi.com      # optional; your collector when self-hosting
export MODEL=gemini-3.8-flash                     # optional
export PAUSE=60                                   # optional; seconds between runs (free-tier rate limits)
./run_e2e.sh
```

`TRACEAI_GO_GENAI_REF` picks the traceAI module version (default `latest`) and `GENAI_VERSION` the SDK version
(default `v1.75.0`). Set the ref to a release version or a commit to pin the module.

Then open the project in Future AGI Observe. Search for the printed `MARK_DEFAULT` value: it is in the inputs and
outputs of the first run. Search for `MARK_HIDDEN`: it is nowhere, because the third run hides content.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
