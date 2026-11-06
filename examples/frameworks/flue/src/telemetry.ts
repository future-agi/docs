// Sends Flue's OpenTelemetry spans to Future AGI. Import this module once, before
// any agent runs: from src/app.ts for a server, and from the agent module for
// `flue run` (which never loads app.ts).
import { createOpenTelemetryInstrumentation } from '@flue/opentelemetry';
import { instrument } from '@flue/runtime';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';

import { contentOption, exporterHeaders, resourceAttributes, tracesUrl } from './futureagi.ts';

export function installFutureAGITracing(env: NodeJS.ProcessEnv = process.env): (() => Promise<void>) | undefined {
  const headers = exporterHeaders(env);
  if (!headers) {
    console.warn('[futureagi] FI_API_KEY and FI_SECRET_KEY must both be set; Flue tracing is off.');
    return undefined;
  }

  // 1. The application owns the SDK: Flue's package never creates one.
  //    Batches spans and exports every 5 seconds (OTEL_BSP_* env vars tune it).
  const processor = new BatchSpanProcessor(new OTLPTraceExporter({ url: tracesUrl(env), headers })); // uncompressed OTLP/HTTP protobuf
  const sdk = new NodeSDK({
    resource: resourceFromAttributes(resourceAttributes(env)),
    // The default detectors add host.name, host.id, process.owner (the OS user
    // name), process.command_args and process.executable.path (absolute local
    // paths) to every export. Turn them off.
    autoDetectResources: false,
    spanProcessors: [processor],
    // Traces only. By default NodeSDK also starts OTLP metric and log exporters
    // that post to http://localhost:4318 (or OTEL_EXPORTER_OTLP_ENDPOINT). The
    // Future AGI collector takes traces only, and the failed exports would
    // delay shutdown by about ten seconds.
    metricReaders: [],
    logRecordProcessors: [],
  });
  sdk.start();

  // 2. Register Flue's instrumentation. Traces only: do not pass `meter` or
  //    `logger`, because the Future AGI collector accepts traces only.
  const instrumentation = createOpenTelemetryInstrumentation({ content: contentOption(env) });

  // 3. Flush.
  //    - `flue run` disposes module-scope instrumentation before it exits.
  //    - A standalone script that boots the runtime itself exits when its event
  //      loop drains: flush on `beforeExit`.
  //    - A built server (`node dist/server.mjs`) does not dispose instrumentation
  //      created in app.ts and calls process.exit() as soon as it has stopped, so
  //      an async flush on SIGTERM loses the race. Export each submission's spans
  //      as soon as it settles instead.
  const dispose = instrument({
    ...instrumentation,
    observe(event, ctx) {
      const result = instrumentation.observe(event, ctx);
      if (event.type === 'submission_settled') void processor.forceFlush().catch(() => {});
      return result;
    },
    async dispose() {
      instrumentation.dispose(); // ends spans that are still open
      await sdk.shutdown(); // flushes the batch processor
    },
  });
  process.once('beforeExit', () => void dispose());
  return dispose;
}

/** Call to flush and stop tracing yourself, for example at the end of a script. */
export const shutdownTracing: () => Promise<void> = installFutureAGITracing() ?? (async () => {});
