package ai.futureagi.examples.embabel;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.data.DelegatingSpanData;
import io.opentelemetry.sdk.trace.data.EventData;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.data.StatusData;
import io.opentelemetry.sdk.trace.export.SpanExporter;

import java.util.Collection;
import java.util.List;
import java.util.Set;

/**
 * Removes error text and stack traces from spans before they leave the process.
 *
 * <p>Embabel's {@code capture-message-content=false} removes prompts, responses and tool
 * arguments/results, but error text is still exported in three places: the span status
 * description, the {@code exception} event ({@code exception.message} and
 * {@code exception.stacktrace}) and the {@code embabel.llm.error.message} /
 * {@code embabel.tool.error.message} attributes. Error text often quotes the input that caused
 * the error. With {@code keepErrorText=false} this exporter keeps the ERROR status and the
 * exception type and drops the text. Stack traces are dropped in both modes.
 */
public final class ErrorTextRedactingSpanExporter implements SpanExporter {

    /** Attributes that carry raw error text. Exception type attributes are kept. */
    static final Set<String> ERROR_TEXT_KEYS = Set.of(
            "exception.message", "error.message", "embabel.llm.error.message", "embabel.tool.error.message");

    static final String STACKTRACE_KEY = "exception.stacktrace";

    private final SpanExporter delegate;
    private final boolean keepErrorText;

    public ErrorTextRedactingSpanExporter(SpanExporter delegate, boolean keepErrorText) {
        this.delegate = delegate;
        this.keepErrorText = keepErrorText;
    }

    @Override
    public CompletableResultCode export(Collection<SpanData> spans) {
        return delegate.export(spans.stream().map(this::redact).toList());
    }

    @Override
    public CompletableResultCode flush() {
        return delegate.flush();
    }

    @Override
    public CompletableResultCode shutdown() {
        return delegate.shutdown();
    }

    SpanData redact(SpanData span) {
        StatusData status = span.getStatus();
        boolean statusHasText = !keepErrorText && !status.getDescription().isEmpty();
        boolean attributesHaveText = hasDroppedKey(span.getAttributes());
        boolean eventsHaveText = span.getEvents().stream().anyMatch(e -> hasDroppedKey(e.getAttributes()));
        if (!statusHasText && !attributesHaveText && !eventsHaveText) {
            return span;
        }
        StatusData cleanStatus = statusHasText ? StatusData.create(status.getStatusCode(), "") : status;
        Attributes cleanAttributes = withoutDroppedKeys(span.getAttributes());
        List<EventData> cleanEvents = span.getEvents().stream()
                .map(e -> hasDroppedKey(e.getAttributes())
                        ? EventData.create(e.getEpochNanos(), e.getName(), withoutDroppedKeys(e.getAttributes()))
                        : e)
                .toList();
        return new DelegatingSpanData(span) {
            @Override
            public StatusData getStatus() {
                return cleanStatus;
            }

            @Override
            public Attributes getAttributes() {
                return cleanAttributes;
            }

            @Override
            public int getTotalAttributeCount() {
                return cleanAttributes.size();
            }

            @Override
            public List<EventData> getEvents() {
                return cleanEvents;
            }
        };
    }

    private boolean dropped(String key) {
        return STACKTRACE_KEY.equals(key) || (!keepErrorText && ERROR_TEXT_KEYS.contains(key));
    }

    private boolean hasDroppedKey(Attributes attributes) {
        return attributes.asMap().keySet().stream().anyMatch(k -> dropped(k.getKey()));
    }

    private Attributes withoutDroppedKeys(Attributes attributes) {
        AttributesBuilder builder = Attributes.builder();
        attributes.forEach((key, value) -> {
            if (!dropped(key.getKey())) {
                @SuppressWarnings("unchecked")
                AttributeKey<Object> k = (AttributeKey<Object>) key;
                builder.put(k, value);
            }
        });
        return builder.build();
    }
}
