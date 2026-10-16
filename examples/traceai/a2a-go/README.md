# A2A Go example

This folder backs [`src/pages/docs/integrations/traceai/go/a2a.mdx`](../../../src/pages/docs/integrations/traceai/go/a2a.mdx).
`main.go` is the program the page walks through: an agent that calls a remote agent over the A2A protocol with the
official Go SDK (`github.com/a2aproject/a2a-go/v2`), traced with `github.com/future-agi/traceAI/go/a2a`. It is the same
program as `go/a2a/example/main.go` in traceAI.

| File | What it does |
| --- | --- |
| `main.go` | Agent span, one A2A call (streamed with `-stream`), and with `-fail` a second call the demo agent answers with a failed task. Without `-agent-url` it starts a demo remote agent on 127.0.0.1 built with a2a-go's own server package; that agent reads `traceparent`, so its spans (and its model call, when `OPENAI_API_KEY` is set) join the trace. Exports with the stock OTLP/HTTP exporter: both Future AGI headers, `project_name`, no gzip, flush on exit. |
| `run_e2e.sh` | Builds `main.go` the way the page says (`go mod init`, `go get`, `go build`) in a temporary module and sends three runs: default capture streamed with a failed task, default capture not streamed, and `FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true` streamed with a failed task. Prints each trace id and the two privacy markers. Never prints a key. |
| `tests/` | Checks that every Go snippet on the page is an excerpt of `main.go`, that the exporter settings Future AGI needs are present, and that the page states the tested versions, the privacy switches and how it differs from the Python package. No network, no Go toolchain. |

## Run it

Needs Go 1.26 or later (or `GOTOOLCHAIN=auto` with network access) and a Future AGI key pair. An OpenAI key (or any
OpenAI-compatible endpoint through `OPENAI_BASE_URL`) is optional: without it the demo agent echoes.

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_PROJECT_NAME=a2a-go-example             # optional
export FI_BASE_URL=https://api.futureagi.com      # optional; your collector when self-hosting
export OPENAI_API_KEY=... MODEL=gpt-4.1-mini      # optional
./run_e2e.sh
```

`TRACEAI_GO_A2A_REF` picks the traceAI module version (default `latest`) and `A2A_GO_VERSION` the a2a-go version
(default `v2.6.0`). Until traceAI PR #261 is merged, set the ref to the PR commit and fetch it straight from GitHub:

```bash
GOPRIVATE=github.com/future-agi/traceAI TRACEAI_GO_A2A_REF=dc4879f14bef ./run_e2e.sh
```

Then open the project in Future AGI Observe. Search for the printed `MARK_DEFAULT` value: it is in the inputs and
outputs of the first run. Search for `MARK_HIDDEN`: it is nowhere, because the third run hides content.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
