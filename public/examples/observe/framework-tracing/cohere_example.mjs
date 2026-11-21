import * as Cohere from 'cohere-ai';
import { register, ProjectType } from '@traceai/fi-core';
import { CohereInstrumentation } from '@traceai/cohere';

const provider = register({ projectName: 'ridgeline-framework-tracing', projectType: ProjectType.OBSERVE, verbose: false });
const tracing = new CohereInstrumentation({ traceConfig: { hideInputs: true, hideOutputs: true, hideEmbeddingVectors: true } });
tracing.setTracerProvider(provider);
tracing.manuallyInstrument(Cohere);
try {
  const client = new Cohere.CohereClientV2({ token: process.env.COHERE_API_KEY, baseUrl: process.env.CO_API_URL });
  const stream = await client.chatStream({ model: process.env.COHERE_MODEL,
    messages: [{ role: 'user', content: 'Give one care tip for a Ridgeline rain shell.' }] });
  for await (const event of stream) {
    if (event.type === 'content-delta') process.stdout.write(event.delta.message.content.text ?? '');
  }
  await client.embed({ model: 'embed-english-v3.0', texts: ['Air dry your Ridgeline shell.'],
    inputType: 'search_document', embeddingTypes: ['int8'] });
} finally {
  tracing.disable();
  await provider.shutdown();
}
