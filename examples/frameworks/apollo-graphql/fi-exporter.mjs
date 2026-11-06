// Wraps the OTLP exporter so the default export carries structure only.
//
// The stock OpenTelemetry GraphQL instrumentation records, besides names and timings:
//   - graphql.source        the query text (literals masked with allowValues:false, but still text)
//   - exception events      exception.message and exception.stacktrace of a thrown resolver error
// and the HTTP instrumentation records url.full, server.address, user_agent.original, ...
// None of that is needed to see a trace. This wrapper keeps an allowlist of attributes and, on
// error events, only exception.type. Set FI_APOLLO_CAPTURE_CONTENT=true to also keep the (masked)
// query text and the error message. The stack trace is never exported: it carries local file paths.

const KEEP_ATTRIBUTES = new Set([
  "graphql.operation.type",
  "graphql.operation.name",
  "graphql.field.name",
  "graphql.field.path",
  "graphql.field.type",
  "graphql.parent.name",
  "http.request.method",
  "http.response.status_code",
  "http.route",
]);
const CONTENT_ATTRIBUTES = new Set(["graphql.source"]);

// Only spans created by these two instrumentations are filtered. Your own spans are exported as you made them.
const FILTERED_SCOPES = new Set(["@opentelemetry/instrumentation-graphql", "@opentelemetry/instrumentation-http"]);

export function sanitizeSpan(span, { captureContent = false } = {}) {
  if (!FILTERED_SCOPES.has(span.instrumentationScope?.name)) return span;
  const attributes = {};
  for (const [key, value] of Object.entries(span.attributes ?? {})) {
    if (KEEP_ATTRIBUTES.has(key) || (captureContent && CONTENT_ATTRIBUTES.has(key))) attributes[key] = value;
  }
  const events = (span.events ?? []).map((event) => {
    const kept = {};
    const source = event.attributes ?? {};
    if (source["exception.type"] !== undefined) kept["exception.type"] = source["exception.type"];
    if (captureContent && source["exception.message"] !== undefined) kept["exception.message"] = source["exception.message"];
    return { ...event, attributes: kept };
  });
  // The status message of an errored span is raw error text too.
  const status = captureContent ? span.status : { code: span.status?.code };
  // Object.create keeps the span's prototype methods (spanContext(), ...) and overrides the data.
  return Object.create(span, {
    attributes: { value: attributes, enumerable: true },
    events: { value: events, enumerable: true },
    status: { value: status, enumerable: true },
  });
}

export class FiSanitizingExporter {
  constructor(inner, options = {}) {
    this.inner = inner;
    this.options = options;
  }
  export(spans, resultCallback) {
    this.inner.export(spans.map((span) => sanitizeSpan(span, this.options)), resultCallback);
  }
  shutdown() {
    return this.inner.shutdown();
  }
  forceFlush() {
    return this.inner.forceFlush?.() ?? Promise.resolve();
  }
}
