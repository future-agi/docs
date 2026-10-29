// Worker: one request = one trace.  worker.fetch (root)  ->  workers_ai.run (child, the env.AI.run call)
import { createTracing, errorStatus, type Tracing, type TracingEnv } from "./tracing";

export interface AiBinding {
  run(model: string, input: Record<string, unknown>): Promise<any>;
}
export interface Env extends TracingEnv {
  AI: AiBinding;
}
interface Ctx {
  waitUntil(p: Promise<unknown>): void;
}

export const MODEL = "@cf/meta/llama-3.1-8b-instruct";

/** Wrap one env.AI.run call in a child span. Same signature as the binding. */
export async function tracedRun(tracing: Tracing, root: import("@opentelemetry/api").Span, ai: AiBinding, model: string, input: Record<string, unknown>) {
  const span = tracing.startSpan(
    "workers_ai.run",
    {
      "fi.span.kind": "LLM",
      "gen_ai.provider.name": "cloudflare", // one provider key, not two
      "gen_ai.request.model": model, // the model id argument, as passed
      "llm.model_name": model,
    },
    root,
  );
  if (tracing.captureContent) span.setAttribute("input.value", JSON.stringify(input).slice(0, 4000));
  try {
    const result = await ai.run(model, input);
    const usage = result && typeof result === "object" ? result.usage : undefined;
    // Usage only when the binding returned it. Never write zeros.
    if (usage && Number.isFinite(usage.prompt_tokens)) {
      span.setAttribute("gen_ai.usage.input_tokens", usage.prompt_tokens);
      span.setAttribute("llm.token_count.prompt", usage.prompt_tokens);
    }
    if (usage && Number.isFinite(usage.completion_tokens)) {
      span.setAttribute("gen_ai.usage.output_tokens", usage.completion_tokens);
      span.setAttribute("llm.token_count.completion", usage.completion_tokens);
    }
    if (tracing.captureContent) span.setAttribute("output.value", JSON.stringify(result).slice(0, 4000));
    return result;
  } catch (err) {
    errorStatus(span, err, tracing.captureContent);
    throw err;
  } finally {
    span.end();
  }
}

export async function handle(request: Request, env: Env, _ctx: Ctx): Promise<Response> {
  const tracing = createTracing(env);
  const url = new URL(request.url);
  const root = tracing.startSpan("worker.fetch", {
    "fi.span.kind": "CHAIN",
    "http.request.method": request.method,
    "url.path": url.pathname, // path only: the query string can carry tokens
  });
  try {
    const body = (await request.json().catch(() => ({}))) as { prompt?: string };
    const result = await tracedRun(tracing, root, env.AI, MODEL, { prompt: body.prompt ?? "Say hello." });
    root.setAttribute("http.response.status_code", 200);
    return Response.json({ response: result?.response ?? null });
  } catch (err) {
    // This handler returns 502 when the AI call fails, so the request span is ERROR as well.
    // If you catch the error and return a fallback with 200, leave the root span OK.
    root.setAttribute("http.response.status_code", 502);
    errorStatus(root, err, tracing.captureContent);
    return Response.json({ error: "ai_failed" }, { status: 502 });
  } finally {
    root.end();
    // Await the export before the Response is returned, on success and on error.
    // This local REST recipe awaits export; it supplies no waitUntil lifecycle guarantee.
    if (!(await tracing.flush()) && tracing.enabled) {
      console.warn("Future AGI trace export failed or timed out");
    }
  }
}

export default {
  fetch: (request: Request, env: Env, ctx: Ctx) => handle(request, env, ctx),
};
