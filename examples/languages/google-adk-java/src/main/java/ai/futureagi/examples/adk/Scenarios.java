package ai.futureagi.examples.adk;

import com.google.adk.agents.LlmAgent;
import com.google.adk.events.Event;
import com.google.adk.models.langchain4j.LangChain4j;
import com.google.adk.runner.InMemoryRunner;
import com.google.adk.sessions.Session;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;
import com.google.genai.types.Content;
import com.google.genai.types.Part;
import dev.langchain4j.model.openai.OpenAiChatModel;
import io.opentelemetry.api.baggage.Baggage;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import java.util.Map;

/**
 * The agent the example runs. Loading this class loads ADK, so {@code Main} only touches it AFTER
 * {@link FutureAgiTelemetry#register} has run.
 */
public final class Scenarios {

  private Scenarios() {}

  /** The tool the model is asked to call. */
  @Schema(name = "get_weather", description = "Current weather for a city")
  public static Map<String, Object> getWeather(
      @Schema(name = "city", description = "City name") String city) {
    return Map.of("city", city, "forecast", "sunny", "temp_c", 21);
  }

  /** Runs one agent turn and returns the final text. Model comes from OPENAI_* env vars. */
  public static String run(String modelName, String userId, String userText) {
    OpenAiChatModel chat =
        OpenAiChatModel.builder()
            .baseUrl(System.getenv().getOrDefault("OPENAI_BASE_URL", "https://api.openai.com/v1"))
            .apiKey(System.getenv().getOrDefault("OPENAI_API_KEY", "unset"))
            .modelName(modelName)
            .maxRetries(0)
            .build();
    LlmAgent agent =
        LlmAgent.builder()
            .name("weather_agent")
            .description("Answers weather questions")
            .model(LangChain4j.builder().chatModel(chat).modelName(modelName).build())
            .instruction("Use the get_weather tool, then answer in one short sentence.")
            .tools(FunctionTool.create(Scenarios.class, "getWeather"))
            .build();
    InMemoryRunner runner = new InMemoryRunner(agent);
    Session session = runner.sessionService().createSession(runner.appName(), userId).blockingGet();
    Content msg = Content.fromParts(Part.fromText(userText));
    StringBuilder out = new StringBuilder();
    // session.id / user.id: put the values YOU hold on the context; the processor copies them
    // onto every span started under it.
    Baggage baggage =
        Baggage.builder().put("session.id", session.id()).put("user.id", userId).build();
    try (Scope ignored = Context.current().with(baggage).makeCurrent()) {
      runner
          .runAsync(userId, session.id(), msg)
          .blockingForEach(
              (Event e) -> {
                if (e.finalResponse()) {
                  out.append(e.stringifyContent());
                }
              });
    }
    return out.toString();
  }
}
