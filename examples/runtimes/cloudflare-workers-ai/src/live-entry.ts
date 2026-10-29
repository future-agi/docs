// Local REST-backed recipe. This is not a deployed Worker or a native AI-binding qualification.
import { handle, tracedRun, type AiBinding, type Env } from "./index";
import { createTracing, errorStatus } from "./tracing";

interface LiveEnv extends Omit<Env, "AI"> {
  CLOUDFLARE_ACCOUNT_ID: string;
  CLOUDFLARE_API_TOKEN: string;
}

function liveAi(env: LiveEnv): AiBinding {
  return {
    async run(model, input) {
      const r = await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.CLOUDFLARE_ACCOUNT_ID}/ai/run/${model}`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${env.CLOUDFLARE_API_TOKEN}` },
        body: JSON.stringify({ max_tokens: 40, ...input }),
      });
      const j: any = await r.json().catch(() => ({}));
      if (!r.ok || j.success === false) {
        const e = j.errors?.[0];
        throw new Error(`Workers AI ${r.status}${e ? ` ${e.code}: ${e.message}` : ""}`);
      }
      return j.result;
    },
  };
}

// /bad-model: the same wrapper with a model id that does not exist, to get a real vendor error.
async function badModel(env: LiveEnv): Promise<Response> {
  const tracing = createTracing(env);
  const root = tracing.startSpan("worker.fetch", { "fi.span.kind": "CHAIN", "url.path": "/bad-model" });
  try {
    await tracedRun(tracing, root, liveAi(env), "@cf/meta/not-a-real-model-9000", { prompt: "hi" });
    return Response.json({ ok: true });
  } catch (err) {
    errorStatus(root, err, tracing.captureContent);
    return Response.json({ error: "ai_failed" }, { status: 502 });
  } finally {
    root.end();
    if (!(await tracing.flush()) && tracing.enabled) {
      console.warn("Future AGI trace export failed or timed out");
    }
  }
}

export default {
  fetch: (request: Request, env: LiveEnv, ctx: { waitUntil(p: Promise<unknown>): void }) =>
    new URL(request.url).pathname === "/bad-model" ? badModel(env) : handle(request, { ...env, AI: liveAi(env) }, ctx),
};
