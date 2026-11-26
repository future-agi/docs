import ai.traceai.FITracer;
import ai.traceai.elasticsearch.TracedElasticsearchClient;
import co.elastic.clients.elasticsearch.ElasticsearchAsyncClient;
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.ElasticsearchException;
import co.elastic.clients.json.jackson.JacksonJsonpMapper;
import co.elastic.clients.transport.instrumentation.OpenTelemetryForElasticsearch;
import co.elastic.clients.transport.rest_client.RestClientTransport;
import com.sun.net.httpserver.HttpServer;
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.proto.collector.trace.v1.ExportTraceServiceRequest;
import io.opentelemetry.proto.common.v1.KeyValue;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import org.apache.http.HttpHost;
import org.elasticsearch.client.RestClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.ByteArrayInputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.zip.GZIPInputStream;

import static org.junit.jupiter.api.Assertions.*;

class NativeElasticsearchTest {
    private static final String RESPONSE = """
        {"took":1,"timed_out":false,"_shards":{"total":1,"successful":1,"skipped":0,"failed":0},
         "hits":{"total":{"value":1,"relation":"eq"},"max_score":0.9,
                 "hits":[{"_index":"documents","_id":"1","_score":0.9,
                          "_source":{"text":"synthetic-response-content"}}]}}
        """;
    private HttpServer server;
    private String url;
    private InMemorySpanExporter memory;
    private OpenTelemetrySdk sdk;
    private final AtomicInteger searches = new AtomicInteger();
    private final BlockingQueue<WireExport> exports = new LinkedBlockingQueue<>();
    private volatile String searchBody;
    private volatile String authorization;
    private volatile boolean error;

    record WireExport(String contentType, String encoding, String apiKey, String secretKey,
                      ExportTraceServiceRequest request) {}

    @BeforeEach
    void start() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/documents/_search", exchange -> {
            searches.incrementAndGet();
            authorization = exchange.getRequestHeaders().getFirst("Authorization");
            searchBody = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            byte[] body = (error
                ? "{\"error\":{\"type\":\"index_not_found_exception\",\"reason\":\"synthetic missing index\"},\"status\":404}"
                : RESPONSE).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.getResponseHeaders().add("X-Elastic-Product", "Elasticsearch");
            exchange.sendResponseHeaders(error ? 404 : 200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.createContext("/tracer/v1/traces", exchange -> {
            var headers = exchange.getRequestHeaders();
            byte[] body = exchange.getRequestBody().readAllBytes();
            String encoding = headers.getFirst("Content-Encoding");
            if ("gzip".equals(encoding)) {
                try (var gzip = new GZIPInputStream(new ByteArrayInputStream(body))) {
                    body = gzip.readAllBytes();
                }
            }
            exports.add(new WireExport(headers.getFirst("Content-Type"), encoding,
                headers.getFirst("X-Api-Key"), headers.getFirst("X-Secret-Key"),
                ExportTraceServiceRequest.parseFrom(body)));
            exchange.getResponseHeaders().add("Content-Type", "application/x-protobuf");
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
        });
        server.start();
        url = "http://127.0.0.1:" + server.getAddress().getPort();
        memory = InMemorySpanExporter.create();
        sdk = OpenTelemetrySdk.builder().setTracerProvider(SdkTracerProvider.builder()
            .addSpanProcessor(SimpleSpanProcessor.create(memory)).build()).build();
    }

    @AfterEach
    void stop() {
        sdk.close();
        server.stop(0);
        GlobalOpenTelemetry.resetForTest();
    }

    private RestClientTransport transport() {
        return new RestClientTransport(RestClient.builder(HttpHost.create(url)).build(),
            new JacksonJsonpMapper(), null, new OpenTelemetryForElasticsearch(sdk, false));
    }

    private static String attribute(SpanData span, String key) {
        return span.getAttributes().get(AttributeKey.stringKey(key));
    }

