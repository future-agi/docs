import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';

// Configure this once per Node.js process, before constructing a Client or Worker.
const resource = resourceFromAttributes({
  'service.name': 'temporal-weather-agent',
  project_name: process.env.FI_PROJECT_NAME || 'temporal-weather-agent',
  project_type: 'observe',
});
if (!process.env.FI_API_KEY || !process.env.FI_SECRET_KEY) {
  throw new Error('Set FI_API_KEY and FI_SECRET_KEY before starting tracing');
}
const exporter = new OTLPTraceExporter({
  url: process.env.FI_TRACES_URL || 'https://api.futureagi.com/tracer/v1/traces',
  headers: {
    'X-Api-Key': process.env.FI_API_KEY,
    'X-Secret-Key': process.env.FI_SECRET_KEY,
  },
});
export const spanProcessor = new BatchSpanProcessor(exporter);
export const sdk = new NodeSDK({ resource, spanProcessors: [spanProcessor] });
export { resource };
