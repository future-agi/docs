// Future AGI destination pieces for eve's OpenTelemetry pipeline.
//
// eve sends every span in the process to each destination, including the
// durable-workflow plumbing under instrumentation scope "workflow" (dozens of
// spans per turn, in separate traces). This file keeps eve's agent spans
// (scope "eve.agent") and anything else you add, and drops the plumbing.
import type { Context } from "@opentelemetry/api";
import {
  BatchSpanProcessor,
  type ReadableSpan,
  type Span,
  type SpanExporter,
  type SpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { OTLPHttpProtoTraceExporter } from "@vercel/otel";
import type { SpanExportPolicy } from "eve/instrumentation/otel";

/** Instrumentation scopes that never reach Future AGI. */
export const DROPPED_SCOPES: ReadonlySet<string> = new Set([
  "workflow", // durable orchestration: steps, queues, replays, routes
  "@vercel/otel/fetch", // outbound HTTP spans, when fetch instrumentation is on
]);

type Env = Readonly<Record<string, string | undefined>>;

/** The instrumentation scope name of a span (OTel JS SDK 2.x and 1.x shapes). */
export function scopeName(span: ReadableSpan | Span): string {
  const s = span as unknown as {
    instrumentationScope?: { name?: string };
    instrumentationLibrary?: { name?: string };
  };
  return s.instrumentationScope?.name ?? s.instrumentationLibrary?.name ?? "";
}

/** True when the app opted in to exporting prompts, outputs and tool payloads. */
export function captureContentEnabled(env: Env = process.env): boolean {
  return /^(1|true|yes|on)$/i.test((env.FI_CAPTURE_CONTENT ?? "").trim());
}

/**
 * Attributes that identify the caller. eve copies the authenticated principal's
 * id here, which can be a user id or an email, so they are dropped unless the
 * app opted in to content capture. The principal *type* is kept.
 */
export const PRINCIPAL_ID_KEYS: ReadonlySet<string> = new Set([
  "agent.principal.current.id",
  "agent.principal.initiator.id",
]);

/**
 * The Future AGI destination's export policy. By default it keeps span
 * metadata (names, timing, model, tokens, tool names, status code) and redacts
 * content: prompts, system instructions, tool definitions, model output, tool
 * arguments and results, error messages, exception events, the session title,
 * and the principal ids above. FI_CAPTURE_CONTENT=1 turns all of that back on,
 * up to eve's own otel({ tracePolicy }) ceiling.
 */
export function futureAGIExportPolicy(env: Env = process.env): SpanExportPolicy[] {
  if (captureContentEnabled(env)) return [];
  return [
    {
      span: () => ({ redact: true, inputs: true, outputs: true }),
      attribute: ({ key }) => ({ emit: !PRINCIPAL_ID_KEYS.has(key) }),
    },
  ];
}

/** Forwards a span to `next` unless its instrumentation scope is dropped. */
export class ScopeFilterSpanProcessor implements SpanProcessor {
  readonly next: SpanProcessor;
  readonly dropped: ReadonlySet<string>;

  constructor(next: SpanProcessor, dropped: ReadonlySet<string> = DROPPED_SCOPES) {
    this.next = next;
    this.dropped = dropped;
  }

  onStart(span: Span, parentContext: Context): void {
    if (!this.dropped.has(scopeName(span))) this.next.onStart(span, parentContext);
  }

  onEnd(span: ReadableSpan): void {
    if (!this.dropped.has(scopeName(span))) this.next.onEnd(span);
  }

  forceFlush(): Promise<void> {
    return this.next.forceFlush();
  }

  shutdown(): Promise<void> {
    return this.next.shutdown();
  }
}

/** The OTLP/HTTP traces URL: FI_BASE_URL (default: hosted) + /tracer/v1/traces. */
export function futureAGITracesUrl(env: Env = process.env): string {
  const base = (env.FI_BASE_URL || "https://api.futureagi.com").replace(/\/+$/, "");
  return `${base}/tracer/v1/traces`;
}

/** OTLP/HTTP protobuf exporter for the Future AGI trace endpoint. */
export function futureAGIExporter(env: Env = process.env): OTLPHttpProtoTraceExporter {
  return new OTLPHttpProtoTraceExporter({
    url: futureAGITracesUrl(env),
    headers: {
      "X-Api-Key": env.FI_API_KEY ?? "",
      "X-Secret-Key": env.FI_SECRET_KEY ?? "",
    },
  });
}

/** Scope filter in front of a batching processor in front of the exporter. */
export function futureAGISpanProcessor(
  exporter: SpanExporter = futureAGIExporter(),
): ScopeFilterSpanProcessor {
  return new ScopeFilterSpanProcessor(new BatchSpanProcessor(exporter));
}