    private SpanData assertNativeSpan() throws InterruptedException {
        assertEquals(1, searches.get());
        // A completed async response can wake its caller before the native
        // instrumentation's completion callback has finished exporting the span.
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        var spans = memory.getFinishedSpanItems();
        while (spans.isEmpty() && System.nanoTime() < deadline) {
            TimeUnit.MILLISECONDS.sleep(5);
            spans = memory.getFinishedSpanItems();
        }
        assertEquals(1, spans.size(), "native-only setup must finish exactly one database span");
        var span = spans.get(0);
        assertEquals("search", span.getName());
        assertEquals(SpanKind.CLIENT, span.getKind());
        assertEquals("elasticsearch-api", span.getInstrumentationScopeInfo().getName());
        assertTrue("elasticsearch".equals(attribute(span, "db.system.name"))
            || "elasticsearch".equals(attribute(span, "db.system")));
        assertTrue("search".equals(attribute(span, "db.operation.name"))
            || "search".equals(attribute(span, "db.operation")));
        assertNull(attribute(span, "fi.span.kind"));
        assertNull(attribute(span, "db.statement"));
        assertNull(attribute(span, "db.query.text"));
        assertFalse(span.getAttributes().toString().contains("synthetic-query-content"));
        assertFalse(span.getAttributes().toString().contains("synthetic-response-content"));
        return span;
    }

    @Test
    void explicitSdkTracesRealSynchronousClientWithoutWrapper() throws Exception {
        try (var transport = transport()) {
            var response = new ElasticsearchClient(transport).search(s -> s.index("documents")
                .query(q -> q.match(m -> m.field("text").query("synthetic-query-content"))), Map.class);
            assertEquals(1, response.hits().hits().size());
            assertTrue(searchBody.contains("synthetic-query-content"));
        }
        assertNativeSpan();
    }

