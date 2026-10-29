// The model is any AI SDK LanguageModel. This example uses an OpenAI-compatible
// endpoint so it runs without a Vercel AI Gateway account. Tracing does not
// depend on the model choice: a gateway string such as "openai/gpt-5.4-mini"
// produces the same spans.
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { defineAgent } from "eve";

const provider = createOpenAICompatible({
  name: "openai-compatible",
  baseURL: process.env.MODEL_BASE_URL ?? "https://api.openai.com/v1",
  apiKey: process.env.MODEL_API_KEY,
  includeUsage: true,
});

export default defineAgent({
  model: provider(process.env.MODEL_ID ?? "gpt-5.4-mini"),
  // Required for a model eve cannot look up in the AI Gateway catalog.
  modelContextWindowTokens: 128_000,
  // Keep the example to one custom tool, so it needs no sandbox.
  defaultTools: false,
});
