import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { StrandsSpanExporter, StrandsSpanProcessor } from '@traceai/strands/native';
import { Agent, FunctionTool } from '@strands-agents/sdk';
import { OpenAIModel } from '@strands-agents/sdk/models/openai';

const base = (process.env.FI_TRACES_URL || process.env.FI_BASE_URL || 'https://api.futureagi.com').replace(/\/+$/, '');
const exporter = new OTLPTraceExporter({
  url: process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT || `${base}/tracer/v1/traces`,
  headers: { 'x-api-key': process.env.FI_API_KEY, 'x-secret-key': process.env.FI_SECRET_KEY },
});
const provider = new NodeTracerProvider({
  resource: resourceFromAttributes({ project_name: 'ridgeline-framework-tracing', project_type: 'observe' }),
  spanProcessors: [new StrandsSpanProcessor(new BatchSpanProcessor(new StrandsSpanExporter(exporter)))],
});
provider.register();
try {
  const agent = new Agent({
    name: 'care-desk', printer: false,
    model: new OpenAIModel({ api: 'chat', modelId: process.env.OPENAI_MODEL }),
    tools: [new FunctionTool({ name: 'lookup_care', description: 'Look up rain shell care instructions.',
      inputSchema: { type: 'object', properties: {} }, callback: async () => 'Air dry away from direct heat.' })],
  });
  const result = await agent.invoke('Use lookup_care to tell me how to dry my rain shell.');
  console.log(result.lastMessage);
} finally {
  await provider.shutdown();
}
