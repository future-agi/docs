// Future AGI settings for the Flue OpenTelemetry recipe. Pure functions of the
// environment, so they can be unit-tested without Flue or the network.
import type { ContentOption } from '@flue/opentelemetry';

type Env = Readonly<Record<string, string | undefined>>;

/** True when the app opted in to exporting prompts, outputs and tool payloads. */
export function captureContentEnabled(env: Env = process.env): boolean {
  return /^(1|true|yes|on)$/i.test((env.FI_CAPTURE_CONTENT ?? '').trim());
}

/**
 * The `content` option for createOpenTelemetryInstrumentation().
 *
 * Flue exports content by default: model messages, system instructions, tool
 * definitions, tool arguments and results, exception messages and stack traces.
 * `false` removes all of it. This recipe passes `false` unless the app sets
 * FI_CAPTURE_CONTENT=1. The opt-in keeps Flue's content (up to its 56 KiB
 * per-span budget) but still drops stack traces, which carry absolute local
 * paths.
 */
export function contentOption(env: Env = process.env): ContentOption {
  if (!captureContentEnabled(env)) return false;
  return {
    transform: (content, scope) => (scope.contentType === 'exception_stacktrace' ? undefined : content),
  };
}

/** The OTLP/HTTP traces URL: FI_BASE_URL (default: hosted) + /tracer/v1/traces. */
export function tracesUrl(env: Env = process.env): string {
  const base = (env.FI_BASE_URL || 'https://api.futureagi.com').replace(/\/+$/, '');
  return `${base}/tracer/v1/traces`;
}

/** Both auth headers are required; one alone is a failed setup. */
export function exporterHeaders(env: Env = process.env): Record<string, string> | null {
  const apiKey = env.FI_API_KEY?.trim();
  const secretKey = env.FI_SECRET_KEY?.trim();
  if (!apiKey || !secretKey) return null;
  return { 'X-Api-Key': apiKey, 'X-Secret-Key': secretKey };
}

/**
 * Resource attributes. Future AGI files spans by the RESOURCE attribute
 * `project_name`; a span attribute with that key does not count.
 */
export function resourceAttributes(env: Env = process.env): Record<string, string> {
  const project = env.FI_PROJECT_NAME?.trim() || 'flue-agent';
  return {
    project_name: project,
    project_type: 'observe',
    'service.name': env.OTEL_SERVICE_NAME?.trim() || project,
  };
}
