# OpenAI Go example

This folder backs [`src/pages/docs/integrations/traceai/go/openai.mdx`](../../../src/pages/docs/integrations/traceai/go/openai.mdx).
`main.go` is the program the page walks through: a small weather agent on the official OpenAI Go SDK
(`github.com/openai/openai-go/v3`) traced with `github.com/future-agi/traceAI/go/openai`. It is the same program as
`go/openai/example/main.go` in traceAI.

| File | What it does |
| --- | --- |
| `main.go` | Agent span, a chat completion that asks for `get_weather`, the tool span, and the final answer (streamed with `-stream`). `-fail` adds one call to a model that does not exist, to show an ERROR span. Exports with the stock OTLP/HTTP exporter: both Future AGI headers, `project_name`, no gzip, flush on exit. |
| `run_e2e.sh` | Builds `main.go` the way the page says (`go mod init`, `go get`, `go build`) in a temporary module and sends three runs: default capture with a stream and a failing call, default capture without a stream, and `FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true` with a stream and a failing call. Prints each trace id and the two privacy markers. Never prints a key. |
| `tests/` | Checks that every Go snippet on the page is an excerpt of `main.go`, that the exporter settings Future AGI needs are present, and that the page states the tested versions, the privacy switches and how it differs from the other OpenAI integrations. No network, no Go toolchain. |

## Run it

Needs Go 1.26 or later (or `GOTOOLCHAIN=auto` with network access), a Future AGI key pair and an OpenAI key
(or any OpenAI-compatible endpoint through `OPENAI_BASE_URL`).

```bash
export FI_API_KEY=... FI_SECRET_KEY=... OPENAI_API_KEY=...
export FI_PROJECT_NAME=openai-go-example          # optional
export FI_BASE_URL=https://api.futureagi.com      # optional; your collector when self-hosting
export MODEL=gpt-4.1-mini                         # optional
./run_e2e.sh
```

`TRACEAI_GO_OPENAI_REF` picks the traceAI module version (default `latest`). Set the ref to a release version or a commit to pin the module.

Then open the project in Future AGI Observe. Search for the printed `MARK_DEFAULT` value: it is in the inputs and
outputs of the first run. Search for `MARK_HIDDEN`: it is nowhere, because the third run hides content.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
