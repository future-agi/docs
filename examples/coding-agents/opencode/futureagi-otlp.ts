// Future AGI tracing plugin for OpenCode.
//
// Copy this file to `.opencode/plugins/futureagi-otlp.ts` in a project you
// trust. It listens to OpenCode's documented plugin events and hooks
// (https://opencode.ai/docs/plugins/) and exports one OTLP trace per OpenCode
// session to Future AGI:
//
//   opencode.session (AGENT)
//     opencode.turn (CHAIN)            one per user message
//       chat <model> (LLM)             one per assistant message (model step)
//         execute_tool <tool> (TOOL)   one per tool call in that step
//
// Default mode exports metadata only: ids, model and provider ids, token counts,
// timings, tool names and byte sizes. Prompt text, assistant text, tool
// arguments, tool output, session titles and error messages are dropped unless
// FI_CAPTURE_CONTENT=true. The plugin never blocks or rewrites a tool call,
// never runs shell commands, and never reads OpenCode's session storage.
//
// Environment:
//   FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME   required; plugin is inert without them
//   FI_OTLP_ENDPOINT     full traces URL (default: $FI_BASE_URL/tracer/v1/traces)
//   FI_BASE_URL          default https://api.futureagi.com
//   FI_CAPTURE_CONTENT   "true" to export bounded, redacted content (default off)
//   FI_OTLP_TIMEOUT_MS   export timeout (default 5000)
//   FI_OTLP_DEBUG        "true" to print export failures to stderr
//
// This file must export exactly one function: OpenCode loads every export of
// a plugin file as a plugin.

import type { Plugin } from "@opencode-ai/plugin"
import { createHash, randomBytes } from "node:crypto"

