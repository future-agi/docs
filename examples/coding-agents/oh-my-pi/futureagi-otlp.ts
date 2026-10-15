// Future AGI tracing hook for Oh My Pi (the omp.sh fork, binary `omp`,
// package `@oh-my-pi/pi-coding-agent`).
//
// Copy this file to `.omp/hooks/post/futureagi-otlp.ts` in a project you trust
// (or load it for one run with `omp --hook <path>`). It subscribes to omp's
// documented hook events (https://omp.sh/docs/hooks) and exports one OTLP
// trace per omp session to Future AGI:
//
//   omp.session (AGENT)                one per session, per omp process
//     omp.prompt (CHAIN)               one per submitted prompt (agent loop)
//       omp.turn (CHAIN)               one per model/tool turn
//         chat <model> (LLM)           one per assistant message
//         execute_tool <tool> (TOOL)   one per tool execution in that turn
//
// Default mode exports metadata only: ids, model and provider ids, token
// counts, omp's cost estimate, timings, tool names and byte sizes. Prompt text,
// assistant text, tool arguments, tool results, tool intents and error messages
// are dropped unless FI_CAPTURE_CONTENT=true. The hook only observes: it never
// returns a value from any handler, so it never blocks or rewrites a tool call,
// a tool result, the context or a message. It never runs shell commands and
// never reads omp's session files.
//
// Environment:
//   FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME   required; the hook is inert without them
//   FI_OTLP_ENDPOINT     full traces URL (default: $FI_BASE_URL/tracer/v1/traces)
//   FI_BASE_URL          default https://api.futureagi.com
//   FI_CAPTURE_CONTENT   "true" to export bounded, redacted content (default off)
//   FI_OTLP_TIMEOUT_MS   export timeout (default 10000)
//   FI_OTLP_DEBUG        "true" to print export failures to stderr
//
// omp loads only the default export. `createFutureAGIHook` is exported for tests.

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"
import { randomBytes } from "node:crypto"

const SCOPE = { name: "futureagi.oh-my-pi", version: "1.0.0" }
const CONTENT_LIMIT = 4096
// session_shutdown handlers get 2 s in omp 18.x; stay under it.
const SHUTDOWN_BUDGET_MS = 1800
const SECRET_PATTERNS: Array<[RegExp, string]> = [
  [/sk-[A-Za-z0-9_-]{12,}/g, "[REDACTED]"],
  [/(bearer\s+)[A-Za-z0-9._~+/=-]{12,}/gi, "$1[REDACTED]"],
  [/(api[_-]?key\s*[:=]\s*)[^\s,}"']+/gi, "$1[REDACTED]"],
]
const OMITTED = "error details omitted by default"

type Env = Record<string, string | undefined>
type AttrValue = string | number | boolean | string[]
type Attrs = Record<string, AttrValue | undefined | null>
type Span = {
  traceId: string
  spanId: string
  parentSpanId?: string
  name: string
  kind: number
  startTimeUnixNano: string
  endTimeUnixNano: string
  attributes: Array<{ key: string; value: Record<string, unknown> }>
  status: { code: number; message?: string }
}

export type HookOptions = { env?: Env; fetch?: typeof fetch; now?: () => number }

const truthy = (value: string | undefined) => ["1", "true", "yes", "on"].includes((value ?? "").trim().toLowerCase())
const hex = (bytes: number) => randomBytes(bytes).toString("hex")
const nanos = (ms: number) => `${Math.max(0, Math.round(ms))}000000`
const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : undefined)
const byteLength = (value: unknown) => {
  if (value === undefined || value === null) return 0
  const text = typeof value === "string" ? value : (JSON.stringify(value) ?? "")
  return Buffer.byteLength(text, "utf8")
}

function bounded(value: unknown): string {
  let text = typeof value === "string" ? value : (JSON.stringify(value) ?? "")
  for (const [pattern, replacement] of SECRET_PATTERNS) text = text.replace(pattern, replacement)
  return text.length > CONTENT_LIMIT ? text.slice(0, CONTENT_LIMIT) : text
}

