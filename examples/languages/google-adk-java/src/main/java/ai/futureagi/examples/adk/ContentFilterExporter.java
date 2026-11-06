package ai.futureagi.examples.adk;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.data.DelegatingSpanData;
import io.opentelemetry.sdk.trace.data.EventData;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.data.StatusData;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;

/**
 * Wraps the OTLP exporter. When content capture is off it removes the attributes where ADK puts
 * prompts, responses and tool arguments/results, the raw error text on the span status, and span
 * events (exception events carry the message and a stack trace). Span names, ids, timing, model,
 * token counts and status CODE are kept.
 */
final class ContentFilterExporter implements io.opentelemetry.sdk.trace.export.SpanExporter {

  /** Attribute keys ADK 1.12.0 uses for message content. */
  static final Set<String> CONTENT_KEYS =
      Set.of(
          "gcp.vertex.agent.llm_request",
          "gcp.vertex.agent.llm_response",
          "gcp.vertex.agent.tool_call_args",
          "gcp.vertex.agent.tool_response",
          "gcp.vertex.agent.data");

  private final io.opentelemetry.sdk.trace.export.SpanExporter delegate;
  private final boolean captureContent;

  ContentFilterExporter(
      io.opentelemetry.sdk.trace.export.SpanExporter delegate, boolean captureContent) {
    this.delegate = delegate;
    this.captureContent = captureContent;
  }

  @Override
  public CompletableResultCode export(Collection<SpanData> spans) {
    if (captureContent) {
      return delegate.export(spans);
    }
    List<SpanData> out = new ArrayList<>(spans.size());
    for (SpanData s : spans) {
      out.add(new Redacted(s));
    }
    return delegate.export(out);
  }

  @Override
  public CompletableResultCode flush() {
    return delegate.flush();
  }

  @Override
  public CompletableResultCode shutdown() {
    return delegate.shutdown();
  }

  private static final class Redacted extends DelegatingSpanData {
    Redacted(SpanData d) {
      super(d);
    }

    @Override
    public Attributes getAttributes() {
      AttributesBuilder b = Attributes.builder();
      super.getAttributes()
          .forEach(
              (k, v) -> {
                if (!CONTENT_KEYS.contains(k.getKey())) {
                  put(b, k, v);
                }
              });
      return b.build();
    }

    @SuppressWarnings("unchecked")
    private static <T> void put(AttributesBuilder b, AttributeKey<T> k, Object v) {
      b.put(k, (T) v);
    }

    @Override
    public StatusData getStatus() {
      return StatusData.create(super.getStatus().getStatusCode(), "");
    }

    @Override
    public List<EventData> getEvents() {
      return List.of();
    }

    @Override
    public int getTotalRecordedEvents() {
      return 0;
    }

    @Override
    public int getTotalAttributeCount() {
      return getAttributes().size();
    }
  }
}
