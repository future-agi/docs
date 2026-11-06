# Koog -> Future AGI (recipe)

Alpha. Companion to the docs page `/docs/integrations/frameworks/koog` (`src/pages/docs/integrations/frameworks/koog.mdx`).

Koog's `OpenTelemetry` feature already creates spans for agent creation, each run, strategy nodes,
model calls and tool calls. This example sends them to Future AGI over OTLP/HTTP. There is no
Future AGI library; copy the two `FutureAgi*` files into your project.

| File | Role |
| --- | --- |
| `src/main/kotlin/.../FutureAgiTelemetry.kt` | Builds the Kotlin OpenTelemetry SDK for Koog (`setSdk`): OTLP/HTTP exporter to `{FI_BASE_URL}/tracer/v1/traces`, both Future AGI headers, no compression, `project_name` on the resource, and a `shutdown()` that flushes first. |
| `src/main/kotlin/.../FutureAgiSpanExporter.kt` | Wraps the exporter: content stays out unless `FI_KOOG_CAPTURE_CONTENT=true` (masks Koog's content attributes, blanks raw error text, drops events; stack traces are emptied even with the opt-in), adds `fi.span.kind` where Future AGI would show `unknown`, copies `gen_ai.conversation.id` to `session.id`, and waits for each HTTP export. |
| `src/main/kotlin/.../WeatherAgent.kt`, `Main.kt` | One agent with one tool. Scenarios `happy`, `tool-error`, `model-error`. |
| `src/main/kotlin/.../quickstart/Quickstart.kt` | The page's step 4 snippet, compiled and runnable (`gradle quickstart`). |
| `src/test/kotlin/...` | JUnit tests. They run a real Koog agent against a local fake OpenAI endpoint (test stand-in) and an in-memory or local recording exporter. No network. |
| `fixtures/koog-1.3.0-weather.otlp.json` | One real Koog 1.3.0 run (content off), recorded as OTLP/JSON with `gradle recordFixture`. |
| `tools/replay_fixture.py` | Replays the fixture into a Future AGI project with fresh ids and timestamps. Python standard library, no JDK. Stands in for the shared round-trip harness until it exists. |
| `tools/test_replay_fixture.py`, `tools/test_page.py` | Offline checks: fixture shape and replay, and that the docs page snippets, versions, env names and links match this project. |

## Run

```bash
export FI_BASE_URL=https://api.futureagi.com FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=koog-example
export OPENAI_API_KEY=... OPENAI_BASE_URL=https://api.openai.com OPENAI_MODEL=gpt-5.6-luna   # base URL without /v1
./run_e2e.sh                      # tests + happy + tool-error + model-error + content-on (+ tool-error) + quickstart + replay
KOOG_VERSION=1.2.0 ./run_e2e.sh   # the older version leg
gradle test                       # Kotlin tests only (no network)
(cd tools && python3 -m unittest test_replay_fixture test_page)   # offline Python checks
```

Needs JDK 17+ and Gradle on PATH (set `GRADLE=` to use another binary). Tested: Koog 1.3.0 on JDK 21 and
JDK 17, Koog 1.2.0 on JDK 21; OpenTelemetry Java 1.61.0, Kotlin 2.3.10 (bytecode 17), Gradle 9.8.1.

`FI_KOOG_CAPTURE_CONTENT=true` turns content capture on; it is off by default (see the page's Privacy section).
