// Trace @openrouter/agent runs in Future AGI.
//
// callModel() emits no OpenTelemetry spans of its own and takes no endpoint, headers or resource.
// It does fire lifecycle hooks (SessionStart, PostModelCall, PreToolUse, PostToolUse,
// PostToolUseFailure, SessionEnd), and PostModelCall is documented upstream as the telemetry
// primitive: one span per model call. This file turns those hooks into spans:
//
//   invoke_agent openrouter-agent   one callModel() run            fi.span.kind AGENT
//   |- chat <model>                 one model request              LLM: model, tokens, duration
//   |- execute_tool <tool>          one tool execution             TOOL: duration, ERROR on failure
//   `- chat <model> ...             the follow-up request after the tool result
//
// Nothing here wraps or monkey-patches callModel. Use one hooks object per callModel() call.
//
// Privacy: by default only metadata leaves the process. The prompt, tool arguments, tool results
// and error text are exported only with captureContent / FI_CAPTURE_CONTENT=1. A stack trace is
// never exported, because it holds absolute local file paths.
import { context, trace, SpanStatusCode } from '@opentelemetry/api';
import { BasicTracerProvider, BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';

const TRUE = new Set(['1', 'true', 'yes', 'on']);
export const envCaptureContent = () => TRUE.has((process.env.FI_CAPTURE_CONTENT ?? '').toLowerCase());

/** A tracer provider that exports to Future AGI (traces only, OTLP over HTTP, no gzip). */
export function buildTracerProvider({
  projectName = process.env.FI_PROJECT_NAME ?? 'openrouter-agent-app',
  baseUrl = process.env.FI_BASE_URL ?? 'https://api.futureagi.com',
  apiKey = process.env.FI_API_KEY,
  secretKey = process.env.FI_SECRET_KEY,
  spanProcessors,
} = {}) {
  if (!spanProcessors && (!apiKey || !secretKey)) throw new Error('set FI_API_KEY and FI_SECRET_KEY');
  const exporter = spanProcessors
    ? null
    : new OTLPTraceExporter({
        url: `${baseUrl.replace(/\/+$/, '')}/tracer/v1/traces`,
        headers: { 'X-Api-Key': apiKey, 'X-Secret-Key': secretKey },
        // The exporter sends no compression by default; Future AGI also accepts gzip.
      });
  return new BasicTracerProvider({
    // Future AGI files spans by the RESOURCE attribute project_name.
    resource: resourceFromAttributes({ project_name: projectName, project_type: 'observe' }),
    spanProcessors: spanProcessors ?? [new BatchSpanProcessor(exporter)],
  });
}

const json = (value) => {
  try {
    return typeof value === 'string' ? value : JSON.stringify(value);
  } catch {
    return String(value);
  }
};
const MAX_CONTENT = 32_000;
const clip = (text) => (text.length > MAX_CONTENT ? `${text.slice(0, MAX_CONTENT)}...[truncated]` : text);
const errorName = (error) => (error instanceof Error ? error.name : typeof error);
const errorMessage = (error) => (error instanceof Error ? error.message : json(error));

/**
 * Lifecycle hooks for one callModel() run:
 *   callModel(client, { model, input, tools, hooks: createTraceHooks(provider) })
 */
export function createTraceHooks(provider, { captureContent = envCaptureContent(), agentName = 'openrouter-agent' } = {}) {
  const tracer = provider.getTracer('futureagi-openrouter-agent');
  let root;
  let prompt;
  const pendingTools = new Map(); // tool name -> FIFO of { start, input }
  const childCtx = () => trace.setSpan(context.active(), root);
  const ensureRoot = () => {
    if (!root) {
      root = tracer.startSpan(`invoke_agent ${agentName}`, {
        attributes: {
          'fi.span.kind': 'AGENT',
          'gen_ai.operation.name': 'invoke_agent',
          'gen_ai.provider.name': 'openrouter',
          'gen_ai.agent.name': agentName,
        },
      });
      if (captureContent && prompt !== undefined) root.setAttribute('input.value', clip(prompt));
    }
    return root;
  };

  return {
    SessionStart: [{ handler: () => void ensureRoot() }],
    UserPromptSubmit: [
      {
        // Fires after SessionStart, before the first request; observe only (no mutation).
        handler: ({ prompt: text }) => {
          prompt = text;
          if (captureContent && root) root.setAttribute('input.value', clip(text));
        },
      },
    ],
    PostModelCall: [
      {
        handler: ({ model, responseId, durationMs, usage, turnType, turnNumber }) => {
          ensureRoot();
          const end = Date.now();
          const span = tracer.startSpan(
            `chat ${model}`,
            {
              startTime: end - durationMs,
              attributes: {
                'fi.span.kind': 'LLM',
                'gen_ai.operation.name': 'chat',
                'gen_ai.provider.name': 'openrouter',
                'gen_ai.request.model': model,
                'gen_ai.response.id': responseId,
                'openrouter.agent.turn_type': turnType,
                'openrouter.agent.turn_number': turnNumber,
              },
            },
            childCtx(),
          );
          if (usage) {
            span.setAttributes({
              'gen_ai.usage.input_tokens': usage.inputTokens,
              'gen_ai.usage.output_tokens': usage.outputTokens,
              'gen_ai.usage.total_tokens': usage.totalTokens,
            });
            if (usage.cost !== undefined) span.setAttribute('gen_ai.cost.total', usage.cost);
          }
          span.end(end);
        },
      },
    ],
    PreToolUse: [
      {
        handler: ({ toolName, toolInput }) => {
          ensureRoot();
          const queue = pendingTools.get(toolName) ?? [];
          queue.push({ start: Date.now(), input: toolInput });
          pendingTools.set(toolName, queue);
        },
      },
    ],
    PostToolUse: [
      {
        handler: ({ toolName, toolOutput, durationMs }) => {
          const call = pendingTools.get(toolName)?.shift();
          const span = toolSpan(toolName, call, durationMs);
          if (captureContent) {
            span.setAttribute('input.value', clip(json(call?.input ?? {})));
            span.setAttribute('output.value', clip(json(toolOutput)));
          }
          span.end();
        },
      },
    ],
    PostToolUseFailure: [
      {
        handler: ({ toolName, error }) => {
          const call = pendingTools.get(toolName)?.shift();
          const span = toolSpan(toolName, call);
          span.setAttribute('error.type', errorName(error));
          // Error text can hold user data and paths, so it follows the content switch. Never the stack.
          span.setStatus({ code: SpanStatusCode.ERROR, message: captureContent ? clip(errorMessage(error)) : errorName(error) });
          if (captureContent) {
            span.setAttribute('input.value', clip(json(call?.input ?? {})));
            span.setAttribute('error.message', clip(errorMessage(error)));
          }
          span.end();
        },
      },
    ],
    SessionEnd: [
      {
        handler: ({ reason, totalUsage }) => {
          ensureRoot();
          root.setAttribute('openrouter.agent.end_reason', reason);
          if (totalUsage) root.setAttribute('openrouter.agent.model_calls', totalUsage.modelCalls);
          // Token totals stay on the chat spans only, so a sum over the trace counts each call once.
          if (reason !== 'complete') root.setStatus({ code: SpanStatusCode.ERROR, message: reason });
          root.end();
        },
      },
    ],
  };

  function toolSpan(toolName, call, durationMs) {
    ensureRoot();
    const end = Date.now();
    const start = call?.start ?? (durationMs !== undefined ? end - durationMs : end);
    return tracer.startSpan(
      `execute_tool ${toolName}`,
      {
        startTime: start,
        attributes: { 'fi.span.kind': 'TOOL', 'gen_ai.operation.name': 'execute_tool', 'gen_ai.tool.name': toolName },
      },
      childCtx(),
    );
  }
}
