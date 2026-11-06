package ai.futureagi.examples.koog

import ai.koog.prompt.executor.clients.openai.OpenAIClientSettings
import ai.koog.prompt.executor.clients.openai.OpenAILLMClient
import ai.koog.prompt.executor.llms.MultiLLMPromptExecutor
import ai.koog.prompt.llm.LLMProvider
import ai.koog.utils.io.use
// OtlpStdoutSpanExporter lives in an internal package in OpenTelemetry Java 1.61. Test scope only.
import io.opentelemetry.exporter.logging.otlp.internal.traces.OtlpStdoutSpanExporter
import kotlinx.coroutines.runBlocking
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Records one real Koog run (real model, content off) as OTLP/JSON, exactly as the recipe would
 * send it, without sending it. The output is the fixture `tools/replay_fixture.py` replays.
 */
fun main(args: Array<String>) {
    val out = File(args.getOrElse(0) { "fixtures/koog-weather.otlp.json" })
    val buffer = ByteArrayOutputStream()
    val recorder = OtlpStdoutSpanExporter.builder().setOutput(buffer).setWrapperJsonObject(true).build()
    val config = FutureAgiTelemetry.Config("http://not-used", "unused", "unused", "koog-fixture")
    val telemetry = FutureAgiTelemetry(config, delegate = recorder)
    val client = OpenAILLMClient(
        apiKey = System.getenv("OPENAI_API_KEY") ?: error("OPENAI_API_KEY is required"),
        settings = OpenAIClientSettings(baseUrl = System.getenv("OPENAI_BASE_URL") ?: "https://api.openai.com"),
    )
    val model = customModel(System.getenv("OPENAI_MODEL") ?: "gpt-5.6-luna")
    runBlocking {
        try {
            weatherAgent(MultiLLMPromptExecutor(LLMProvider.OpenAI to client), model, WeatherTools("station-7"), telemetry)
                .use { it.run("What is the weather in Paris?", "fixture-session") }
        } finally {
            telemetry.shutdown()
        }
    }
    out.parentFile?.mkdirs()
    out.writeText(buffer.toString(Charsets.UTF_8))
    println("Wrote ${out.path}")
}
