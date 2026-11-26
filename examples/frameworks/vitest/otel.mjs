import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';

for (const key of ['FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME']) {
  if (!process.env[key]) throw new Error(`Set ${key} before running Vitest`);
}

const sdk = new NodeSDK({
  resource: resourceFromAttributes({
    'service.name': 'vitest-tests',
    project_name: process.env.FI_PROJECT_NAME,
    project_type: 'observe',
  }),
  traceExporter: new OTLPTraceExporter({
    url: process.env.FI_OTLP_ENDPOINT ?? 'https://api.futureagi.com/tracer/v1/traces',
    headers: {
      'X-Api-Key': process.env.FI_API_KEY,
      'X-Secret-Key': process.env.FI_SECRET_KEY,
    },
  }),
});

sdk.start(); // Vitest imports this module; NodeSDK does not start itself.
export default sdk; // Vitest calls shutdown() on exit to flush short runs.
