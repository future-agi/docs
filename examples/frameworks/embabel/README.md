# Embabel tracing to Future AGI

Runnable companion to the docs page `docs/integrations/frameworks/embabel`:
a Spring Boot app with one Embabel agent and one tool, whose traces go to Future AGI through
Embabel's observability starter and Spring Boot's OTLP exporter. There is no traceAI package.

Tested with Embabel 1.5.3 (and 1.5.2), Spring Boot 4.1.1, OpenTelemetry Java 1.62.0, JDK 21, Maven 3.10.

| File | What it is |
| --- | --- |
| `pom.xml` | Embabel starter, OpenAI-compatible model starter, observability starter, `opentelemetry-exporter-otlp` |
| `src/main/resources/application.yml` | The tracing configuration the page documents |
| `src/main/java/.../FutureAgiTracingConfiguration.java` | The two beans the page documents: the resource with `project_name`, and the exporter wrapper |
| `src/main/java/.../ErrorTextRedactingSpanExporter.java` | Drops error text (content off) and stack traces (always) |
| `src/main/java/.../WeatherAgent.java`, `WeatherTools.java`, `EmbabelTracingApplication.java` | The agent, its tool, and a runner that runs it once and exits |
| `src/test/java/...` | Unit test of the exporter wrapper; a contract test that runs the app against an in-process OTLP receiver and a stub model and checks path, headers, compression, resource, span tree, and content off/on |
| `run_e2e.sh` | Real run: real model, real Future AGI, content off and on, one tool failure |
| `tools/check_trace.py`, `tools/scan_local_stack.py` | Checks for a self-hosted Future AGI in Docker: stored span tree, and a search of every stored column for a marker |
| `tools/wire_tap.py` | OTLP/HTTP tap that records what the exporter sends (header names only) |
| `tools/replay_fixture.py`, `tools/tests/fixtures/` | A recorded 1.5.3 trace (content off) and a script that replays it to a collector |

## Run the tests (no keys needed)

```bash
mvn -B package                                  # Java 21 and Maven 3.9+
python3 -m pytest tools/tests                    # needs pytest
```

## Run end to end

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_PROJECT_NAME=embabel-e2e               # the opt-in run uses embabel-e2e-optin
# export FI_BASE_URL=http://localhost:4318       # self-hosted; default https://api.futureagi.com
export OPENAI_CUSTOM_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint, ending in /v1
export OPENAI_CUSTOM_API_KEY=...
export OPENAI_CUSTOM_MODELS=gpt-4.1-mini         # the first entry is the model the agent uses
./run_e2e.sh
# Self-hosted Future AGI in Docker: VERIFY_LOCAL_STACK=1 ./run_e2e.sh also checks what was stored.
# RUN_LLM_FAILURE=1 adds a run whose model call fails (about 3 minutes of Embabel retries).
```

The app runs the agent once with `--demo.station-id` and `--demo.question`, then closes the
Spring context, which flushes the spans. A station id starting with `offline-` makes the tool throw.
