// The "Install it on your agent" snippet from the docs page, verbatim below the package line.
// tools/test_page.py fails if the page and this file drift apart. Run it with `gradle quickstart`.
package ai.futureagi.examples.koog.quickstart

import ai.futureagi.examples.koog.FutureAgiTelemetry
import ai.koog.agents.core.agent.AIAgent
import ai.koog.agents.core.tools.ToolRegistry
import ai.koog.agents.core.tools.annotations.LLMDescription
import ai.koog.agents.core.tools.annotations.Tool
import ai.koog.agents.core.tools.reflect.ToolSet
import ai.koog.agents.features.opentelemetry.feature.OpenTelemetry
import ai.koog.prompt.executor.clients.openai.OpenAIClientSettings
import ai.koog.prompt.executor.clients.openai.OpenAILLMClient
import ai.koog.prompt.executor.clients.openai.OpenAIModels
import ai.koog.prompt.executor.llms.MultiLLMPromptExecutor
import ai.koog.prompt.llm.LLMProvider
import ai.koog.utils.io.use

@LLMDescription("Weather tools")
class WeatherTools : ToolSet {
    @Tool
    @LLMDescription("Returns the current weather for a city")
    fun getWeather(@LLMDescription("City name") city: String): String = "Sunny, 21 C in $city"
}

suspend fun main() {
    val telemetry = FutureAgiTelemetry(FutureAgiTelemetry.Config.fromEnv())
    val openAI = OpenAILLMClient(
        apiKey = System.getenv("OPENAI_API_KEY"),
        settings = OpenAIClientSettings(baseUrl = System.getenv("OPENAI_BASE_URL") ?: "https://api.openai.com"),
    )
    try {
        AIAgent(
            id = "weather-agent", // readable span names; Koog uses a random UUID otherwise
            promptExecutor = MultiLLMPromptExecutor(LLMProvider.OpenAI to openAI),
            llmModel = OpenAIModels.Chat.GPT5_6Luna,
            systemPrompt = "You are a weather assistant. Always call getWeather before answering.",
            toolRegistry = ToolRegistry { tools(WeatherTools()) },
        ) {
            install(OpenTelemetry) { telemetry.configure(this) }
        }.use { agent ->
            // The second argument becomes gen_ai.conversation.id and the Future AGI session id.
            println(agent.run("What is the weather in Paris?", "user-42-chat-7"))
        }
    } finally {
        telemetry.shutdown() // flush, or the last spans of the run are lost
    }
}
