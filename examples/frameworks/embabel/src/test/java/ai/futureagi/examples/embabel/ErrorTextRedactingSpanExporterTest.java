package ai.futureagi.examples.embabel;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.EventData;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class ErrorTextRedactingSpanExporterTest {

    private static final String SECRET = "card 4242 declined for alice@example.com";

    /** Collects what the wrapped exporter would have sent. */
    static final class Capture implements SpanExporter {
        final List<SpanData> spans = new ArrayList<>();

        @Override
        public CompletableResultCode export(Collection<SpanData> batch) {
            spans.addAll(batch);
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

    private static SpanData export(boolean keepErrorText, java.util.function.Consumer<Span> body) {
        Capture capture = new Capture();
        try (SdkTracerProvider provider = SdkTracerProvider.builder()
                .addSpanProcessor(SimpleSpanProcessor.create(new ErrorTextRedactingSpanExporter(capture, keepErrorText)))
                .build()) {
            Span span = provider.get("test").spanBuilder("execute_tool currentWeather").startSpan();
            body.accept(span);
            span.end();
        }
        assertThat(capture.spans).hasSize(1);
        return capture.spans.get(0);
    }

    private static void failingTool(Span s) {
        s.setAttribute("embabel.tool.error.type", "IllegalStateException");
        s.setAttribute("embabel.tool.error.message", SECRET);
        s.setAttribute("embabel.tool.name", "currentWeather");
        s.recordException(new IllegalStateException(SECRET));
        s.setStatus(StatusCode.ERROR, SECRET);
    }

    @Test
    void dropsErrorTextButKeepsErrorStatusAndType() {
        SpanData span = export(false, ErrorTextRedactingSpanExporterTest::failingTool);

        assertThat(span.getStatus().getStatusCode()).isEqualTo(StatusCode.ERROR);
        assertThat(span.getStatus().getDescription()).isEmpty();
        assertThat(span.getAttributes().get(AttributeKey.stringKey("embabel.tool.error.type")))
                .isEqualTo("IllegalStateException");
        assertThat(span.getAttributes().get(AttributeKey.stringKey("embabel.tool.name"))).isEqualTo("currentWeather");
        assertThat(span.getAttributes().get(AttributeKey.stringKey("embabel.tool.error.message"))).isNull();

        EventData exception = span.getEvents().get(0);
        assertThat(exception.getName()).isEqualTo("exception");
        assertThat(exception.getAttributes().get(AttributeKey.stringKey("exception.type")))
                .isEqualTo(IllegalStateException.class.getName());
        assertThat(exception.getAttributes().get(AttributeKey.stringKey("exception.message"))).isNull();
        assertThat(exception.getAttributes().get(AttributeKey.stringKey("exception.stacktrace"))).isNull();

        assertThat(span.toString()).doesNotContain("4242").doesNotContain("alice@example.com");
    }

    @Test
    void contentOptInKeepsErrorTextButStillDropsTheStackTrace() {
        SpanData span = export(true, ErrorTextRedactingSpanExporterTest::failingTool);
        assertThat(span.getStatus().getDescription()).isEqualTo(SECRET);
        assertThat(span.getAttributes().get(AttributeKey.stringKey("embabel.tool.error.message"))).isEqualTo(SECRET);
        EventData exception = span.getEvents().get(0);
        assertThat(exception.getAttributes().get(AttributeKey.stringKey("exception.message"))).isEqualTo(SECRET);
        assertThat(exception.getAttributes().get(AttributeKey.stringKey("exception.stacktrace"))).isNull();
    }

    @Test
    void leavesSpansWithoutErrorTextUntouched() {
        SpanData span = export(false, s -> s.setAttribute("gen_ai.operation.name", "execute_tool"));
        assertThat(span.getAttributes().get(AttributeKey.stringKey("gen_ai.operation.name"))).isEqualTo("execute_tool");
        assertThat(span.getStatus().getStatusCode()).isEqualTo(StatusCode.UNSET);
    }
}
