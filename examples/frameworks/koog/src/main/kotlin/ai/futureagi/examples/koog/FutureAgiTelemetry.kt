package ai.futureagi.examples.koog

import ai.koog.agents.features.opentelemetry.feature.OpenTelemetryConfig
import io.opentelemetry.api.metrics.MeterProvider
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter
import io.opentelemetry.kotlin.ExperimentalApi
import io.opentelemetry.kotlin.OpenTelemetry
import io.opentelemetry.kotlin.createOpenTelemetry
import io.opentelemetry.kotlin.export.TelemetryCloseable
import io.opentelemetry.kotlin.tracing.export.batchSpanProcessor
import io.opentelemetry.kotlin.tracing.export.toOtelKotlinSpanExporter
import io.opentelemetry.sdk.trace.export.SpanExporter
import java.time.Duration

/**
 * Sends Koog's OpenTelemetry spans to Future AGI.
 *
 * Usage:
 * ```
 * val telemetry = FutureAgiTelemetry(FutureAgiTelemetry.Config.fromEnv())
 * val agent = AIAgent(...) { install(OpenTelemetry) { telemetry.configure(this) } }
 * try { agent.use { it.run("...") } } finally { telemetry.shutdown() }
 * ```
 *
 * Why the SDK is built here instead of with `addSpanExporter` + `setShutdownOnAgentClose(true)`:
 * in Koog 1.3.0 that shutdown path stops the exporter before the batch queue is drained, so the
 * spans that end last in a run (invoke_agent, create_agent, the final model call) are dropped.
 * Building the SDK and passing it with `setSdk` lets [shutdown] flush first.
 */
@OptIn(ExperimentalApi::class)
class FutureAgiTelemetry(
    val config: Config,
    delegate: SpanExporter = otlpExporter(config),
) {
    /** Connection and privacy settings. Secrets never appear in [toString]. */
    data class Config(
        val baseUrl: String,
        val apiKey: String,
        val secretKey: String,
        val projectName: String,
        val serviceName: String = "koog-agent",
        val serviceVersion: String = "1.0.0",
        /** Off by default. When true, prompts, responses, tool arguments/results and raw error text are exported. */
        val captureContent: Boolean = false,
    ) {
        init {
            require(apiKey.isNotBlank() && secretKey.isNotBlank()) { "Both FI_API_KEY and FI_SECRET_KEY are required." }
            require(projectName.isNotBlank()) { "FI_PROJECT_NAME is required." }
        }

        /** Future AGI's OTLP/HTTP traces endpoint. */
        val tracesEndpoint: String get() = baseUrl.trimEnd('/') + "/tracer/v1/traces"

        override fun toString(): String =
            "Config(endpoint=$tracesEndpoint, projectName=$projectName, serviceName=$serviceName, captureContent=$captureContent)"

        companion object {
            const val DEFAULT_BASE_URL = "https://api.futureagi.com"

            fun fromEnv(env: (String) -> String? = System::getenv): Config = Config(
                baseUrl = env("FI_BASE_URL")?.takeIf { it.isNotBlank() } ?: DEFAULT_BASE_URL,
                apiKey = env("FI_API_KEY").orEmpty(),
                secretKey = env("FI_SECRET_KEY").orEmpty(),
                projectName = env("FI_PROJECT_NAME").orEmpty(),
                serviceName = env("OTEL_SERVICE_NAME")?.takeIf { it.isNotBlank() } ?: "koog-agent",
                captureContent = env("FI_KOOG_CAPTURE_CONTENT").equals("true", ignoreCase = true),
            )
        }
    }

    /** The exporter wrapper. Exposed for tests. */
    val spanExporter: FutureAgiSpanExporter = FutureAgiSpanExporter(delegate, config.captureContent)

    /** The Kotlin OpenTelemetry SDK Koog will use. `project_name` must be a resource attribute. */
    val sdk: OpenTelemetry = createOpenTelemetry {
        tracerProvider {
            resource(
                mapOf(
                    "service.name" to config.serviceName,
                    "service.version" to config.serviceVersion,
                    "project_name" to config.projectName,
                    "project_type" to "observe",
                )
            )
            export { batchSpanProcessor(spanExporter.toOtelKotlinSpanExporter()) }
        }
    }

    /** Call inside `install(OpenTelemetry) { ... }`. */
    fun configure(otel: OpenTelemetryConfig) {
        otel.setServiceInfo(config.serviceName, config.serviceVersion)
        // Koog masks message content unless verbose is on. Verbose follows the content opt-in.
        otel.setVerbose(config.captureContent)
        otel.setSdk(sdk)
    }

    /** Flushes every pending span, then shuts the SDK down. Call once, after the agent is closed. */
    suspend fun shutdown() {
        val closeable = sdk as TelemetryCloseable
        closeable.forceFlush()
        closeable.shutdown()
    }

    companion object {
        /** OTLP/HTTP (protobuf) exporter with both Future AGI headers and no compression. */
        fun otlpExporter(config: Config): SpanExporter = OtlpHttpSpanExporter.builder()
            .setEndpoint(config.tracesEndpoint)
            .addHeader("X-Api-Key", config.apiKey)
            .addHeader("X-Secret-Key", config.secretKey)
            // Optional: Future AGI cloud and self-hosted v1.56.0+ also accept gzip.
            .setCompression("none")
            .setTimeout(Duration.ofSeconds(10))
            // The exporter's own self-metrics are not sent anywhere.
            .setMeterProvider(MeterProvider.noop())
            .build()
    }
}
