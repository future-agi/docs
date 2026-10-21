# CloudWeGo Eino Go example

This folder backs [`src/pages/docs/integrations/traceai/go/eino.mdx`](../../../src/pages/docs/integrations/traceai/go/eino.mdx).
`main.go` is the program the page walks through: an Eino ADK `ChatModelAgent` with the eino-ext OpenAI chat model and a
`get_weather` tool, run through `adk.Runner` and traced with `github.com/future-agi/traceAI/go/eino`. It is the same
program as `go/eino/example/main.go` in traceAI.

| File | What it does |
| --- | --- |
| `main.go` | Registers the handler once with `callbacks.AppendGlobalHandlers`, asks the agent one question under a request span (streamed with `-stream`), and with `-fail` asks a second agent whose model does not exist. Exports with the stock OTLP/HTTP exporter: both Future AGI headers, `project_name`, no gzip, flush on exit. Prints one trace id per question. |
| `run_e2e.sh` | Builds `main.go` the way the page says (`go mod init`, `go get`, `go build`) in a temporary module and sends three runs: default capture streamed with the failing run, default capture not streamed, and `FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true` streamed with the failing run. Prints each trace id and the two privacy markers. Never prints a key. |
| `tests/` | Checks that every Go snippet on the page is an excerpt of `main.go`, that the exporter settings Future AGI needs are present, and that the page states the tested versions, the privacy switches and how it differs from the provider Go modules and Eino's own handlers. No network, no Go toolchain. |

## Run it

Needs Go 1.26 or later (or `GOTOOLCHAIN=auto` with network access), a Future AGI key pair and an OpenAI key (or any
OpenAI-compatible endpoint through `OPENAI_BASE_URL`).

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_PROJECT_NAME=eino-go-example            # optional
export FI_BASE_URL=https://api.futureagi.com      # optional; your collector when self-hosting
export OPENAI_API_KEY=... MODEL=gpt-4.1-mini      # OPENAI_BASE_URL optional
./run_e2e.sh
```

`TRACEAI_GO_EINO_REF` picks the traceAI module version (default `latest`), `EINO_VERSION` the Eino version (default
`v0.9.21`) and `EINO_EXT_OPENAI_VERSION` the eino-ext OpenAI model version (default `v0.1.13`). Set the ref to a release version or a commit to pin the module.

Then open the project in Future AGI Observe. Search for the printed `MARK_DEFAULT` value: it is in the inputs of the
first run. Search for `MARK_HIDDEN`: it is nowhere, because the third run hides content.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