// Text parts of an omp message or tool result. Thinking blocks are never included.
function textOf(content: unknown): string {
  if (typeof content === "string") return content
  if (!Array.isArray(content)) return ""
  return content
    .filter((part: any) => part?.type === "text" && typeof part.text === "string")
    .map((part: any) => part.text)
    .join("\n")
}

function otlpValue(value: AttrValue): Record<string, unknown> {
  if (Array.isArray(value)) return { arrayValue: { values: value.map((v) => ({ stringValue: String(v) })) } }
  if (typeof value === "boolean") return { boolValue: value }
  if (typeof value === "number") return Number.isInteger(value) ? { intValue: String(value) } : { doubleValue: value }
  return { stringValue: value }
}

function toAttributes(attrs: Attrs) {
  return Object.entries(attrs)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => ({ key, value: otlpValue(value as AttrValue) }))
}

type SessionState = {
  id: string
  traceId: string
  spanId: string
  start: number
  end?: number
  attrs: Attrs
  prompts: number
  turns: number
  llmCalls: number
  toolCalls: number
  toolErrors: number
  inputTokens: number
  outputTokens: number
  cost: number
  // Content for the trace list, only with FI_CAPTURE_CONTENT: first prompt in, last answer out.
  firstPrompt?: string
  lastOutput?: string
  prompt?: PromptState
  turn?: TurnState
  closed: boolean
}

type PromptState = {
  spanId: string
  index: number
  start: number
  end?: number
  promptBytes?: number
  prompt?: string
  output?: string
  stopReason?: string
  failed: boolean
}

type TurnState = {
  spanId: string
  index: number
  start: number
  toolCount: number
  stopReason?: string
  failed: boolean
}

type ToolState = {
  callId: string
  sessionId: string
  name: string
  spanId: string
  parentSpanId: string
  start: number
  inputBytes: number
  input?: string
  intent?: string
}

