package ai.futureagi.examples.adk;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.baggage.Baggage;
import io.opentelemetry.context.Context;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.ReadWriteSpan;
import io.opentelemetry.sdk.trace.ReadableSpan;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.SpanProcessor;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

/**
 * Registers one OpenTelemetry SDK as the process-wide global, pointed at Future AGI.
 *
 * <p>Google ADK Java has no API to hand it an OpenTelemetry instance. Its telemetry classes ask
 * {@link GlobalOpenTelemetry} for a tracer when they are first loaded. So {@link #register} has to
 * run before ANY ADK class is touched. Nothing in this file imports ADK, on purpose.
 */
public final class FutureAgiTelemetry {

  private FutureAgiTelemetry() {}

  /** Settings read from the environment. Never logged. */
  public record Config(String baseUrl, String apiKey, String secretKey, String projectName) {
    public static Config fromEnv() {
      return new Config(
          require("FI_BASE_URL"),
          require("FI_API_KEY"),
          require("FI_SECRET_KEY"),
          require("FI_PROJECT_NAME"));
    }

    /** {FI_BASE_URL}/tracer/v1/traces, with no trailing slash on the base. */
    public String tracesEndpoint() {
      String b = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
      return b + "/tracer/v1/traces";
    }
  }

  private static String require(String name) {
    String v = System.getenv(name);
    if (v == null || v.isBlank()) {
      throw new IllegalStateException("Set " + name);
    }
    return v;
  }

  /** Builds the SDK for {@code config}, registers it as the global, and returns it. */
  public static OpenTelemetrySdk register(Config config) {
    return register(
        config,
        OtlpHttpSpanExporter.builder()
            .setEndpoint(config.tracesEndpoint())
            .addHeader("X-Api-Key", config.apiKey())
            .addHeader("X-Secret-Key", config.secretKey())
            // Optional: Future AGI cloud and self-hosted v1.56.0+ also accept gzip. "none" is also the exporter default; stated so it stays.
            .setCompression("none")
            .setTimeout(Duration.ofSeconds(10))
            .build());
  }

  /** Same, with any exporter. The tests use this to capture spans in memory. */
  public static OpenTelemetrySdk register(Config config, SpanExporter exporter) {
    return register(config, exporter, captureContentFromEnv());
  }

  /**
   * Content is OFF unless {@code FI_ADK_CAPTURE_CONTENT=true}. This is this example's own switch,
   * applied on the way out. ADK's own switch is {@code ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS}.
   */
  public static boolean captureContentFromEnv() {
    return "true".equalsIgnoreCase(System.getenv("FI_ADK_CAPTURE_CONTENT"));
  }

  public static OpenTelemetrySdk register(
      Config config, SpanExporter exporter, boolean captureContent) {
    OpenTelemetrySdk sdk = build(config, exporter, captureContent);
    // Throws IllegalStateException if GlobalOpenTelemetry was already read, e.g. because an ADK
    // class loaded first. That is the failure to look for, not a no-op.
    GlobalOpenTelemetry.set(sdk);
    return sdk;
  }

  /** Builds the SDK without registering it. Tests use this; applications call {@code register}. */
  static OpenTelemetrySdk build(Config config, SpanExporter exporter, boolean captureContent) {
    Resource resource =
        Resource.getDefault()
            .merge(
                Resource.create(
                    Attributes.of(
                        AttributeKey.stringKey("project_name"), config.projectName(),
                        AttributeKey.stringKey("project_type"), "observe",
                        AttributeKey.stringKey("service.name"), config.projectName())));
    SdkTracerProvider tracerProvider =
        SdkTracerProvider.builder()
            .setResource(resource)
            .addSpanProcessor(new FiAttributesProcessor())
            .addSpanProcessor(
                BatchSpanProcessor.builder(new ContentFilterExporter(exporter, captureContent))
                    .build())
            .build();
    return OpenTelemetrySdk.builder().setTracerProvider(tracerProvider).build();
  }

  /** Flushes the batch and stops the exporter. Call it in a finally block before the JVM exits. */
  public static void shutdown(OpenTelemetrySdk sdk) {
    sdk.getSdkTracerProvider().shutdown().join(15, TimeUnit.SECONDS);
  }

  /**
   * Adds what ADK does not write: {@code fi.span.kind} from the ADK span name, and {@code
   * session.id} / {@code user.id} from OpenTelemetry Baggage the application put on the current
   * context. Only values the application supplied are written.
   */
  static final class FiAttributesProcessor implements SpanProcessor {
    @Override
    public void onStart(Context parent, ReadWriteSpan span) {
      String n = span.getName();
      String kind =
          n.startsWith("invoke_agent")
              ? "AGENT"
              : n.equals("call_llm")
                  ? "LLM"
                  : n.startsWith("execute_tool")
                      ? "TOOL"
                      : n.equals("invocation") || n.startsWith("invoke_workflow") ? "CHAIN" : null;
      if (kind != null) {
        span.setAttribute("fi.span.kind", kind);
      }
      Baggage b = Baggage.fromContext(parent);
      String session = b.getEntryValue("session.id");
      String user = b.getEntryValue("user.id");
      if (session != null) {
        span.setAttribute("session.id", session);
      }
      if (user != null) {
        span.setAttribute("user.id", user);
      }
    }

    @Override
    public boolean isStartRequired() {
      return true;
    }

    @Override
    public void onEnd(ReadableSpan span) {}

    @Override
    public boolean isEndRequired() {
      return false;
    }
  }
}
