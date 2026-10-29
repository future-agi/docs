# Ruby LLM with Future AGI

Runnable companion to the page `docs/integrations/frameworks/ruby-llm`.

- `futureagi_tracing.rb` is the whole integration: OpenTelemetry SDK + OTLP/HTTP exporter (both auth headers, `project_name` resource attribute, no gzip), the `opentelemetry-instrumentation-ruby_llm` instrumentation, and a `SanitizingExporter` that keeps spans metadata-only unless `FI_CAPTURE_CONTENT=1`.
- `app.rb` is a demo with six scenarios: `chat`, `stream`, `tool`, `agent`, `session`, `error`.
- `test/` runs with a WebMock stand-in for the model (canned OpenAI-shaped replies, NOT a real model) and a WebMock stand-in for Future AGI (the real OTLP exporter posts to it). No network needed.
- `run_e2e.sh` installs the gems, runs the tests, then runs the scenarios against a real model and a real Future AGI, once metadata only and once with the opt-in.

Tested: `ruby_llm` 1.16.0 and 1.15.0 with `opentelemetry-instrumentation-ruby_llm` 0.7.1, Ruby 3.2.2 and 3.4.11. `ruby_llm` 2.x is not supported by that instrumentation (it raises `NoMethodError` on `model_id`); `RUBY_LLM_VERSION=2.1.1 bundle install` reproduces it.

```bash
export FI_API_KEY=... FI_SECRET_KEY=... OPENAI_API_KEY=...
# self-hosted Future AGI / OpenAI-compatible endpoint:
# export FI_BASE_URL=http://localhost:4318 OPENAI_API_BASE=http://127.0.0.1:8317/v1 MODEL_ID=my-model
./run_e2e.sh
```

Needs Ruby 3.2 or newer on PATH. Knobs: `RUBY_LLM_VERSION` (default 1.16.0), `SCENARIOS`, `SKIP_TESTS=1`, `FI_PROJECT_NAME`, `MARKER`.
