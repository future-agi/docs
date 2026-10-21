// In-isolate tracing for a Cloudflare Worker. Copy this file next to your handler.
//
//   one provider per request  ->  spans ended in the handler  ->  await flush() in `finally`
//
// Why per request: the keys are bindings on `env`, which only exists inside a handler, and an isolate
// can be torn down at any time, so nothing here relies on a timer or on state surviving the request.
//
// Configuration (Worker vars and secrets, never in the source):
//   FI_API_KEY, FI_SECRET_KEY   both required; if either is missing tracing is off and nothing is exported
//   FI_BASE_URL                 default https://api.futureagi.com  (self-hosted: your own URL)
//   FI_PROJECT_NAME             the Observe project (default "cloudflare-workers-ai")
//   FI_CAPTURE_CONTENT=true     opt in to prompt, response and error text on spans (off by default)
import { trace, context, SpanStatusCode, type Span } from "@opentelemetry/api";
import { JsonTraceSerializer } from "@opentelemetry/otlp-transformer";
import { resourceFromAttributes } from "@opentelemetry/resources";
import {
  BasicTracerProvider,
  BatchSpanProcessor,
  type ReadableSpan,
  type SpanExporter,
} from "@opentelemetry/sdk-trace-base";

export const FLUSH_BUDGET_MS = 2000; // proposed bound for one flush: a proposal, not a measurement

export interface TracingEnv {
  FI_API_KEY?: string;
  FI_SECRET_KEY?: string;
  FI_BASE_URL?: string;
  FI_PROJECT_NAME?: string;
  FI_CAPTURE_CONTENT?: string;
}

/** OTLP/HTTP (JSON) exporter built on fetch: workerd has no XMLHttpRequest and no node:http by default. */
export function fiExporter(env: TracingEnv, fetchImpl: typeof fetch = fetch): SpanExporter | undefined {
  if (!env.FI_API_KEY || !env.FI_SECRET_KEY) return undefined; // missing keys: do not export, do not throw
  const base = (env.FI_BASE_URL || "https://api.futureagi.com").replace(/\/+$/, "");
  return {
    export(spans: ReadableSpan[], done) {
      const body = JsonTraceSerializer.serializeRequest(spans);
      fetchImpl(`${base}/tracer/v1/traces`, {
        method: "POST",
        // Both keys are required. Do not set Content-Encoding: Future AGI rejects gzip bodies.
        headers: {
          "content-type": "application/json",
          "X-Api-Key": env.FI_API_KEY!,
          "X-Secret-Key": env.FI_SECRET_KEY!,
        },
        body: body as BodyInit,
        signal: AbortSignal.timeout(FLUSH_BUDGET_MS),
      })
        .then((r) => done({ code: r.ok ? 0 : 1 }))
        .catch(() => done({ code: 1 })); // never log the body or the keys
    },
    shutdown: async () => {},
  };
}

export interface Tracing {
  readonly enabled: boolean;
  readonly captureContent: boolean;
  startSpan(name: string, attributes: Record<string, string | number | boolean>, parent?: Span): Span;
  /** Await this in `finally`, after the root span has ended. Never throws, never outlives FLUSH_BUDGET_MS. */
  flush(): Promise<boolean>;
}

export function createTracing(env: TracingEnv, exporter: SpanExporter | undefined = fiExporter(env)): Tracing {
  const projectName = env.FI_PROJECT_NAME || "cloudflare-workers-ai";
  const provider = new BasicTracerProvider({
    resource: resourceFromAttributes({
      project_name: projectName, // a RESOURCE attribute: a span attribute with this key is not a substitute
      project_type: "observe",
      "service.name": projectName,
    }),
    // A batch processor whose timer never matters: flush() below is the only trigger.
    spanProcessors: exporter ? [new BatchSpanProcessor(exporter, { scheduledDelayMillis: 60_000 })] : [],
  });
  const tracer = provider.getTracer("fi-cloudflare-workers-ai");
  return {
    enabled: !!exporter,
    captureContent: (env.FI_CAPTURE_CONTENT || "").toLowerCase() === "true",
    startSpan(name, attributes, parent) {
      const ctx = parent ? trace.setSpan(context.active(), parent) : context.active();
      return tracer.startSpan(name, { attributes }, ctx);
    },
    async flush() {
      if (!exporter) return true;
      try {
        let timer: ReturnType<typeof setTimeout> | undefined;
        const timeout = new Promise<boolean>((resolve) => {
          timer = setTimeout(() => resolve(false), FLUSH_BUDGET_MS);
        });
        const ok = await Promise.race([provider.forceFlush().then(() => true), timeout]);
        clearTimeout(timer);
        return ok;
      } catch {
        return false; // a failed export never changes the user's response
      }
    },
  };
}

export function errorStatus(span: Span, err: unknown, captureContent: boolean) {
  const type = err instanceof Error ? err.name : "Error";
  span.setAttribute("error.type", type);
  // Raw error text can carry prompts, paths or hostnames: only the class name unless you opt in.
  span.setStatus({ code: SpanStatusCode.ERROR, message: captureContent && err instanceof Error ? err.message : type });
}
