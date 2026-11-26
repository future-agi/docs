# AWS Lambda tracing lifecycle (Python and Go)

Runnable companion of the page `src/pages/docs/integrations/runtimes/aws-lambda.mdx`: a Lambda handler
that builds the tracer provider once, makes one trace per invocation and flushes before every return,
including the error path. No layer, no ADOT, no AWS call.

| Path | What |
| --- | --- |
| `python/tracing.py`, `python/handler.py` | the recipe (copy these two files) |
| `python/tests/` | 18 tests: fake exporter, a local OTLP receiver, no AWS client |
| `python/local_runner.py` | calls the handler in-process (cold start, then warm) for the end-to-end run |
| `go/tracing/`, `go/handler/` | the same recipe in Go; `go/cmd/function` is the real `lambda.Start` entry point (built, not run) |
| `go/handler/handler_test.go` | the same contract as the Python tests |
| `go/cmd/e2e` | in-process runner for the end-to-end run |
| `run_e2e.sh`, `tools/` | the end-to-end script against a self-hosted Future AGI, and its checks |

## Unit tests (no network beyond 127.0.0.1, no credentials)

```bash
cd python && python -m venv .venv && .venv/bin/pip install -r requirements-test.txt && .venv/bin/python -m pytest -q tests
cd ../go && go test ./...        # needs Go 1.26 (OpenTelemetry Go 1.47 requires it); GOTOOLCHAIN=auto fetches it
```

## End to end against Future AGI

Needs a Future AGI you can read back (self-hosted), its keys, and `fi_verify.py` from the local test
stack.

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338
PYTHON=python/.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh all   # or python | go
```

Scenarios, per language, each in its own project: `happy` (API Gateway v2 event with `traceparent`,
a direct event, an SQS event: three traces, the first one parented), `failure` (the handler raises:
ERROR spans, flushed, and the next warm invocation still works), `privacy` (a unique marker, the
username, the hostname, the home path and `Traceback`/`goroutine` must be absent from every stored
column with the defaults; then the opt-in `LAMBDA_TRACE_CAPTURE_CONTENT=true` stores the marker and
still no username, hostname, path or stack), `nokeys` (handler works, nothing is exported, no project
is created), `dead end` (the collector is unreachable: the invocation still returns).

## Supported scope

This is a local lifecycle example, not an AWS deployment guide. The handler is called in-process with a stand-in context (request id and remaining time). Actual AWS freeze/thaw, hard platform timeouts, SnapStart, provisioned concurrency and response streaming are outside this example’s supported scope.