export function createFutureAGIHook(options: HookOptions = {}) {
  return function futureAGITracing(pi: ExtensionAPI) {
    const env: Env = options.env ?? process.env
    const doFetch = options.fetch ?? globalThis.fetch
    const now = options.now ?? Date.now
    const apiKey = env.FI_API_KEY
    const secretKey = env.FI_SECRET_KEY
    const projectName = env.FI_PROJECT_NAME
    if (!apiKey || !secretKey || !projectName) return

    const capture = truthy(env.FI_CAPTURE_CONTENT)
    const debug = truthy(env.FI_OTLP_DEBUG)
    const timeoutMs = Number(env.FI_OTLP_TIMEOUT_MS ?? "10000") || 10000
    const endpoint =
      env.FI_OTLP_ENDPOINT || `${(env.FI_BASE_URL || "https://api.futureagi.com").replace(/\/+$/, "")}/tracer/v1/traces`

    const sessions = new Map<string, SessionState>()
    const tools = new Map<string, ToolState>()
    let buffer: Span[] = []
    let pending: Promise<void> = Promise.resolve()
    const retried = new WeakSet<Span>()

    const log = (message: string) => {
      if (debug) console.error(`[futureagi-otlp] ${message}`)
    }

    function sessionIdOf(ctx: any): string | undefined {
      try {
        const id = ctx?.sessionManager?.getSessionId?.()
        return typeof id === "string" && id ? id : undefined
      } catch {
        return undefined
      }
    }

    function session(ctx: any): SessionState | undefined {
      const id = sessionIdOf(ctx)
      // No session id from omp: drop the event rather than invent a key.
      if (!id) return undefined
      let s = sessions.get(id)
      if (!s || s.closed) {
        s = {
          id,
          traceId: hex(16),
          spanId: hex(8),
          start: now(),
          attrs: {},
          prompts: 0,
          turns: 0,
          llmCalls: 0,
          toolCalls: 0,
          toolErrors: 0,
          inputTokens: 0,
          outputTokens: 0,
          cost: 0,
          closed: false,
        }
        sessions.set(id, s)
      }
      const agent = ctx?.agent ?? {}
      const seen: Attrs = {
        "omp.mode": ctx?.mode,
        "omp.cwd": typeof ctx?.cwd === "string" ? ctx.cwd : undefined,
        "omp.agent.kind": agent.kind,
        "omp.agent.id": agent.id,
        "omp.agent.name": agent.name,
        "omp.agent.depth": num(agent.depth),
        "omp.agent.parent_id": agent.parentId,
      }
      for (const [key, value] of Object.entries(seen)) if (value !== undefined && value !== null) s.attrs[key] = value
      return s
    }

    const base = (s: SessionState): Attrs => ({ "session.id": s.id, "gen_ai.conversation.id": s.id })

    function rootSpan(s: SessionState): Span {
      const end = s.end ?? now()
      return {
        traceId: s.traceId,
        spanId: s.spanId,
        name: "omp.session",
        kind: 1,
        startTimeUnixNano: nanos(s.start),
        endTimeUnixNano: nanos(Math.max(end, s.start)),
        attributes: toAttributes({
          "fi.span.kind": "AGENT",
          "gen_ai.span.kind": "AGENT",
          "gen_ai.operation.name": "invoke_agent",
          "gen_ai.agent.name": "oh-my-pi",
          ...base(s),
          "omp.prompt.count": s.prompts,
          "omp.turn.count": s.turns,
          "omp.llm.count": s.llmCalls,
          "omp.tool.count": s.toolCalls,
          "omp.tool.error.count": s.toolErrors,
          // Session totals use omp.* keys so they are not counted twice next to the LLM spans.
          "omp.usage.input_tokens": s.inputTokens,
          "omp.usage.output_tokens": s.outputTokens,
          "omp.usage.cost": s.cost > 0 ? s.cost : undefined,
          "omp.session.open": s.closed ? undefined : true,
          ...s.attrs,
          "input.value": capture ? s.firstPrompt : undefined,
          "input.mime_type": capture && s.firstPrompt ? "text/plain" : undefined,
          "output.value": capture ? s.lastOutput : undefined,
          "output.mime_type": capture && s.lastOutput ? "text/plain" : undefined,
        }),
        status: { code: 1 },
      }
    }

    function promptSpan(s: SessionState, p: PromptState): Span {
      const end = p.end ?? now()
      return {
        traceId: s.traceId,
        spanId: p.spanId,
        parentSpanId: s.spanId,
        name: "omp.prompt",
        kind: 1,
        startTimeUnixNano: nanos(p.start),
        endTimeUnixNano: nanos(Math.max(end, p.start)),
        attributes: toAttributes({
          "fi.span.kind": "CHAIN",
          "gen_ai.span.kind": "CHAIN",
          ...base(s),
          "omp.prompt.index": p.index,
          "omp.prompt.bytes": p.promptBytes,
          "omp.stop_reason": p.stopReason,
          "omp.incomplete": p.end === undefined ? true : undefined,
          "input.value": capture ? p.prompt : undefined,
          "input.mime_type": capture && p.prompt ? "text/plain" : undefined,
          "output.value": capture ? p.output : undefined,
          "output.mime_type": capture && p.output ? "text/plain" : undefined,
          "error.type": p.failed ? "ProviderError" : undefined,
        }),
        status: p.failed ? { code: 2, message: OMITTED } : p.end === undefined ? { code: 0 } : { code: 1 },
      }
    }

    function push(span: Span) {
      buffer.push(span)
      if (buffer.length >= 128) void flush()
    }

    function emitTurn(s: SessionState, t: TurnState, end: number | undefined) {
      push({
        traceId: s.traceId,
        spanId: t.spanId,
        parentSpanId: s.prompt?.spanId ?? s.spanId,
        name: "omp.turn",
        kind: 1,
        startTimeUnixNano: nanos(t.start),
        endTimeUnixNano: nanos(Math.max(end ?? now(), t.start)),
        attributes: toAttributes({
          "fi.span.kind": "CHAIN",
          "gen_ai.span.kind": "CHAIN",
          ...base(s),
          "omp.turn.index": t.index,
          "omp.turn.tool_count": t.toolCount,
          "omp.stop_reason": t.stopReason,
          "omp.incomplete": end === undefined ? true : undefined,
          "error.type": t.failed ? "ProviderError" : undefined,
        }),
        status: t.failed ? { code: 2, message: OMITTED } : end === undefined ? { code: 0 } : { code: 1 },
      })
    }

    function emitLlm(s: SessionState, message: any) {
      const usage = message.usage ?? {}
      const cost = usage.cost ?? {}
      const cacheRead = num(usage.cacheRead) ?? 0
      const cacheWrite = num(usage.cacheWrite) ?? 0
      const hasUsage = num(usage.input) !== undefined || num(usage.output) !== undefined
      // omp reports uncached input separately; the prompt size is input + cache reads + cache writes.
      const input = (num(usage.input) ?? 0) + cacheRead + cacheWrite
      const output = num(usage.output) ?? 0
      const failed = message.stopReason === "error"
      const start = num(message.timestamp) ?? now()
      const end = num(message.completedAt) ?? (num(message.duration) !== undefined ? start + message.duration : now())
      const text = textOf(message.content)
      s.llmCalls += 1
      if (hasUsage) {
        s.inputTokens += input
        s.outputTokens += output
      }
      if (num(cost.total)) s.cost += cost.total
      const turn = s.turn
      if (turn) {
        turn.stopReason = message.stopReason
        if (failed) turn.failed = true
      }
      if (s.prompt) {
        s.prompt.stopReason = message.stopReason
        if (failed) s.prompt.failed = true
        if (capture && text) s.prompt.output = bounded(text)
      }
      if (capture && text) s.lastOutput = bounded(text)
      const model = message.model ?? "unknown"
      push({
        traceId: s.traceId,
        spanId: hex(8),
        parentSpanId: turn?.spanId ?? s.prompt?.spanId ?? s.spanId,
        name: `chat ${model}`,
        kind: 3,
        startTimeUnixNano: nanos(start),
        endTimeUnixNano: nanos(Math.max(end, start)),
        attributes: toAttributes({
          "fi.span.kind": "LLM",
          "gen_ai.span.kind": "LLM",
          "gen_ai.operation.name": "chat",
          "gen_ai.request.model": model,
          "gen_ai.response.model": message.model,
          "gen_ai.provider.name": message.provider,
          "gen_ai.response.finish_reasons": message.stopReason ? [message.stopReason] : undefined,
          "gen_ai.usage.input_tokens": hasUsage ? input : undefined,
          "gen_ai.usage.output_tokens": hasUsage ? output : undefined,
          "gen_ai.usage.total_tokens": hasUsage ? (num(usage.totalTokens) ?? input + output) : undefined,
          "gen_ai.usage.cache_read.input_tokens": hasUsage ? cacheRead : undefined,
          "gen_ai.usage.cache_creation.input_tokens": hasUsage ? cacheWrite : undefined,
          "omp.usage.reasoning_tokens": num(usage.reasoningTokens),
          "gen_ai.cost.input": num(cost.total) ? num(cost.input) : undefined,
          "gen_ai.cost.output": num(cost.total) ? num(cost.output) : undefined,
          "gen_ai.cost.cache_read": num(cost.total) ? num(cost.cacheRead) : undefined,
          "gen_ai.cost.cache_write": num(cost.total) ? num(cost.cacheWrite) : undefined,
          "gen_ai.cost.total": num(cost.total) || undefined,
          "omp.api": message.api,
          "omp.llm.ttft_ms": num(message.ttft) !== undefined ? Math.round(message.ttft) : undefined,
          "omp.error.http_status": num(message.errorStatus),
          ...base(s),
          "output.value": capture && text ? bounded(text) : undefined,
          "output.mime_type": capture && text ? "text/plain" : undefined,
          "error.type": failed ? "ProviderError" : undefined,
        }),
        status: failed
          ? { code: 2, message: capture && message.errorMessage ? bounded(message.errorMessage) : OMITTED }
          : { code: 1 },
      })
    }

    function emitTool(s: SessionState, t: ToolState, end: number | undefined, isError: boolean, result: unknown) {
      const output = result === undefined ? undefined : textOf((result as any)?.content ?? result)
      s.toolCalls += 1
      if (isError) s.toolErrors += 1
      push({
        traceId: s.traceId,
        spanId: t.spanId,
        parentSpanId: t.parentSpanId,
        name: `execute_tool ${t.name}`,
        kind: 1,
        startTimeUnixNano: nanos(t.start),
        endTimeUnixNano: nanos(Math.max(end ?? now(), t.start)),
        attributes: toAttributes({
          "fi.span.kind": "TOOL",
          "gen_ai.span.kind": "TOOL",
          "gen_ai.operation.name": "execute_tool",
          "gen_ai.tool.name": t.name,
          "gen_ai.tool.call.id": t.callId,
          ...base(s),
          "omp.tool.input.bytes": t.inputBytes,
          "omp.tool.output.bytes": output === undefined ? undefined : byteLength(output),
          "omp.incomplete": end === undefined ? true : undefined,
          "omp.tool.intent": capture ? t.intent : undefined,
          "input.value": capture ? t.input : undefined,
          "input.mime_type": capture && t.input !== undefined ? "application/json" : undefined,
          "output.value": capture && output ? bounded(output) : undefined,
          "output.mime_type": capture && output ? "text/plain" : undefined,
          "error.type": isError ? "ToolError" : undefined,
        }),
        status: isError
          ? { code: 2, message: capture && output ? bounded(output) : OMITTED }
          : end === undefined
            ? { code: 0 }
            : { code: 1 },
      })
    }

    function closeTurn(s: SessionState, end: number | undefined) {
      const turn = s.turn
      if (!turn) return
      for (const t of tools.values()) {
        if (t.sessionId === s.id && t.parentSpanId === turn.spanId) {
          tools.delete(t.callId)
          emitTool(s, t, undefined, false, undefined)
        }
      }
      emitTurn(s, turn, end)
      s.turn = undefined
    }

    function closePrompt(s: SessionState, end: number | undefined) {
      closeTurn(s, end)
      if (!s.prompt) return
      if (end !== undefined) s.prompt.end = end
      push(promptSpan(s, s.prompt))
      s.prompt = undefined
    }

    function close(s: SessionState) {
      closePrompt(s, undefined)
      s.end = now()
      s.closed = true
      push(rootSpan(s))
    }

    function flush(): Promise<void> {
      // Re-send the session root (and the open prompt) with every batch: same span id and
      // start time, so the latest export wins and a killed process still leaves a rooted tree.
      const traces = new Set(buffer.map((span) => span.traceId))
      for (const s of sessions.values()) {
        if (!traces.has(s.traceId) || s.closed) continue
        if (s.prompt) buffer.push(promptSpan(s, s.prompt))
        buffer.push(rootSpan(s))
      }
      if (buffer.length === 0) return pending
      const spans = buffer
      buffer = []
      const body = JSON.stringify({
        resourceSpans: [
          {
            resource: {
              attributes: toAttributes({
                "service.name": "oh-my-pi",
                project_name: projectName!,
                project_type: "observe",
                "telemetry.sdk.name": "futureagi-oh-my-pi-hook",
                "telemetry.sdk.version": SCOPE.version,
              }),
            },
            scopeSpans: [{ scope: SCOPE, spans }],
          },
        ],
      })
      pending = pending.then(async () => {
        const started = now()
        try {
          const response = await doFetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Api-Key": apiKey!, "X-Secret-Key": secretKey! },
            body,
            signal: AbortSignal.timeout(timeoutMs),
          })
          if (response.ok) {
            log(`exported ${spans.length} spans in ${now() - started} ms`)
            return
          }
          log(`collector returned HTTP ${response.status}`)
        } catch (error) {
          // Never surface payloads or header values; never break the session.
          log(`export failed: ${(error as Error)?.name ?? "Error"}`)
        }
        // Give each span one more try with the next flush, then drop it.
        const again = spans.filter((span) => !retried.has(span))
        for (const span of again) retried.add(span)
        buffer.unshift(...again)
      })
      return pending
    }

    // Batch exports: a turn's spans leave about a second after the turn, a finished prompt's
    // spans 250 ms after it. In print mode the process exits right after the last turn, so
    // the shutdown handler cancels the timer and sends everything left as one request.
    let timer: ReturnType<typeof setTimeout> | undefined
    let due = Infinity
    function scheduleFlush(delayMs: number) {
      const at = now() + delayMs
      if (timer && at >= due) return
      if (timer) clearTimeout(timer)
      due = at
      timer = setTimeout(() => {
        timer = undefined
        due = Infinity
        void flush()
      }, delayMs)
      ;(timer as any).unref?.()
    }

    const within = (promise: Promise<void>, ms: number) =>
      Promise.race([promise, new Promise<void>((resolve) => (setTimeout(resolve, ms) as any).unref?.())])

    // Every handler returns undefined: observing only, never blocking or rewriting.
    const on = (event: string, fn: (event: any, ctx: any) => void | Promise<void>) =>
      (pi.on as any)(event, async (payload: any, ctx: any) => {
        try {
          await fn(payload, ctx)
        } catch (error) {
          log(`handler failed: ${(error as Error)?.name ?? "Error"}`)
        }
        return undefined
      })

    on("session_start", (_e, ctx) => {
      session(ctx)
    })

    on("session_switch", (_e, ctx) => {
      // /new, /resume or /fork inside one process: this agent's previous session is done.
      const s = session(ctx)
      if (!s) return
      for (const other of sessions.values()) {
        if (other !== s && !other.closed && other.attrs["omp.agent.id"] === s.attrs["omp.agent.id"]) close(other)
      }
      scheduleFlush(0)
    })

    on("agent_start", (_e, ctx) => {
      const s = session(ctx)
      if (!s) return
      closePrompt(s, undefined)
      s.prompts += 1
      s.prompt = { spanId: hex(8), index: s.prompts, start: now(), failed: false }
    })

    on("message_end", (event, ctx) => {
      const s = session(ctx)
      const message = event?.message
      if (!s || !message) return
      if (message.role === "user" && s.prompt && s.prompt.promptBytes === undefined) {
        const text = textOf(message.content)
        s.prompt.promptBytes = byteLength(text)
        if (capture) s.prompt.prompt = bounded(text)
        if (capture && s.firstPrompt === undefined) s.firstPrompt = s.prompt.prompt
      } else if (message.role === "assistant") {
        emitLlm(s, message)
      }
    })

    on("turn_start", (event, ctx) => {
      const s = session(ctx)
      if (!s) return
      closeTurn(s, undefined)
      s.turns += 1
      s.turn = { spanId: hex(8), index: num(event?.turnIndex) ?? s.turns - 1, start: num(event?.timestamp) ?? now(), toolCount: 0, failed: false }
    })

    on("tool_execution_start", (event, ctx) => {
      const s = session(ctx)
      if (!s || !event?.toolCallId) return
      if (s.turn) s.turn.toolCount += 1
      tools.set(event.toolCallId, {
        callId: event.toolCallId,
        sessionId: s.id,
        name: event.toolName ?? "unknown",
        spanId: hex(8),
        parentSpanId: s.turn?.spanId ?? s.prompt?.spanId ?? s.spanId,
        start: now(),
        inputBytes: byteLength(event.args),
        input: capture ? bounded(event.args ?? {}) : undefined,
        intent: capture && typeof event.intent === "string" ? bounded(event.intent) : undefined,
      })
    })

    on("tool_execution_end", (event, ctx) => {
      const s = session(ctx)
      const t = event?.toolCallId ? tools.get(event.toolCallId) : undefined
      if (!s || !t) return
      tools.delete(t.callId)
      emitTool(s, t, now(), event.isError === true, event.result)
    })

    on("turn_end", (_e, ctx) => {
      const s = session(ctx)
      if (!s) return
      closeTurn(s, now())
      scheduleFlush(1000)
    })

    on("agent_end", (_e, ctx) => {
      const s = session(ctx)
      if (!s) return
      closePrompt(s, now())
      scheduleFlush(250)
    })

    on("session_shutdown", async () => {
      if (timer) clearTimeout(timer)
      timer = undefined
      due = Infinity
      for (const s of sessions.values()) if (!s.closed) close(s)
      await within(
        flush().then(() => flush()),
        SHUTDOWN_BUDGET_MS,
      )
    })
  }
}

export default createFutureAGIHook()
