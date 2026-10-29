package ai.futureagi.examples.koog

import ai.koog.prompt.executor.clients.openai.OpenAIClientSettings
import ai.koog.prompt.executor.clients.openai.OpenAILLMClient
import ai.koog.prompt.executor.llms.MultiLLMPromptExecutor
import ai.koog.prompt.llm.LLMProvider
import ai.koog.utils.io.use
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** What actually goes over the wire: endpoint, both headers, no gzip, protobuf, resource, flush. */
class OtlpWireTest {
    private val marker = "WIREMARK93"

    @Test
    fun `exports OTLP protobuf to tracer v1 traces with both headers and no compression`() {
        RecordingOtlpReceiver().use { receiver ->
            FakeOpenAI(marker).use { fake ->
                val config = FutureAgiTelemetry.Config(receiver.baseUrl, "fi-api-key-123", "fi-secret-456", "wire-project")
                val telemetry = FutureAgiTelemetry(config)
                val client = OpenAILLMClient(apiKey = "model-key-789", settings = OpenAIClientSettings(baseUrl = fake.baseUrl))
                runBlocking {
                    try {
                        weatherAgent(MultiLLMPromptExecutor(LLMProvider.OpenAI to client), customModel("fake-model"), WeatherTools(marker), telemetry)
                            .use { it.run("Weather in Paris? ref $marker", "wire-session") }
                    } finally {
                        telemetry.shutdown()
                    }
                }
            }
            assertTrue(receiver.requests.isNotEmpty(), "nothing was exported")
            receiver.requests.forEach { r ->
                assertEquals("/tracer/v1/traces", r.path)
                assertEquals("fi-api-key-123", r.headers["x-api-key"])
                assertEquals("fi-secret-456", r.headers["x-secret-key"])
                assertEquals("application/x-protobuf", r.headers["content-type"])
                assertFalse(r.headers["content-encoding"].orEmpty().contains("gzip"), "Future AGI rejects gzip")
            }
            val body = receiver.requests.joinToString("") { it.body.decodeToString() }
            assertTrue("project_name" in body && "wire-project" in body)
            // create_agent ends last (when the agent closes): seeing it proves the final batch was flushed.
            listOf("create_agent weather-agent", "invoke_agent weather-agent", "chat fake-model", "execute_tool getWeather").forEach {
                assertTrue(it in body, "missing span $it")
            }
            assertFalse(marker in body, "content must be off by default")
            listOf("fi-api-key-123", "fi-secret-456", "model-key-789").forEach { assertFalse(it in body, "credential in payload") }
        }
    }
}
