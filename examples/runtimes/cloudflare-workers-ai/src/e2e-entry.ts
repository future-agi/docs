// STANDIN, local runs only. Wraps the real handler and replaces env.AI with a stub whose run() forwards to an
// OpenAI-compatible endpoint (CLIProxy) and returns the Workers AI text-generation shape {response, usage}.
// The Workers AI binding itself is never called and Cloudflare is never contacted.
import { handle, type AiBinding, type Env } from "./index";

interface E2eEnv extends Omit<Env, "AI"> {
  STANDIN_BASE_URL: string;
  STANDIN_API_KEY: string;
  STANDIN_MODEL: string;
}

function standinAi(env: E2eEnv): AiBinding {
  return {
    async run(_model, input) {
      const prompt = String(input.prompt ?? "");
      if (prompt.includes("__fail__")) throw new Error("standin AI failure: " + prompt);
      const r = await fetch(`${env.STANDIN_BASE_URL}/chat/completions`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${env.STANDIN_API_KEY}` },
        body: JSON.stringify({ model: env.STANDIN_MODEL, messages: [{ role: "user", content: prompt }], max_tokens: 60 }),
      });
      if (!r.ok) throw new Error(`standin upstream ${r.status}`);
      const j: any = await r.json();
      return {
        response: j.choices?.[0]?.message?.content ?? "",
        usage: j.usage
          ? { prompt_tokens: j.usage.prompt_tokens, completion_tokens: j.usage.completion_tokens, total_tokens: j.usage.total_tokens }
          : undefined,
      };
    },
  };
}

export default {
  fetch: (request: Request, env: E2eEnv, ctx: { waitUntil(p: Promise<unknown>): void }) =>
    handle(request, { ...env, AI: standinAi(env) }, ctx),
};
