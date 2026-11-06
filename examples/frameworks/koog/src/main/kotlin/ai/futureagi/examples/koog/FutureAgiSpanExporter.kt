package ai.futureagi.examples.koog

import io.opentelemetry.api.common.AttributeKey
import io.opentelemetry.api.common.Attributes
import io.opentelemetry.api.trace.StatusCode
import io.opentelemetry.sdk.common.CompletableResultCode
import io.opentelemetry.sdk.trace.data.DelegatingSpanData
import io.opentelemetry.sdk.trace.data.EventData
import io.opentelemetry.sdk.trace.data.SpanData
import io.opentelemetry.sdk.trace.data.StatusData
import io.opentelemetry.sdk.trace.export.SpanExporter
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Wraps the OTLP exporter that sends Koog spans to Future AGI.
 *
 * It does three things, and nothing else:
 *
 * 1. Privacy. Unless [captureContent] is true, it keeps message content out of the export even if
 *    Koog's verbose mode was switched on elsewhere: the content attributes Koog masks by default are
 *    masked again, the raw error text in the span status is blanked (Koog does not mask it), and span
 *    events are dropped. The status code and `error.type` are kept. Stack traces are never exported:
 *    with content on, the `stackTrace` fields Koog serializes into node inputs/outputs are emptied and
 *    `exception.stacktrace` is removed from span events.
 * 2. Display. It adds `fi.span.kind` where Future AGI would otherwise show `unknown`
 *    (`invoke_agent` / `create_agent` become AGENT; Koog strategy, node and subgraph spans become CHAIN),
 *    and copies `gen_ai.conversation.id` to `session.id` so runs show up in Sessions.
 *    `chat` and `execute_tool` spans are left as Koog wrote them; Future AGI already maps those.
 * 3. Delivery. Koog 1.3.0 bridges Java exporters through opentelemetry-kotlin 0.3.0, which does not
 *    wait for the Java exporter's asynchronous result. This wrapper waits for each export to finish,
 *    and [shutdown] waits for in-flight exports, so a flush really means "sent".
 */
