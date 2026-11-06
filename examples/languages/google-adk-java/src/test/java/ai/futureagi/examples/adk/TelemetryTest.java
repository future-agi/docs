package ai.futureagi.examples.adk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.baggage.Baggage;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.junit.jupiter.api.Test;

/** No network, no model, no ADK class loaded. */
class TelemetryTest {

  static final class Capture implements SpanExporter {
    final List<SpanData> spans = new ArrayList<>();

    @Override
    public synchronized CompletableResultCode export(Collection<SpanData> s) {
      spans.addAll(s);
      return CompletableResultCode.ofSuccess();
    }

    @Override
    public CompletableResultCode flush() {
      return CompletableResultCode.ofSuccess();
    }

    @Override
    public CompletableResultCode shutdown() {
      return CompletableResultCode.ofSuccess();
    }
  }

  static final FutureAgiTelemetry.Config CFG =
      new FutureAgiTelemetry.Config("http://localhost:14338/", "k", "s", "proj-x");

  static List<SpanData> emit(boolean capture) {
    Capture cap = new Capture();
    OpenTelemetrySdk sdk = FutureAgiTelemetry.build(CFG, cap, capture);
    Tracer t = sdk.getTracer("gcp.vertex.agent");
    Baggage bag = Baggage.builder().put("session.id", "sess-1").put("user.id", "user-1").build();
    try (Scope ignored = Context.current().with(bag).makeCurrent()) {
      Span agent = t.spanBuilder("invoke_agent a").startSpan();
      try (Scope s1 = agent.makeCurrent()) {
        Span llm = t.spanBuilder("call_llm").startSpan();
        llm.setAttribute("gcp.vertex.agent.llm_request", "SECRET-PROMPT");
        llm.setAttribute("gcp.vertex.agent.llm_response", "SECRET-REPLY");
        llm.setAttribute("gen_ai.request.model", "m1");
        llm.setAttribute("gen_ai.usage.input_tokens", 7L);
        llm.setStatus(StatusCode.ERROR, "raw error SECRET-ERR");
        llm.recordException(new RuntimeException("SECRET-EXC"));
        llm.end();
        Span tool = t.spanBuilder("execute_tool get_weather").startSpan();
        tool.setAttribute("gcp.vertex.agent.tool_call_args", "SECRET-ARGS");
        tool.setAttribute("gcp.vertex.agent.tool_response", "SECRET-RESULT");
        tool.end();
      }
      agent.end();
    }
    sdk.getSdkTracerProvider().shutdown().join(5, java.util.concurrent.TimeUnit.SECONDS);
    return cap.spans;
  }

  static String dump(List<SpanData> spans) {
    return spans.toString() + spans.stream().map(s -> s.getAttributes().toString()).toList();
  }

  @Test
  void contentOffRemovesPromptsToolIoErrorTextAndEvents() {
    List<SpanData> spans = emit(false);
    assertEquals(3, spans.size());
    String all = dump(spans);
    for (String secret :
        new String[] {"SECRET-PROMPT", "SECRET-REPLY", "SECRET-ARGS", "SECRET-RESULT", "SECRET-ERR"}) {
      assertFalse(all.contains(secret), secret);
    }
    for (SpanData s : spans) {
      assertTrue(s.getEvents().isEmpty());
    }
    SpanData llm = spans.stream().filter(s -> s.getName().equals("call_llm")).findFirst().get();
    assertEquals(StatusCode.ERROR, llm.getStatus().getStatusCode());
    assertEquals("", llm.getStatus().getDescription());
    assertEquals("m1", llm.getAttributes().get(AttributeKey.stringKey("gen_ai.request.model")));
    assertEquals(7L, llm.getAttributes().get(AttributeKey.longKey("gen_ai.usage.input_tokens")));
  }

  @Test
  void contentOnKeepsEverything() {
    String all = dump(emit(true));
    assertTrue(all.contains("SECRET-PROMPT"));
    assertTrue(all.contains("SECRET-ARGS"));
  }

  @Test
  void addsFiKindSessionUserAndResource() {
    List<SpanData> spans = emit(false);
    SpanData agent = spans.stream().filter(s -> s.getName().startsWith("invoke_agent")).findFirst().get();
    assertEquals("AGENT", agent.getAttributes().get(AttributeKey.stringKey("fi.span.kind")));
    for (SpanData s : spans) {
      assertEquals("sess-1", s.getAttributes().get(AttributeKey.stringKey("session.id")));
      assertEquals("user-1", s.getAttributes().get(AttributeKey.stringKey("user.id")));
      assertEquals("proj-x", s.getResource().getAttribute(AttributeKey.stringKey("project_name")));
      assertEquals("observe", s.getResource().getAttribute(AttributeKey.stringKey("project_type")));
    }
    assertEquals(
        "LLM",
        spans.stream().filter(s -> s.getName().equals("call_llm")).findFirst().get()
            .getAttributes().get(AttributeKey.stringKey("fi.span.kind")));
    assertEquals(
        "TOOL",
        spans.stream().filter(s -> s.getName().startsWith("execute_tool")).findFirst().get()
            .getAttributes().get(AttributeKey.stringKey("fi.span.kind")));
  }

  @Test
  void noBaggageMeansNoSessionOrUser() {
    Capture cap = new Capture();
    OpenTelemetrySdk sdk = FutureAgiTelemetry.build(CFG, cap, false);
    sdk.getTracer("x").spanBuilder("invoke_agent b").startSpan().end();
    sdk.getSdkTracerProvider().shutdown().join(5, java.util.concurrent.TimeUnit.SECONDS);
    assertNull(cap.spans.get(0).getAttributes().get(AttributeKey.stringKey("session.id")));
    assertNull(cap.spans.get(0).getAttributes().get(AttributeKey.stringKey("user.id")));
  }

  @Test
  void endpointHasNoDoubleSlash() {
    assertEquals("http://localhost:14338/tracer/v1/traces", CFG.tracesEndpoint());
  }

  /** The only test that touches the global. A second registration must fail loudly. */
  @Test
  void registerIsGlobalOnceAndSecondCallFails() {
    OpenTelemetrySdk sdk = FutureAgiTelemetry.register(CFG, new Capture(), false);
    assertThrows(
        IllegalStateException.class, () -> FutureAgiTelemetry.register(CFG, new Capture(), false));
    FutureAgiTelemetry.shutdown(sdk);
    assertTrue(GlobalOpenTelemetry.get() != null);
  }
}