const SCOPE = { name: "futureagi.opencode", version: "1.0.0" }
const CONTENT_LIMIT = 4096
const SECRET_PATTERNS: Array<[RegExp, string]> = [
  [/sk-[A-Za-z0-9_-]{12,}/g, "[REDACTED]"],
  [/(bearer\s+)[A-Za-z0-9._~+/=-]{12,}/gi, "$1[REDACTED]"],
  [/(api[_-]?key\s*[:=]\s*)[^\s,}"']+/gi, "$1[REDACTED]"],
]

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

const truthy = (value: string | undefined) => ["1", "true", "yes", "on"].includes((value ?? "").trim().toLowerCase())
const sha = (value: string) => createHash("sha256").update(value).digest("hex")
const newSpanId = () => randomBytes(8).toString("hex")
const nanos = (ms: number) => `${Math.max(0, Math.round(ms))}000000`
const byteLength = (value: unknown) => {
  if (value === undefined || value === null) return 0
  const text = typeof value === "string" ? value : JSON.stringify(value) ?? ""
  return Buffer.byteLength(text, "utf8")
}

function bounded(value: unknown): string {
  let text = typeof value === "string" ? value : JSON.stringify(value) ?? ""
  for (const [pattern, replacement] of SECRET_PATTERNS) text = text.replace(pattern, replacement)
  return text.length > CONTENT_LIMIT ? text.slice(0, CONTENT_LIMIT) : text
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
  parentSpanId?: string
  parentSessionId?: string
  start: number
  last: number
  attrs: Attrs
  title?: string
  turns: number
  llmCalls: number
  toolCalls: number
  inputTokens: number
  outputTokens: number
  errorType?: string
  currentTurn?: string
  emitted: boolean
}

type TurnState = {
  id: string
  sessionId: string
  spanId: string
  index: number
  start: number
  agent?: string
  model?: string
  provider?: string
  promptBytes?: number
  prompt?: string
  output?: string
  errorType?: string
  emitted: boolean
}

type LlmState = {
  id: string
  sessionId: string
  turnId?: string
  spanId: string
  start: number
  end?: number
  info?: any
  text?: string
  emitted: boolean
}

type ToolState = {
  callId: string
  sessionId: string
  name: string
  spanId: string
  messageId?: string
  start?: number
  end?: number
  status?: string
  inputBytes?: number
  outputBytes?: number
  input?: string
  output?: string
  emitted: boolean
}

export const FutureAGITracing: Plugin = async (ctx, options) => {
  const opts = (options ?? {}) as { env?: Env; fetch?: typeof fetch; now?: () => number }
  const env: Env = opts.env ?? process.env
  const doFetch = opts.fetch ?? globalThis.fetch
  const now = opts.now ?? Date.now
  const apiKey = env.FI_API_KEY
  const secretKey = env.FI_SECRET_KEY
  const projectName = env.FI_PROJECT_NAME
  if (!apiKey || !secretKey || !projectName) return {}

  const capture = truthy(env.FI_CAPTURE_CONTENT)
  const debug = truthy(env.FI_OTLP_DEBUG)
  const timeoutMs = Number(env.FI_OTLP_TIMEOUT_MS ?? "5000") || 5000
  const endpoint =
    env.FI_OTLP_ENDPOINT || `${(env.FI_BASE_URL || "https://api.futureagi.com").replace(/\/+$/, "")}/tracer/v1/traces`

  const sessions = new Map<string, SessionState>()
  const turns = new Map<string, TurnState>()
  const llms = new Map<string, LlmState>()
  const tools = new Map<string, ToolState>()
  let buffer: Span[] = []
  let serviceVersion = "unknown"
  let pending: Promise<void> = Promise.resolve()

  const log = (message: string) => {
    if (debug) console.error(`[futureagi-otlp] ${message}`)
  }

  function session(id: string, info?: any): SessionState {
    let s = sessions.get(id)
    if (!s) {
      const parentSessionId: string | undefined = info?.parentID || undefined
      const parent = parentSessionId ? sessions.get(parentSessionId) : undefined
      const rootId = parent ? parent.traceId : sha(parentSessionId ?? id).slice(0, 32)
      s = {
        id,
        traceId: rootId,
        spanId: sha(`${id}:session`).slice(0, 16),
        parentSpanId: parentSessionId ? sha(`${parentSessionId}:session`).slice(0, 16) : undefined,
        parentSessionId,
        start: info?.time?.created ?? now(),
        last: now(),
        attrs: {},
        turns: 0,
        llmCalls: 0,
        toolCalls: 0,
        inputTokens: 0,
        outputTokens: 0,
        emitted: false,
      }
      sessions.set(id, s)
    }
    if (info) {
      if (info.version) serviceVersion = info.version
      s.attrs = {
        ...s.attrs,
        "opencode.version": info.version,
        "opencode.session.slug": info.slug,
        "opencode.project.id": info.projectID,
        "opencode.directory": info.directory,
      }
      if (info.title) s.title = info.title
    }
    s.last = now()
    return s
  }

  function push(span: Span) {
    buffer.push(span)
    if (buffer.length >= 128) void flush()
  }

  function emitTool(t: ToolState) {
    if (t.emitted) return
    t.emitted = true
    const s = session(t.sessionId)
    const llm = t.messageId ? llms.get(t.messageId) : undefined
    const turn = s.currentTurn ? turns.get(s.currentTurn) : undefined
    const parent = llm?.spanId ?? turn?.spanId ?? s.spanId
    const start = t.start ?? now()
    const failed = t.status === "error"
    s.toolCalls += 1
    push({
      traceId: s.traceId,
      spanId: t.spanId,
      parentSpanId: parent,
      name: `execute_tool ${t.name}`,
      kind: 1,
      startTimeUnixNano: nanos(start),
      endTimeUnixNano: nanos(t.end ?? start),
      attributes: toAttributes({
        "fi.span.kind": "TOOL",
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": t.name,
        "gen_ai.tool.call.id": t.callId,
        "session.id": s.id,
        "gen_ai.conversation.id": s.id,
        "opencode.tool.status": t.status ?? "unknown",
        "opencode.tool.input.bytes": t.inputBytes,
        "opencode.tool.output.bytes": t.outputBytes,
        "input.value": capture ? t.input : undefined,
        "input.mime_type": capture && t.input !== undefined ? "application/json" : undefined,
        "output.value": capture ? t.output : undefined,
        "output.mime_type": capture && t.output !== undefined ? "text/plain" : undefined,
        "error.type": failed ? "ToolError" : undefined,
      }),
      status: failed ? { code: 2, message: "error details omitted by default" } : { code: 1 },
    })
  }

  function emitLlm(l: LlmState) {
    if (l.emitted) return
    l.emitted = true
    const s = session(l.sessionId)
    const info = l.info ?? {}
    const turn = l.turnId ? turns.get(l.turnId) : undefined
    const tokens = info.tokens ?? {}
    const cache = tokens.cache ?? {}
    const input = (tokens.input ?? 0) + (cache.read ?? 0) + (cache.write ?? 0)
    const output = (tokens.output ?? 0) + (tokens.reasoning ?? 0)
    const hasUsage = info.tokens !== undefined
    const errorType: string | undefined = info.error?.name
    s.llmCalls += 1
    if (hasUsage) {
      s.inputTokens += input
      s.outputTokens += output
    }
    if (turn && capture && l.text) turn.output = l.text
    push({
      traceId: s.traceId,
      spanId: l.spanId,
      parentSpanId: turn?.spanId ?? s.spanId,
      name: `chat ${info.modelID ?? "unknown"}`,
      kind: 1,
      startTimeUnixNano: nanos(l.start),
      endTimeUnixNano: nanos(l.end ?? now()),
      attributes: toAttributes({
        "fi.span.kind": "LLM",
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": info.modelID,
        "gen_ai.response.model": info.modelID,
        "gen_ai.provider.name": info.providerID,
        "gen_ai.usage.input_tokens": hasUsage ? input : undefined,
        "gen_ai.usage.output_tokens": hasUsage ? output : undefined,
        "gen_ai.usage.total_tokens": hasUsage ? (tokens.total ?? input + output) : undefined,
        "gen_ai.usage.cache_read.input_tokens": hasUsage ? cache.read : undefined,
        "gen_ai.usage.cache_creation.input_tokens": hasUsage ? cache.write : undefined,
        "opencode.usage.reasoning_tokens": hasUsage ? tokens.reasoning : undefined,
        "opencode.cost": typeof info.cost === "number" ? info.cost : undefined,
        "gen_ai.response.finish_reasons": info.finish ? [info.finish] : undefined,
        "session.id": s.id,
        "gen_ai.conversation.id": s.id,
        "opencode.message.id": l.id,
        "opencode.agent": info.agent ?? info.mode,
        "opencode.incomplete": l.end === undefined ? true : undefined,
        "output.value": capture && l.text ? l.text : undefined,
        "output.mime_type": capture && l.text ? "text/plain" : undefined,
        "error.type": errorType,
      }),
      status: errorType ? { code: 2, message: "error details omitted by default" } : { code: 1 },
    })
  }

  function emitTurn(t: TurnState, end: number) {
    if (t.emitted) return
    t.emitted = true
    const s = session(t.sessionId)
    for (const l of llms.values()) if (l.turnId === t.id && !l.emitted) emitLlm(l)
    const errorType = t.errorType
    push({
      traceId: s.traceId,
      spanId: t.spanId,
      parentSpanId: s.spanId,
      name: "opencode.turn",
      kind: 1,
      startTimeUnixNano: nanos(t.start),
      endTimeUnixNano: nanos(Math.max(end, t.start)),
      attributes: toAttributes({
        "fi.span.kind": "CHAIN",
        "session.id": s.id,
        "gen_ai.conversation.id": s.id,
        "opencode.message.id": t.id,
        "opencode.turn.index": t.index,
        "opencode.agent": t.agent,
        "opencode.model.id": t.model,
        "opencode.provider.id": t.provider,
        "opencode.prompt.bytes": t.promptBytes,
        "input.value": capture ? t.prompt : undefined,
        "input.mime_type": capture && t.prompt ? "text/plain" : undefined,
        "output.value": capture ? t.output : undefined,
        "output.mime_type": capture && t.output ? "text/plain" : undefined,
        "error.type": errorType,
      }),
      status: errorType ? { code: 2, message: "error details omitted by default" } : { code: 1 },
    })
    if (s.currentTurn === t.id) s.currentTurn = undefined
  }

  function emitSession(s: SessionState, end: number) {
    if (s.emitted) return
    s.emitted = true
    push({
      traceId: s.traceId,
      spanId: s.spanId,
      parentSpanId: s.parentSpanId,
      name: "opencode.session",
      kind: 1,
      startTimeUnixNano: nanos(s.start),
      endTimeUnixNano: nanos(Math.max(end, s.start)),
      attributes: toAttributes({
        "fi.span.kind": "AGENT",
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "opencode",
        "session.id": s.id,
        "gen_ai.conversation.id": s.id,
        "opencode.session.parent_id": s.parentSessionId,
        "opencode.turn.count": s.turns,
        "opencode.llm.count": s.llmCalls,
        "opencode.tool.count": s.toolCalls,
        "opencode.usage.input_tokens": s.inputTokens,
        "opencode.usage.output_tokens": s.outputTokens,
        "opencode.session.title": capture && s.title ? bounded(s.title) : undefined,
        "error.type": s.errorType,
        ...s.attrs,
      }),
      status: s.errorType ? { code: 2, message: "error details omitted by default" } : { code: 1 },
    })
  }

  // Close every finished child of a session; with `final`, also close what is still open.
  function settle(sessionId: string, final: boolean) {
    const s = sessions.get(sessionId)
    if (!s) return
    const t = now()
    for (const tool of tools.values()) {
      if (tool.sessionId !== sessionId || tool.emitted) continue
      if (tool.end !== undefined || final) emitTool(tool)
    }
    for (const l of llms.values()) {
      if (l.sessionId !== sessionId || l.emitted) continue
      if (l.end !== undefined || final) emitLlm(l)
    }
    for (const turn of turns.values()) {
      if (turn.sessionId === sessionId && !turn.emitted) emitTurn(turn, t)
    }
    if (final) emitSession(s, t)
  }

  function flush(): Promise<void> {
    if (buffer.length === 0) return pending
    const spans = buffer
    buffer = []
    const body = JSON.stringify({
      resourceSpans: [
        {
          resource: {
            attributes: toAttributes({
              "service.name": "opencode",
              "service.version": serviceVersion,
              project_name: projectName!,
              project_type: "observe",
              "telemetry.sdk.name": "futureagi-opencode-plugin",
              "telemetry.sdk.version": SCOPE.version,
            }),
          },
          scopeSpans: [{ scope: SCOPE, spans }],
        },
      ],
    })
    pending = pending.then(async () => {
      try {
        const response = await doFetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Api-Key": apiKey!, "X-Secret-Key": secretKey! },
          body,
          signal: AbortSignal.timeout(timeoutMs),
        })
        if (!response.ok) log(`collector returned HTTP ${response.status}`)
      } catch (error) {
        // Never surface payloads or header values; never break the session.
        log(`export failed: ${(error as Error)?.name ?? "Error"}`)
      }
    })
    return pending
  }

  function onMessage(info: any) {
    if (!info?.id || !info?.sessionID) return
    const s = session(info.sessionID)
    if (info.role === "user") {
      let turn = turns.get(info.id)
      if (!turn) {
        const previous = s.currentTurn ? turns.get(s.currentTurn) : undefined
        if (previous && !previous.emitted) {
          settle(s.id, false)
          emitTurn(previous, info.time?.created ?? now())
        }
        s.turns += 1
        turn = {
          id: info.id,
          sessionId: s.id,
          spanId: newSpanId(),
          index: s.turns,
          start: info.time?.created ?? now(),
          emitted: false,
        }
        turns.set(info.id, turn)
        s.currentTurn = info.id
      }
      turn.agent = info.agent ?? turn.agent
      turn.model = info.model?.modelID ?? turn.model
      turn.provider = info.model?.providerID ?? turn.provider
      return
    }
    if (info.role !== "assistant") return
    let l = llms.get(info.id)
    if (!l) {
      l = {
        id: info.id,
        sessionId: s.id,
        turnId: info.parentID ?? s.currentTurn,
        spanId: newSpanId(),
        start: info.time?.created ?? now(),
        emitted: false,
      }
      llms.set(info.id, l)
    }
    l.info = info
    if (info.error) {
      const turn = l.turnId ? turns.get(l.turnId) : undefined
      if (turn) turn.errorType = info.error.name ?? "Error"
    }
    if (info.time?.completed || info.error) {
      l.end = info.time?.completed ?? now()
      for (const tool of tools.values()) if (tool.messageId === l.id && tool.end !== undefined) emitTool(tool)
      emitLlm(l)
    }
  }

  function tool(callId: string, sessionId: string, name: string): ToolState {
    let t = tools.get(callId)
    if (!t) {
      session(sessionId)
      t = { callId, sessionId, name, spanId: newSpanId(), emitted: false }
      tools.set(callId, t)
    }
    return t
  }

  function onPart(part: any) {
    if (!part?.sessionID) return
    if (part.type === "tool" && part.callID) {
      const t = tool(part.callID, part.sessionID, part.tool ?? "unknown")
      t.messageId = part.messageID ?? t.messageId
      const state = part.state ?? {}
      if (state.time?.start) t.start = state.time.start
      if (state.status === "completed" || state.status === "error") {
        t.status = state.status
        t.end = state.time?.end ?? now()
        if (state.status === "error") {
          t.outputBytes = byteLength(state.error)
          if (capture) t.output = bounded(state.error)
        }
        emitTool(t)
      } else if (state.status) {
        t.status = state.status
      }
      return
    }
    if (part.type === "text" && capture && part.messageID && !part.synthetic) {
      const l = llms.get(part.messageID)
      if (l && typeof part.text === "string") l.text = bounded(part.text)
    }
  }

  const guard =
    <A extends unknown[]>(fn: (...args: A) => void | Promise<void>) =>
    async (...args: A) => {
      try {
        await fn(...args)
      } catch (error) {
        log(`handler failed: ${(error as Error)?.name ?? "Error"}`)
      }
    }

  return {
    event: guard(async ({ event }: { event: any }) => {
      const p = event?.properties ?? {}
      switch (event?.type) {
        case "session.created":
        case "session.updated":
          if (p.info?.id) session(p.info.id, p.info)
          break
        case "message.updated":
          onMessage(p.info)
          break
        case "message.part.updated":
          onPart(p.part)
          break
        case "session.error":
          if (p.sessionID) {
            const s = session(p.sessionID)
            s.errorType = p.error?.name ?? "Error"
            const turn = s.currentTurn ? turns.get(s.currentTurn) : undefined
            if (turn) turn.errorType = s.errorType
          }
          break
        case "session.idle":
          if (p.sessionID) {
            settle(p.sessionID, false)
            await flush()
          }
          break
        case "session.deleted":
          if (p.info?.id) {
            settle(p.info.id, true)
            await flush()
          }
          break
      }
    }),
    "chat.message": guard(async (input: any, output: any) => {
      const messageId = output?.message?.id ?? input?.messageID
      const sessionId = input?.sessionID ?? output?.message?.sessionID
      if (!messageId || !sessionId) return
      onMessage({ ...output.message, id: messageId, sessionID: sessionId, role: "user" })
      const turn = turns.get(messageId)
      if (!turn) return
      const text = (output?.parts ?? [])
        .filter((part: any) => part?.type === "text" && !part.synthetic && typeof part.text === "string")
        .map((part: any) => part.text)
        .join("\n")
      turn.promptBytes = byteLength(text)
      if (capture) turn.prompt = bounded(text)
    }),
    "tool.execute.before": guard(async (input: any, output: any) => {
      if (!input?.callID || !input?.sessionID) return
      const t = tool(input.callID, input.sessionID, input.tool ?? "unknown")
      t.start = t.start ?? now()
      t.inputBytes = byteLength(output?.args)
      if (capture) t.input = bounded(output?.args ?? {})
    }),
    "tool.execute.after": guard(async (input: any, output: any) => {
      if (!input?.callID || !input?.sessionID) return
      const t = tool(input.callID, input.sessionID, input.tool ?? "unknown")
      t.outputBytes = byteLength(output?.output)
      if (capture) t.output = bounded(output?.output ?? "")
      t.end = t.end ?? now()
      t.status = t.status ?? "completed"
    }),
    dispose: guard(async () => {
      for (const id of sessions.keys()) settle(id, true)
      await flush()
    }),
  }
}
