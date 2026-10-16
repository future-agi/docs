package ai.futureagi.examples.adk;

import io.opentelemetry.sdk.OpenTelemetrySdk;

/**
 * Usage: Main happy|error|late [marker]
 *
 * <p>Order matters. Step 1 registers the global OpenTelemetry. Only then does step 2 touch ADK.
 */
public final class Main {

  public static void main(String[] args) throws Exception {
    String scenario = args.length > 0 ? args[0] : "happy";
    String marker = args.length > 1 ? args[1] : "What is the weather in Paris?";
    String model = System.getenv().getOrDefault("OPENAI_MODEL", "gpt-6-luna");
    FutureAgiTelemetry.Config cfg = FutureAgiTelemetry.Config.fromEnv();

    if (scenario.equals("late")) {
      // Negative control: load an ADK telemetry class FIRST, then try to register.
      Class.forName("com.google.adk.telemetry.Tracing");
      try {
        FutureAgiTelemetry.register(cfg);
        System.out.println("late: registration unexpectedly succeeded");
      } catch (IllegalStateException e) {
        System.out.println("late: register failed as documented: " + e.getMessage());
      }
      System.out.println("late: reply=" + Scenarios.run(model, "user-late", marker));
      return;
    }

    OpenTelemetrySdk sdk = FutureAgiTelemetry.register(cfg); // 1. before any ADK class loads
    try {
      String useModel = scenario.equals("error") ? "model-that-does-not-exist" : model;
      try {
        System.out.println(scenario + ": reply=" + Scenarios.run(useModel, "user-42", marker)); // 2.
      } catch (RuntimeException e) {
        System.out.println(scenario + ": run failed (" + e.getClass().getSimpleName() + ")");
      }
    } finally {
      FutureAgiTelemetry.shutdown(sdk); // 3. flush before exit
    }
  }
}
