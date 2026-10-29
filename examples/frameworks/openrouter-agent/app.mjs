// Demo app for the Future AGI OpenRouter Agent recipe.
//   node app.mjs agent        two model requests and one tool call (default)
//   node app.mjs tool-error   the tool throws; the model answers anyway
//   node app.mjs model-error  the model request is rejected; callModel throws
//
// OPENROUTER_API_KEY / OPENROUTER_BASE_URL / MODEL point it at OpenRouter (the defaults) or at any
// server that speaks the OpenRouter Responses API. MAX_OUTPUT_TOKENS (optional) caps each model request. MARKER is put in the prompt and in the tool
// result, so a privacy check can look for it.
import { OpenRouterCore } from '@openrouter/sdk/core.js';
import { callModel, tool } from '@openrouter/agent';
import { z } from 'zod';
import { buildTracerProvider, createTraceHooks } from './futureagi-tracing.mjs';

const scenario = process.argv[2] ?? 'agent';
const marker = process.env.MARKER ?? 'MARKER-NONE';
const model = scenario === 'model-error' ? 'no-such-model-for-this-demo' : process.env.MODEL ?? 'openai/gpt-4o-mini';

const client = new OpenRouterCore({
  apiKey: process.env.OPENROUTER_API_KEY,
  serverURL: process.env.OPENROUTER_BASE_URL, // undefined means https://openrouter.ai/api/v1
});

const getWeather = tool({
  name: 'get_weather',
  description: 'Get the current weather for a city',
  inputSchema: z.object({ city: z.string() }),
  execute: async ({ city }) => {
    if (scenario === 'tool-error') throw new Error(`weather service down for ${city} ${marker}`);
    return { city, temperature_c: 21, condition: `sunny ${marker}` };
  },
});

const provider = buildTracerProvider();
let result = { scenario, ok: false };
try {
  const run = callModel(client, {
    model,
    input: `What is the weather in Lisbon? Use the get_weather tool, then repeat the condition word for word. ${marker}`,
    tools: [getWeather],
    ...(process.env.MAX_OUTPUT_TOKENS ? { maxOutputTokens: Number(process.env.MAX_OUTPUT_TOKENS) } : {}), // optional cap, keeps a test run cheap
    hooks: createTraceHooks(provider), // one hooks object per callModel()
  });
  const text = await run.getText();
  const usage = await run.getUsage();
  result = { scenario, ok: true, text: text.slice(0, 200), modelCalls: usage.modelCalls, totalTokens: usage.totalTokens };
} catch (error) {
  result = { scenario, ok: false, error: error?.name ?? 'Error' };
} finally {
  // Flush before the process ends. A failed export must not crash the app.
  await provider.shutdown().catch((error) => console.error(`trace export failed: ${error?.message ?? error}`));
}
console.log(`RESULT ${JSON.stringify(result)}`);