class FutureAgiSpanExporter(
    private val delegate: SpanExporter,
    private val captureContent: Boolean,
    private val exportTimeoutMillis: Long = 30_000,
) : SpanExporter {

    private val inFlight = AtomicInteger(0)
    private val isShutdown = AtomicBoolean(false)
    private val lock = Object()

    override fun export(spans: Collection<SpanData>): CompletableResultCode {
        if (isShutdown.get()) return CompletableResultCode.ofFailure()
        inFlight.incrementAndGet()
        try {
            val result = delegate.export(spans.map { transform(it, captureContent) })
            result.join(exportTimeoutMillis, TimeUnit.MILLISECONDS)
            return if (result.isSuccess) CompletableResultCode.ofSuccess() else CompletableResultCode.ofFailure()
        } finally {
            if (inFlight.decrementAndGet() == 0) synchronized(lock) { lock.notifyAll() }
        }
    }

    override fun flush(): CompletableResultCode = delegate.flush()

    override fun shutdown(): CompletableResultCode {
        if (!isShutdown.compareAndSet(false, true)) return CompletableResultCode.ofSuccess()
        val deadline = System.currentTimeMillis() + exportTimeoutMillis
        synchronized(lock) {
            while (inFlight.get() > 0 && System.currentTimeMillis() < deadline) {
                lock.wait(maxOf(1L, deadline - System.currentTimeMillis()))
            }
        }
        return delegate.shutdown()
    }

    companion object {
        /** The placeholder Koog itself writes for masked content. */
        const val HIDDEN = "HIDDEN:non-empty"

        /** Attributes Koog masks when verbose mode is off (Koog 1.3.0 `HiddenString` attributes). */
        val CONTENT_KEYS: Set<String> = setOf(
            "gen_ai.input.messages",
            "gen_ai.output.messages",
            "gen_ai.system_instructions",
            // Koog 1.3.0 writes system instructions under this key, not gen_ai.system_instructions.
            "system_instructions",
            "gen_ai.tool.definitions",
            "gen_ai.tool.call.arguments",
            "gen_ai.tool.call.result",
            "koog.node.input",
            "koog.node.output",
            "koog.subgraph.input",
            "koog.subgraph.output",
            "koog.moderation.result",
        )

        private val FI_SPAN_KIND = AttributeKey.stringKey("fi.span.kind")
        private val GEN_AI_SPAN_KIND = AttributeKey.stringKey("gen_ai.span.kind")
        private val OPERATION = AttributeKey.stringKey("gen_ai.operation.name")
        private val CONVERSATION_ID = AttributeKey.stringKey("gen_ai.conversation.id")
        private val SESSION_ID = AttributeKey.stringKey("session.id")
        private val KOOG_CHAIN_KEYS = listOf("koog.strategy.name", "koog.node.id", "koog.subgraph.id")
        private val EXCEPTION_STACKTRACE = AttributeKey.stringKey("exception.stacktrace")

        /**
         * A JSON `"stackTrace": "..."` field, as Koog writes it inside failed tool results. Unrolled and
         * possessive, so long traces do not overflow the regex engine's stack.
         */
        private val STACK_TRACE_FIELD = Regex(""""stackTrace"\s*:\s*"[^"\\]*+(?:\\.[^"\\]*+)*+"""")

        /** Empties every serialized `stackTrace` field in [text]. */
        internal fun stripStackTraces(text: String): String =
            STACK_TRACE_FIELD.replace(text, """"stackTrace":""""")

        /** Span kind Future AGI should show, or null when the collector already maps the span. */
        internal fun spanKindFor(attributes: Attributes): String? {
            if (attributes.get(FI_SPAN_KIND) != null || attributes.get(GEN_AI_SPAN_KIND) != null) return null
            return when (attributes.get(OPERATION)) {
                "invoke_agent", "create_agent" -> "AGENT"
                null -> if (KOOG_CHAIN_KEYS.any { attributes.get(AttributeKey.stringKey(it)) != null }) "CHAIN" else null
                else -> null
            }
        }

        internal fun transformAttributes(attributes: Attributes, captureContent: Boolean): Attributes {
            val builder = attributes.toBuilder()
            attributes.forEach { key, value ->
                if (key.key in CONTENT_KEYS) {
                    val text = value.toString()
                    val exported = when {
                        !captureContent -> if (text.isEmpty()) "" else HIDDEN
                        // If stripping ever fails, mask the value rather than lose the span or leak the trace.
                        "\"stackTrace\"" in text -> runCatching { stripStackTraces(text) }.getOrElse { HIDDEN }
                        else -> null
                    }
                    if (exported != null) {
                        builder.remove(key)
                        builder.put(AttributeKey.stringKey(key.key), exported)
                    }
                }
            }
            spanKindFor(attributes)?.let { builder.put(FI_SPAN_KIND, it) }
            val conversation = attributes.get(CONVERSATION_ID)
            if (conversation != null && attributes.get(SESSION_ID) == null) builder.put(SESSION_ID, conversation)
            return builder.build()
        }

        internal fun transform(span: SpanData, captureContent: Boolean): SpanData {
            val attributes = transformAttributes(span.attributes, captureContent)
            val status = if (!captureContent && span.status.statusCode == StatusCode.ERROR && span.status.description.isNotEmpty()) {
                StatusData.create(StatusCode.ERROR, "")
            } else {
                span.status
            }
            val events: List<EventData> = if (!captureContent) emptyList() else span.events.map { event ->
                if (event.attributes.get(EXCEPTION_STACKTRACE) == null) event
                else EventData.create(
                    event.epochNanos,
                    event.name,
                    event.attributes.toBuilder().remove(EXCEPTION_STACKTRACE).build(),
                    event.totalAttributeCount,
                )
            }
            return object : DelegatingSpanData(span) {
                override fun getAttributes(): Attributes = attributes
                override fun getTotalAttributeCount(): Int = maxOf(span.totalAttributeCount, attributes.size())
                override fun getStatus(): StatusData = status
                override fun getEvents(): List<EventData> = events
                override fun getTotalRecordedEvents(): Int = if (captureContent) span.totalRecordedEvents else 0
            }
        }
    }
}
