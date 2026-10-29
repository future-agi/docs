// Imported FIRST by server.mjs, before @apollo/server. The GraphQL and HTTP instrumentations
// patch `graphql` and `http` when they are first loaded, so loading Apollo earlier leaves them
// unpatched and the trace has no GraphQL spans.
import { NodeSDK, tracing } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { SpanStatusCode } from "@opentelemetry/api";
import { GraphQLInstrumentation } from "@opentelemetry/instrumentation-graphql";
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http";
import { FiSanitizingExporter } from "./fi-exporter.mjs";

const baseUrl = (process.env.FI_BASE_URL ?? "https://api.futureagi.com").replace(/\/+$/, "");
const projectName = process.env.FI_PROJECT_NAME ?? "apollo-server-4";

const processor = new tracing.BatchSpanProcessor(
  new FiSanitizingExporter(
    new OTLPTraceExporter({
      url: `${baseUrl}/tracer/v1/traces`, // HTTP, not gRPC
      headers: {
        "X-Api-Key": process.env.FI_API_KEY ?? "",
        "X-Secret-Key": process.env.FI_SECRET_KEY ?? "",
      },
      compression: "none" /* the Future AGI collector rejects gzip bodies */,
    }),
    { captureContent: process.env.FI_APOLLO_CAPTURE_CONTENT === "true" },
  ),
);

export const sdk = new NodeSDK({
  // No resource detectors: the default host/process detectors would add the hostname, the OS
  // user name and the full command line (local paths) to every batch.
  resourceDetectors: [],
  resource: resourceFromAttributes({
    project_name: projectName, // a RESOURCE attribute; without it the batch is dropped
    project_type: "observe",
    "service.name": projectName,
  }),
  spanProcessors: [processor],
  // NodeSDK defaults to OTLP metric and log exporters (OTEL_METRICS_EXPORTER / OTEL_LOGS_EXPORTER
  // unset = otlp). The Future AGI endpoint takes traces only, and the defaults also delay shutdown
  // by several seconds. Traces only:
  metricReaders: [],
  logRecordProcessors: [],
  instrumentations: [
    new HttpInstrumentation(),
    // depth:1 bounds the field spans; allowValues:false keeps literals out of graphql.source.
    // ignoreTrivialResolveSpans is NOT used: it had no effect on Apollo Server 4.13.0 (see the page).
    new GraphQLInstrumentation({
      depth: 1,
      allowValues: false,
      // The stock instrumentation marks the failing resolve span ERROR but leaves the operation
      // span UNSET (observed on 4.13.0). This hook marks it ERROR when the result has errors.
      // It sets a status code only, no message.
      responseHook: (span, result) => {
        if (result?.errors?.length) span.setStatus({ code: SpanStatusCode.ERROR });
      },
    }),
  ],
});

sdk.start();

/** Export everything finished so far, without waiting for the batch interval. */
export const flushTelemetry = () => processor.forceFlush().catch(reportExportError);
/** Call on server shutdown so the last batch is exported. */
export const shutdownTelemetry = () => sdk.shutdown().catch(reportExportError);

// An unreachable or rejecting endpoint (401, 5xx, refused) rejects flush/shutdown. Telemetry must
// never take the server down, so log the error class and carry on.
function reportExportError(error) {
  console.error(`telemetry export failed: ${error?.name ?? "Error"}${error?.code ? ` (${error.code})` : ""}`);
}
