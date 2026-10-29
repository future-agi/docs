// The Future AGI destination. eve combines it with any other destination file.
import { otelIntegration } from "eve/instrumentation/otel";

import { futureAGIExportPolicy, futureAGISpanProcessor } from "../lib/futureagi.ts";

export default otelIntegration({
  // Metadata only unless FI_CAPTURE_CONTENT=1. Applies to this destination
  // only: eve's local traces and Workflow retention are unchanged.
  exportPolicy: futureAGIExportPolicy(),
  // Drops eve's durable-workflow spans, then batches and exports the rest.
  spanProcessors: [futureAGISpanProcessor()],
});