    @Test
    void explicitSdkTracesRealAsynchronousClientWithoutWrapper() throws Exception {
        try (var transport = transport()) {
            var response = new ElasticsearchAsyncClient(transport).search(s -> s.index("documents")
                .query(q -> q.match(m -> m.field("text").query("synthetic-query-content"))), Map.class)
                .get(10, TimeUnit.SECONDS);
            assertEquals(1, response.hits().hits().size());
        }
        assertNativeSpan();
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void nativeSearchPreservesApplicationParent(boolean asynchronous) throws Exception {
        var parent = sdk.getTracer("application").spanBuilder("retrieve-documents").startSpan();
        try (var scope = parent.makeCurrent(); var transport = transport()) {
            if (asynchronous) {
                new ElasticsearchAsyncClient(transport).search(s -> s.index("documents"), Map.class)
                    .get(10, TimeUnit.SECONDS);
            } else {
                new ElasticsearchClient(transport).search(s -> s.index("documents"), Map.class);
            }
            var child = assertNativeSpan();
            assertEquals(parent.getSpanContext().getSpanId(), child.getParentSpanId());
            assertEquals(parent.getSpanContext().getTraceId(), child.getTraceId());
        } finally {
            parent.end();
        }
        assertEquals(2, memory.getFinishedSpanItems().size());
    }

    @Test
    void nativeAsyncErrorsPreserveFailureAndFinishOneSpan() throws Exception {
        error = true;
        try (var transport = transport()) {
            var failure = assertThrows(java.util.concurrent.ExecutionException.class,
                () -> new ElasticsearchAsyncClient(transport).search(s -> s.index("documents"), Map.class)
                    .get(10, TimeUnit.SECONDS));
            assertInstanceOf(ElasticsearchException.class, failure.getCause());
        }
        assertEquals(StatusCode.ERROR, assertNativeSpan().getStatus().getStatusCode());
    }

    @Test
    void defaultTransportUsesSdkRegisteredBeforeConstruction() throws Exception {
        GlobalOpenTelemetry.set(sdk);
        try (var transport = new RestClientTransport(RestClient.builder(HttpHost.create(url)).build(),
                new JacksonJsonpMapper())) {
            new ElasticsearchClient(transport).search(s -> s.index("documents"), Map.class);
        }
        assertNativeSpan();
    }

    @Test
    void nativeErrorsPreserveClientFailureAndFinishOneSpan() throws Exception {
        error = true;
        try (var transport = transport()) {
            assertThrows(ElasticsearchException.class,
                () -> new ElasticsearchClient(transport).search(s -> s.index("documents"), Map.class));
        }
        var span = assertNativeSpan();
        assertEquals(StatusCode.ERROR, span.getStatus().getStatusCode());
        assertFalse(span.getEvents().isEmpty(), "native errors may include details, as documented");
    }

    @Test
    void publishedOptionalWrapperCompatibilityBoundaryMatchesGuide() throws Exception {
        try (var transport = transport()) {
            var client = new ElasticsearchClient(transport);
            var traced = new TracedElasticsearchClient(client, new FITracer(sdk.getTracer("elasticsearch-retrieval")));
            if (!"8.12.0".equals(System.getProperty("elasticsearch.version"))) {
                // The released wrapper supplies an 8.x KnnQuery builder lambda to 9.x KnnSearch.
                var failure = assertThrows(ClassCastException.class,
                    () -> traced.knnSearch("documents", new float[]{0.1f, 0.2f, 0.3f}, 5, 100, "embedding"));
                assertTrue(failure.getMessage().contains("KnnSearch$Builder")
                    && failure.getMessage().contains("KnnQuery$Builder"));
                assertEquals(0, searches.get(), "9.x users must use the native path instead");
                return;
            }
            var response = traced.knnSearch("documents", new float[]{0.1f, 0.2f, 0.3f}, 5, 100, "embedding");
            assertEquals(1, response.hits().hits().size());
            assertSame(client, traced.unwrap());
        }
        assertEquals(1, searches.get());
        var spans = memory.getFinishedSpanItems();
        assertEquals(2, spans.size());
        var child = spans.stream().filter(s -> s.getKind() == SpanKind.CLIENT).findFirst().orElseThrow();
        var parent = spans.stream().filter(s -> "RETRIEVER".equals(attribute(s, "fi.span.kind")))
            .findFirst().orElseThrow();
        assertEquals(parent.getSpanId(), child.getParentSpanId());
        assertEquals(parent.getTraceId(), child.getTraceId());
        assertEquals(5L, parent.getAttributes().get(AttributeKey.longKey("retriever.top_k")));
        assertEquals(3L, parent.getAttributes().get(AttributeKey.longKey("embedding.dimensions")));
        assertEquals(1L, parent.getAttributes().get(AttributeKey.longKey("db.vector.results.count")));
        assertEquals(0.9, parent.getAttributes().get(AttributeKey.doubleKey("elasticsearch.top_score")));
    }

    @ParameterizedTest
    @ValueSource(strings = {"none", "gzip"})
    void nativeSpansExportAsProtobufWithPlainAndGzipTransport(String compression) throws Exception {
        var exporter = OtlpHttpSpanExporter.builder().setEndpoint(url + "/tracer/v1/traces")
            .setCompression(compression).build();
        try (var exportingSdk = OpenTelemetrySdk.builder().setTracerProvider(SdkTracerProvider.builder()
                .addSpanProcessor(SimpleSpanProcessor.create(exporter)).build()).build();
             var transport = new RestClientTransport(RestClient.builder(HttpHost.create(url)).build(),
                new JacksonJsonpMapper(), null, new OpenTelemetryForElasticsearch(exportingSdk, false))) {
            new ElasticsearchClient(transport).search(s -> s.index("documents")
                .query(q -> q.match(m -> m.field("text").query("synthetic-query-content"))), Map.class);
        }
        var exported = exports.poll(10, TimeUnit.SECONDS);
        assertNotNull(exported);
        assertEquals("application/x-protobuf", exported.contentType());
        assertEquals("gzip".equals(compression) ? "gzip" : null, exported.encoding());
        var resource = exported.request().getResourceSpans(0);
        assertEquals(1, resource.getScopeSpans(0).getSpansCount());
        var span = resource.getScopeSpans(0).getSpans(0);
        assertEquals("search", span.getName());
        assertEquals(io.opentelemetry.proto.trace.v1.Span.SpanKind.SPAN_KIND_CLIENT, span.getKind());
        assertFalse(exported.request().toString().contains("synthetic-query-content"));
        assertFalse(exported.request().toString().contains("synthetic-response-content"));
    }

    static List<String> documentedExamples() {
        return "8.12.0".equals(System.getProperty("elasticsearch.version"))
            ? List.of("NativeElasticsearchExample", "AsyncElasticsearchExample", "KnnElasticsearchExample", "OptionalElasticsearchExample")
            : List.of("NativeElasticsearchExample", "AsyncElasticsearchExample", "KnnElasticsearchExample");
    }

    @ParameterizedTest
    @org.junit.jupiter.params.provider.MethodSource("documentedExamples")
    void exactDocumentedExamplesExportHeadersResourcesAndExpectedSpans(String mainClass) throws Exception {
        boolean optional = mainClass.startsWith("Optional");
        var consumer = Path.of("target", "native-consumer", "target");
        // The native examples run from a packaged JAR with only the page's dependencies.
        String classpath = optional ? System.getProperty("java.class.path")
            : consumer.resolve("native-consumer-1.0.0-SNAPSHOT.jar").toAbsolutePath()
                + java.io.File.pathSeparator + java.nio.file.Files.readString(consumer.resolve("classpath.txt")).trim();
        var process = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
            "-Djava.net.preferIPv4Stack=true", "-cp", classpath, mainClass);
        // No inherited credentials or external endpoints, including from the developer's shell.
        process.environment().clear();
        process.environment().putAll(Map.of(
            "FI_API_KEY", "synthetic-fi-key", "FI_SECRET_KEY", "synthetic-fi-secret",
            "FI_PROJECT_NAME", "elasticsearch-native-test", "ELASTICSEARCH_URL", url,
            "ELASTICSEARCH_API_KEY", "synthetic-es-key", "ELASTICSEARCH_INDEX", "documents",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", url + "/tracer/v1/traces"));
        process.redirectErrorStream(true);
        var child = process.start();
        try {
            assertTrue(child.waitFor(30, TimeUnit.SECONDS), "documented process timed out");
            String output = new String(child.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            assertEquals(0, child.exitValue(), output);
            assertTrue(output.contains("Matches returned: 1"), output);
        } finally {
            child.destroyForcibly();
        }
        assertEquals("ApiKey synthetic-es-key", authorization);
        var exported = exports.poll(10, TimeUnit.SECONDS);
        assertNotNull(exported, "SDK close must drain the documented batch exporter");
        assertEquals("synthetic-fi-key", exported.apiKey());
        assertEquals("synthetic-fi-secret", exported.secretKey());
        assertEquals("application/x-protobuf", exported.contentType());
        var resource = exported.request().getResourceSpans(0);
        assertEquals("elasticsearch-native-test", stringValue(resource.getResource().getAttributesList(), "project_name"));
        assertEquals("observe", stringValue(resource.getResource().getAttributesList(), "project_type"));
        assertEquals("elasticsearch-search", stringValue(resource.getResource().getAttributesList(), "service.name"));
        var scope = resource.getScopeSpansList().stream()
            .filter(s -> s.getScope().getName().equals("elasticsearch-api")).findFirst().orElseThrow();
        assertEquals(1, scope.getSpansCount());
        assertEquals("search", scope.getSpans(0).getName());
        int spanCount = exported.request().getResourceSpansList().stream()
            .flatMap(r -> r.getScopeSpansList().stream()).mapToInt(s -> s.getSpansCount()).sum();
        assertEquals(optional ? 2 : 1, spanCount);
        assertFalse(exported.request().toString().contains("synthetic-es-key"));
        assertFalse(exported.request().toString().contains("synthetic-fi-secret"));
        assertFalse(exported.request().toString().contains("observability"));
        assertFalse(exported.request().toString().contains("synthetic-response-content"));
        assertEquals(1, searches.get());
        assertTrue(exports.isEmpty(), "one pipeline must not export the same operation twice");
        var payloads = Path.of("target", "wire", System.getProperty("elasticsearch.version"));
        java.nio.file.Files.createDirectories(payloads);
        java.nio.file.Files.write(payloads.resolve(mainClass + ".pb"), exported.request().toByteArray());
    }

    private static String stringValue(List<KeyValue> attributes, String name) {
        return attributes.stream().filter(a -> a.getKey().equals(name)).findFirst().orElseThrow()
            .getValue().getStringValue();
    }
}
