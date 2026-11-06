# Google ADK for Java -> Future AGI (recipe)

Alpha. Companion to the docs page `integrations/traceai/java/google-adk`.

ADK for Java emits OpenTelemetry spans but has no API to hand it an OpenTelemetry instance, so this
example registers a global OpenTelemetry SDK (`GlobalOpenTelemetry.set`) **before any ADK class loads**.

| File | Role |
| --- | --- |
| `FutureAgiTelemetry.java` | Builds and registers the SDK: OTLP/HTTP exporter, both Future AGI headers, resource `project_name`, `fi.span.kind`, `session.id`/`user.id` from Baggage. Does not import ADK. |
| `ContentFilterExporter.java` | Removes prompts, responses, tool args/results, raw error text and span events unless `FI_ADK_CAPTURE_CONTENT=true`. |
| `Main.java` | `happy`, `error` and `late` (negative control) scenarios. |
| `Scenarios.java` | The ADK agent with one tool. Only reached after registration. |

## Run

```bash
export FI_BASE_URL=http://localhost:14338 FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=adk-java-example
export OPENAI_BASE_URL=https://api.openai.com/v1 OPENAI_API_KEY=... OPENAI_MODEL=gpt-4o-mini
./run_e2e.sh                       # tests + happy + error + content-on + late
ADK_VERSION=1.4.0 ./run_e2e.sh     # the older version leg
```

Tested: google-adk 1.12.0 and 1.4.0, OpenTelemetry 1.51.0, JDK 21 (release 17), Maven 3.9.
