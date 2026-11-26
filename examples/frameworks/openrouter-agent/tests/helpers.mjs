import { OpenRouterCore } from '@openrouter/sdk/core.js';
import { callModel, tool } from '@openrouter/agent';
import { z } from 'zod';
import { InMemorySpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { buildTracerProvider, createTraceHooks } from '../futureagi-tracing.mjs';

export const MARKER = 'MKR-TEST-7f3a91';

export async function runAgent(server, { captureContent = false, toolFails = false, model = 'openai/gpt-4o-mini' } = {}) {
  const exporter = new InMemorySpanExporter();
  const provider = buildTracerProvider({ projectName: 'unit', spanProcessors: [new SimpleSpanProcessor(exporter)] });
  const client = new OpenRouterCore({ apiKey: 'sk-or-FAKE-KEY-0001', serverURL: server.url });
  const getWeather = tool({
    name: 'get_weather',
    description: 'Get the current weather for a city',
    inputSchema: z.object({ city: z.string() }),
    execute: async ({ city }) => {
      if (toolFails) throw new Error(`weather service down at /Users/someone/secret/path ${MARKER}`);
      return { city, condition: `sunny ${MARKER}` };
    },
  });
  let text;
  let error;
  try {
    const run = callModel(client, {
      model,
      input: `What is the weather in Lisbon? ${MARKER}`,
      tools: [getWeather],
      hooks: createTraceHooks(provider, { captureContent }),
    });
    text = await run.getText();
  } catch (e) {
    error = e;
  }
  await provider.forceFlush();
  return { spans: exporter.getFinishedSpans(), provider, text, error };
}

export const everything = (spans) =>
  JSON.stringify(
    spans.map((s) => ({
      name: s.name,
      attributes: s.attributes,
      events: s.events,
      status: s.status,
      resource: s.resource.attributes,
      scope: s.instrumentationScope,
    })),
  );
