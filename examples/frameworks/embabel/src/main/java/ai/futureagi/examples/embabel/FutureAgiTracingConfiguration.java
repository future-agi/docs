package ai.futureagi.examples.embabel;

import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.resources.ResourceBuilder;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.micrometer.tracing.opentelemetry.autoconfigure.SpanExporters;
import org.springframework.boot.opentelemetry.autoconfigure.OpenTelemetryProperties;
import org.springframework.boot.opentelemetry.autoconfigure.OpenTelemetryResourceAttributes;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

/**
 * The two beans an Embabel 1.5.3 app needs on top of application.yml to send traces to
 * Future AGI.
 */
@Configuration(proxyBeanMethods = false)
public class FutureAgiTracingConfiguration {

    /**
     * Embabel's observability starter registers its own {@code Resource} bean (service.name only),
     * which replaces Spring Boot's and so ignores {@code management.opentelemetry.resource-attributes}
     * and {@code OTEL_RESOURCE_ATTRIBUTES}. Future AGI needs the {@code project_name} resource
     * attribute, so this bean builds the resource the way Spring Boot does.
     */
    @Bean
    Resource futureAgiResource(Environment environment, OpenTelemetryProperties properties) {
        ResourceBuilder builder = Resource.builder();
        new OpenTelemetryResourceAttributes(environment, properties.getResourceAttributes()).applyTo(builder::put);
        return Resource.getDefault().merge(builder.build());
    }

    /**
     * Wraps every span exporter Spring Boot creates (here, the OTLP exporter). Error text follows
     * the same switch as message content, and stack traces are never exported.
     * {@code SpanExporters} is the Spring Boot 4 bean the batch span processor exports to;
     * declaring it replaces Boot's default list, so spans are still exported exactly once.
     */
    @Bean
    SpanExporters spanExporters(
            ObjectProvider<SpanExporter> exporters,
            // Same switch, same default (true) as Embabel's own content capture.
            @Value("${embabel.agent.platform.observability.capture-message-content:true}") boolean captureContent) {
        return SpanExporters.of(exporters.orderedStream()
                .map(exporter -> new ErrorTextRedactingSpanExporter(exporter, captureContent))
                .toList());
    }
}
