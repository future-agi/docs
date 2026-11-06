// Demo only, not part of the recipe: points the `proxy/<id>` model at any
// OpenAI-compatible endpoint (MODEL_BASE_URL, MODEL_API_KEY, MODEL_ID) so the
// example runs without a provider-specific key. With these unset, the agent
// uses Flue's built-in providers and their usual keys (for example
// ANTHROPIC_API_KEY). Tracing does not depend on the provider.
import { createProvider } from '@earendil-works/pi-ai';
import { openAICompletionsApi } from '@earendil-works/pi-ai/api/openai-completions.lazy';
import { setProvider } from '@flue/runtime';

export const MODEL = process.env.MODEL_BASE_URL
  ? `proxy/${process.env.MODEL_ID ?? 'gpt-5.6-luna'}`
  : (process.env.FLUE_MODEL ?? 'anthropic/claude-haiku-4-5');

if (process.env.MODEL_BASE_URL) {
  const id = process.env.MODEL_ID ?? 'gpt-5.6-luna';
  setProvider(
    createProvider({
      id: 'proxy',
      auth: {
        apiKey: {
          name: 'OpenAI-compatible endpoint',
          resolve: async () => ({ auth: { apiKey: process.env.MODEL_API_KEY ?? '' } }),
        },
      },
      models: [
        {
          id,
          name: id,
          api: 'openai-completions',
          provider: 'proxy',
          baseUrl: process.env.MODEL_BASE_URL,
          reasoning: false,
          input: ['text'],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 128000,
          maxTokens: 4096,
        },
      ],
      api: openAICompletionsApi(),
    }),
  );
}
