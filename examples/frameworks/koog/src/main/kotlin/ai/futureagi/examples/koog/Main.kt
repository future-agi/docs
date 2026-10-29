package ai.futureagi.examples.koog

import ai.koog.prompt.executor.clients.openai.OpenAIClientSettings
import ai.koog.prompt.executor.clients.openai.OpenAILLMClient
import ai.koog.prompt.executor.llms.MultiLLMPromptExecutor
import ai.koog.prompt.llm.LLMCapability
import ai.koog.prompt.llm.LLMProvider
import ai.koog.prompt.llm.LLModel
import ai.koog.utils.io.use
import kotlinx.coroutines.runBlocking
import java.util.UUID
import kotlin.system.exitProcess

/**
 * Runs one Koog agent and sends its trace to Future AGI.
 *
 *   happy [reference]       one run with a tool call
 *   tool-error [reference]  the tool throws; the execute_tool span is ERROR
 *   model-error [reference] the model id does not exist; the run fails and is still exported
 *
 * Needs FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME (FI_BASE_URL defaults to https://api.futureagi.com)
 * and OPENAI_API_KEY. OPENAI_BASE_URL (default https://api.openai.com, no /v1 suffix) and OPENAI_MODEL
 * (default gpt-5.6-luna) are optional. Any OpenAI-compatible chat-completions endpoint works.
 */
fun main(args: Array<String>) {
    val scenario = args.getOrElse(0) { "happy" }
    val reference = args.getOrElse(1) { "station-7" }
    val telemetry = FutureAgiTelemetry(FutureAgiTelemetry.Config.fromEnv())
    println("Future AGI: ${telemetry.config}")

    val client = OpenAILLMClient(
        apiKey = System.getenv("OPENAI_API_KEY") ?: error("OPENAI_API_KEY is required"),
        settings = OpenAIClientSettings(baseUrl = System.getenv("OPENAI_BASE_URL") ?: "https://api.openai.com"),
    )
    val model = when (scenario) {
        "model-error" -> customModel("no-such-model-koog")
        else -> customModel(System.getenv("OPENAI_MODEL") ?: "gpt-5.6-luna")
    }
    val tools = when (scenario) {
        "tool-error" -> WeatherTools(reference, failWith = "weather backend unavailable ($reference)")
        else -> WeatherTools(reference)
    }
    val sessionId = System.getenv("KOOG_SESSION_ID") ?: UUID.randomUUID().toString()

    var failed = false
    runBlocking {
        try {
            weatherAgent(MultiLLMPromptExecutor(LLMProvider.OpenAI to client), model, tools, telemetry).use { agent ->
                val answer = agent.run("What is the weather in Paris? Mention reference $reference.", sessionId)
                println("Agent answer: $answer")
            }
        } catch (e: Exception) {
            failed = true
            println("Agent run failed: ${e::class.simpleName}")
        } finally {
            // Always flush before the JVM exits, or the last spans of the run are lost.
            telemetry.shutdown()
        }
    }
    println("Session: $sessionId")
    if (failed && scenario != "model-error") exitProcess(1)
}

/**
 * An OpenAI-compatible chat model by id. Koog's built-in definitions (for example
 * OpenAIModels.Chat.GPT5_6Luna, new in 1.3.0) work the same way for tracing.
 */
fun customModel(id: String): LLModel = LLModel(
    provider = LLMProvider.OpenAI,
    id = id,
    capabilities = listOf(
        LLMCapability.Completion,
        LLMCapability.Tools,
        LLMCapability.ToolChoice,
        LLMCapability.OpenAIEndpoint.Completions,
    ),
    contextLength = 128_000,
)
