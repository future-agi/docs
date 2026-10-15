// Future AGI tracing plugin for OpenCode.
//
// Copy this file to `.opencode/plugins/futureagi-otlp.ts` in a project you
// trust. It listens to OpenCode's documented plugin events and the
// `tool.execute.after` hook (https://opencode.ai/docs/plugins/), plus the
// `dispose` hook of the `Hooks` type in @opencode-ai/plugin 1.19.0 (a final
// refresh only), and exports one OTLP trace per OpenCode session to Future AGI.
// It registers no hook that runs before a prompt or a tool call
// (`chat.message`, `tool.execute.before`), so it can never hold one up:
//
//   opencode.session (AGENT)
//     opencode.turn (CHAIN)            one per user message
//       chat <model> (LLM)             one per assistant message (model step)
//         execute_tool <tool> (TOOL)   one per tool call in that step
//
// Spans are sent each time a session goes idle. Every send also carries a
// fresh copy of the session span (same span id and start time; the latest
// copy wins), so the trace has its root without waiting for OpenCode to exit.
//
// Default mode exports metadata only: ids, model and provider ids, token counts,
// timings, tool names, error types and byte sizes. Prompt text, assistant text,
// tool arguments, tool output, session titles, error messages and the project
// directory are dropped unless FI_CAPTURE_CONTENT=true. The plugin never blocks
// or rewrites a tool call, never runs shell commands, and never reads
// OpenCode's session storage.
//
// Environment:
//   FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME   required; plugin is inert without them
//   FI_OTLP_ENDPOINT     full traces URL (default: $FI_BASE_URL/tracer/v1/traces)
//   FI_BASE_URL          default https://api.futureagi.com
//   FI_CAPTURE_CONTENT   "true" to export bounded, redacted content (default off)
//   FI_OTLP_TIMEOUT_MS   timeout of each export request (default 3000)
//   FI_OTLP_DEBUG        "true" to print export failures to stderr
//
// This file must export exactly one function: OpenCode loads every export of
// a plugin file as a plugin.

import type { Plugin } from "@opencode-ai/plugin"
import { createHash } from "node:crypto"

const SCOPE = { name: "futureagi.opencode", version: "1.1.0" }
// Content fields are capped at this many UTF-8 bytes (4 KiB).
const CONTENT_LIMIT_BYTES = 4096
// Key-value secrets in text (`api_key=...`) and in JSON (`"api_key":"..."`).
// Key names ending in api_key, secret_key, private_key, access_key (and
// AWS-style secret_access_key), token, secret, password or passwd, with any
// prefix (OPENAI_API_KEY, x-api-key, client_secret, access_token).
const SECRET_KEY = String.raw`["']?[A-Za-z0-9_.-]*(?:api[_-]?key|(?:secret|private|access)(?:[_-]?access)?[_-]?key|token|secret|password|passwd)["']?`
const SECRET_PATTERNS: Array<[RegExp, string]> = [
  [/sk-[A-Za-z0-9_-]{12,}/g, "[REDACTED]"],
  [/(bearer\s+)[A-Za-z0-9._~+/=-]{12,}/gi, "$1[REDACTED]"],
  [new RegExp(String.raw`(${SECRET_KEY}\s*[:=]\s*["']?)[^\s,}"']+`, "gi"), "$1[REDACTED]"],
]
// OpenCode 1.19.0 error names that are not failures of the turn.
const ABORTED = "MessageAbortedError"
const CONTEXT_OVERFLOW = "ContextOverflowError"
// Test seam. Plugin options come from opencode.json, which cannot hold a
// symbol key, so configuration can never replace the environment or fetch.
const TEST_SEAM = Symbol.for("futureagi.opencode.test")

type Env = Record<string, string | undefined>
type AttrValue = string | number | boolean | string[]
type Attrs = Record<string, AttrValue | undefined | null>
type Status = { code: number; message?: string }
type Span = {
  traceId: string
  spanId: string
  parentSpanId?: string
  name: string
  kind: number
  startTimeUnixNano: string
  endTimeUnixNano: string
  attributes: Array<{ key: string; value: Record<string, unknown> }>
  status: Status
}

const truthy = (value: string | undefined) => ["1", "true", "yes", "on"].includes((value ?? "").trim().toLowerCase())
const sha = (value: string) => createHash("sha256").update(value).digest("hex")
// Span ids derive from OpenCode's ids, so a span sent twice (a retry, or a
// plugin reload mid-session) overwrites instead of duplicating.
const spanId = (key: string) => sha(key).slice(0, 16)
const nanos = (ms: number) => `${Math.max(0, Math.round(ms))}000000`
const byteLength = (value: unknown) => {
  if (value === undefined || value === null) return 0
  const text = typeof value === "string" ? value : JSON.stringify(value) ?? ""
  return Buffer.byteLength(text, "utf8")
}
// Error names are class names (APIError, ToolError). Anything else is replaced.
const errorName = (value: unknown) =>
  typeof value === "string" && /^[A-Za-z][A-Za-z0-9_.]{0,63}$/.test(value) ? value : "Error"

function bounded(value: unknown): string {
  let text = typeof value === "string" ? value : JSON.stringify(value) ?? ""
  for (const [pattern, replacement] of SECRET_PATTERNS) text = text.replace(pattern, replacement)
  const bytes = Buffer.from(text, "utf8")
  if (bytes.length <= CONTENT_LIMIT_BYTES) return text
  // Cut on a character boundary: never split a multi-byte character.
  let end = CONTENT_LIMIT_BYTES
  while (end > 0 && (bytes[end] & 0xc0) === 0x80) end--
  return bytes.subarray(0, end).toString("utf8")
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
  end: number
  attrs: Attrs
  title?: string
  turns: number
  llmCalls: number
  toolCalls: number
  inputTokens: number
  outputTokens: number
  failedTurns: number
  // Outcome of the most recently closed turn; the session span mirrors it.
  lastTurnError?: string
  currentTurn?: string
  idle: boolean
  // Has spans that the last exported copy of the session span does not cover.
  dirty: boolean
}

// Ids of turns, model steps and tools already exported and forgotten. OpenCode
// re-publishes some of them later (session summaries update the user message,
// compaction pruning updates old tool parts); those updates are ignored.
const FINISHED_LIMIT = 20000

type TurnState = {
  id: string
  sessionId: string
  spanId: string
  index: number
  start: number
  lastEnd?: number
  agent?: string
  model?: string
  provider?: string
  // Text parts of the user message (part id -> text), not synthetic ones.
  promptParts: Map<string, string>
  output?: string
  errorType?: string
  errorDetail?: unknown
  aborted?: boolean
  contextOverflow?: boolean
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
  // Saw a step-start or step-finish part, i.e. a real model call. The
  // assistant message OpenCode creates for a subtask command has neither.
  modelStep: boolean
  skipped: boolean
  emitted: boolean
}

type ToolState = {
  callId: string
  sessionId: string
  name: string
  spanId: string
  // Saw a `message.part.updated` tool part. Only these become spans; the
  // `tool.execute.after` hook only adds sizes and content to them.
  partBacked: boolean
  partId?: string
  messageId?: string
  start?: number
  end?: number
  status?: string
  aborted?: boolean
  inputBytes?: number
  outputBytes?: number
  input?: string
  output?: string
  errorDetail?: unknown
  emitted: boolean
}

export const FutureAGITracing: Plugin = async (_ctx, options) => {
  const seam = ((options as any)?.[TEST_SEAM] ?? {}) as { env?: Env; fetch?: typeof fetch; now?: () => number }
  const env: Env = seam.env ?? process.env
  const doFetch = seam.fetch ?? globalThis.fetch
  const now = seam.now ?? Date.now
  const apiKey = env.FI_API_KEY
  const secretKey = env.FI_SECRET_KEY
  const projectName = env.FI_PROJECT_NAME
  if (!apiKey || !secretKey || !projectName) return {}

  const capture = truthy(env.FI_CAPTURE_CONTENT)
  const debug = truthy(env.FI_OTLP_DEBUG)
  const timeoutMs = Number(env.FI_OTLP_TIMEOUT_MS ?? "3000") || 3000
  const endpoint =
    env.FI_OTLP_ENDPOINT || `${(env.FI_BASE_URL || "https://api.futureagi.com").replace(/\/+$/, "")}/tracer/v1/traces`

  const sessions = new Map<string, SessionState>()
  const turns = new Map<string, TurnState>()
  const llms = new Map<string, LlmState>()
  const tools = new Map<string, ToolState>()
  const toolAlias = new Map<string, string>() // tool part id -> call id
  const finished = new Set<string>()
  const forget = (key: string) => {
    finished.add(key)
    // Oldest first: a Set iterates in insertion order.
    for (const old of finished) {
      if (finished.size <= FINISHED_LIMIT) break
      finished.delete(old)
    }
  }
  let buffer: Span[] = []
  let serviceVersion = "unknown"
  let pending: Promise<void> = Promise.resolve()
  const retried = new WeakSet<Span>()

  const log = (message: string) => {
    if (debug) console.error(`[futureagi-otlp] ${message}`)
  }

  // Without content capture the status message is the error type only.
  const errorStatus = (type: string, detail: unknown): Status => ({
    code: 2,
    message: capture && detail !== undefined && detail !== null && detail !== "" ? bounded(detail) : type,
  })

  function session(id: string, info?: any): SessionState {
    let s = sessions.get(id)
    if (!s) {
      const parentSessionId: string | undefined = info?.parentID || undefined
      const parent = parentSessionId ? sessions.get(parentSessionId) : undefined
      const start = info?.time?.created ?? now()
      s = {
        id,
        traceId: parent ? parent.traceId : sha(parentSessionId ?? id).slice(0, 32),
        spanId: spanId(`${id}:session`),
        parentSpanId: parentSessionId ? spanId(`${parentSessionId}:session`) : undefined,
        parentSessionId,
        start,
        end: start,
        attrs: {},
        turns: 0,
        llmCalls: 0,
        toolCalls: 0,
        inputTokens: 0,
        outputTokens: 0,
        failedTurns: 0,
        idle: true,
        dirty: false,
      }
      sessions.set(id, s)
    }
    if (info) {
      if (info.version) serviceVersion = info.version
      // A resumed session can be seen before its info: keep the real creation time.
      if (typeof info.time?.created === "number") s.start = info.time.created
      s.attrs = {
        ...s.attrs,
        "opencode.version": info.version,
        "opencode.session.slug": info.slug,
        "opencode.project.id": info.projectID,
        // The project path contains the OS user name, so it is content.
        "opencode.directory": capture ? info.directory : undefined,
      }
      if (info.title) s.title = info.title
    }
    return s
  }

  function push(s: SessionState, span: Span, end: number) {
    buffer.push(span)
    // Refresh this session span and every one above it (a subagent session's
    // parent is the root of the trace), so a batch never lacks its root.
    let p: SessionState | undefined = s
    for (let depth = 0; p && depth < 16; depth++) {
      p.dirty = true
      p.end = Math.max(p.end, end)
      p = p.parentSessionId ? sessions.get(p.parentSessionId) : undefined
    }
    if (buffer.length >= 128) void flush()
  }

  function emitTool(t: ToolState, final = false) {
    if (t.emitted || !t.partBacked) return
    t.emitted = true
    const s = session(t.sessionId)
    const llm = t.messageId ? llms.get(t.messageId) : undefined
    const turnId = llm?.turnId ?? s.currentTurn
    const turn = turnId ? turns.get(turnId) : undefined
    const parent = (llm?.modelStep ? llm.spanId : undefined) ?? turn?.spanId ?? s.spanId
    const start = t.start ?? now()
    const end = t.end ?? (final ? now() : start)
    const failed = t.status === "error" && !t.aborted
    s.toolCalls += 1
    if (turn) turn.lastEnd = Math.max(turn.lastEnd ?? 0, end)
    push(
      s,
      {
        traceId: s.traceId,
        spanId: t.spanId,
        parentSpanId: parent,
        name: `execute_tool ${t.name}`,
        kind: 1,
        startTimeUnixNano: nanos(start),
        endTimeUnixNano: nanos(Math.max(end, start)),
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
          "opencode.aborted": t.aborted ? true : undefined,
          "opencode.incomplete": t.end === undefined ? true : undefined,
          "input.value": capture ? t.input : undefined,
          "input.mime_type": capture && t.input !== undefined ? "application/json" : undefined,
          "output.value": capture ? t.output : undefined,
          "output.mime_type": capture && t.output !== undefined ? "text/plain" : undefined,
          "error.type": failed ? "ToolError" : undefined,
        }),
        status: failed ? errorStatus("ToolError", t.errorDetail) : { code: 1 },
      },
      end,
    )
  }

  function emitLlm(l: LlmState) {
    if (l.emitted || l.skipped) return
    const info = l.info ?? {}
    const tokens = info.tokens ?? {}
    const cache = tokens.cache ?? {}
    const input = (tokens.input ?? 0) + (cache.read ?? 0) + (cache.write ?? 0)
    const output = (tokens.output ?? 0) + (tokens.reasoning ?? 0)
    // OpenCode's subtask command writes an assistant message without calling a
    // model. It has no step parts and no usage: no model span for it.
    if (!l.modelStep && !info.error && input + output === 0) {
      l.skipped = true
      return
    }
    l.emitted = true
    const s = session(l.sessionId)
    const turn = l.turnId ? turns.get(l.turnId) : undefined
    const hasUsage = info.tokens !== undefined
    const rawError: string | undefined = info.error ? errorName(info.error.name) : undefined
    const aborted = rawError === ABORTED
    const errorType = aborted ? undefined : rawError
    const end = l.end ?? now()
    s.llmCalls += 1
    if (hasUsage) {
      s.inputTokens += input
      s.outputTokens += output
    }
    if (turn) {
      turn.lastEnd = Math.max(turn.lastEnd ?? 0, end)
      if (capture && l.text) turn.output = l.text
      if (aborted) turn.aborted = true
      if (errorType && !turn.errorType) {
        turn.errorType = errorType
        turn.errorDetail = info.error?.data?.message
      }
    }
    push(
      s,
      {
        traceId: s.traceId,
        spanId: l.spanId,
        parentSpanId: turn?.spanId ?? s.spanId,
        name: `chat ${info.modelID ?? "unknown"}`,
        kind: 1,
        startTimeUnixNano: nanos(l.start),
        endTimeUnixNano: nanos(Math.max(end, l.start)),
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
          "opencode.aborted": aborted ? true : undefined,
          "opencode.incomplete": l.end === undefined ? true : undefined,
          "output.value": capture && l.text ? l.text : undefined,
          "output.mime_type": capture && l.text ? "text/plain" : undefined,
          "error.type": errorType,
        }),
        status: errorType ? errorStatus(errorType, info.error?.data?.message) : { code: 1 },
      },
      end,
    )
  }

  function emitTurn(t: TurnState, end: number) {
    if (t.emitted) return
    t.emitted = true
    const s = session(t.sessionId)
    const errorType = t.errorType
    if (errorType) s.failedTurns += 1
    s.lastTurnError = errorType
    const promptText = t.promptParts.size > 0 ? [...t.promptParts.values()].join("\n") : undefined
    const prompt = capture && promptText !== undefined ? bounded(promptText) : undefined
    push(
      s,
      {
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
          "opencode.prompt.bytes": promptText !== undefined ? byteLength(promptText) : undefined,
          "opencode.aborted": t.aborted ? true : undefined,
          "opencode.context_overflow": t.contextOverflow ? true : undefined,
          "input.value": prompt,
          "input.mime_type": prompt ? "text/plain" : undefined,
          "output.value": capture ? t.output : undefined,
          "output.mime_type": capture && t.output ? "text/plain" : undefined,
          "error.type": errorType,
        }),
        status: errorType ? errorStatus(errorType, t.errorDetail) : { code: 1 },
      },
      end,
    )
    if (s.currentTurn === t.id) s.currentTurn = undefined
  }

  // The session span is rebuilt for every export: same span id and start
  // time, cumulative counts, status of the latest closed turn.
  function sessionSpan(s: SessionState): Span {
    const errorType = s.lastTurnError
    return {
      traceId: s.traceId,
      spanId: s.spanId,
      parentSpanId: s.parentSpanId,
      name: "opencode.session",
      kind: 1,
      startTimeUnixNano: nanos(s.start),
      endTimeUnixNano: nanos(Math.max(s.end, s.start)),
      attributes: toAttributes({
        "fi.span.kind": "AGENT",
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "opencode",
        "session.id": s.id,
        "gen_ai.conversation.id": s.id,
        "opencode.session.parent_id": s.parentSessionId,
        "opencode.turn.count": s.turns,
        "opencode.turn.error_count": s.failedTurns,
        "opencode.llm.count": s.llmCalls,
        "opencode.tool.count": s.toolCalls,
        "opencode.usage.input_tokens": s.inputTokens,
        "opencode.usage.output_tokens": s.outputTokens,
        "opencode.session.title": capture && s.title ? bounded(s.title) : undefined,
        "error.type": errorType,
        ...s.attrs,
      }),
      status: errorType ? { code: 2, message: errorType } : { code: 1 },
    }
  }

  const openLlm = (turnId: string) => {
    for (const l of llms.values()) if (l.turnId === turnId && !l.emitted && !l.skipped && l.end === undefined) return true
    return false
  }

  // Close a turn once none of its model steps is still running.
  function closeTurn(t: TurnState, end: number) {
    if (t.emitted || openLlm(t.id)) return
    emitTurn(t, end)
  }

  // Emit every finished child of a session and close its finished turns. With
  // `final`, also close what is still open (OpenCode is shutting down).
  function settle(sessionId: string, final: boolean) {
    const s = sessions.get(sessionId)
    if (!s) return
    for (const t of tools.values()) {
      if (t.sessionId !== sessionId || t.emitted) continue
      if (t.partBacked && (t.end !== undefined || final)) emitTool(t, final)
    }
    for (const l of llms.values()) {
      if (l.sessionId !== sessionId || l.emitted) continue
      if (l.end !== undefined || final) emitLlm(l)
    }
    const t = now()
    for (const turn of turns.values()) {
      if (turn.sessionId !== sessionId || turn.emitted) continue
      if (final) emitTurn(turn, t)
      else closeTurn(turn, t)
    }
    prune(sessionId, final)
  }

  // Forget finished state, or all of it on `final`, and remember the ids so a
  // later re-publish of the same message or part is ignored. Tools seen only
  // through the `tool.execute.after` hook (never as a message part) are dropped.
  function prune(sessionId: string, final: boolean) {
    for (const [id, t] of tools) {
      if (t.sessionId !== sessionId) continue
      if (final || t.emitted || (!t.partBacked && t.end !== undefined)) {
        tools.delete(id)
        if (t.partId) toolAlias.delete(t.partId)
        if (t.partBacked) forget(`tool:${sessionId}:${t.callId}`)
      }
    }
    for (const [id, l] of llms) {
      if (l.sessionId !== sessionId || !(final || l.emitted || l.skipped)) continue
      llms.delete(id)
      forget(`llm:${id}`)
    }
    for (const [id, turn] of turns) {
      if (turn.sessionId !== sessionId || !(final || turn.emitted)) continue
      turns.delete(id)
      forget(`turn:${id}`)
    }
  }

  async function post(spans: Span[]): Promise<boolean> {
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
    try {
      const response = await doFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Api-Key": apiKey!, "X-Secret-Key": secretKey! },
        body,
        signal: AbortSignal.timeout(timeoutMs),
      })
      if (response.ok) return true
      log(`collector returned HTTP ${response.status}`)
    } catch (error) {
      // Never surface payloads or header values; never break the session.
      log(`export failed: ${(error as Error)?.name ?? "Error"}`)
    }
    return false
  }

  // Send buffered spans plus a fresh session span for every session they
  // belong to. A failed batch is retried once with the next flush.
  function flush(): Promise<void> {
    const roots: Span[] = []
    const rooted: SessionState[] = []
    for (const s of sessions.values()) {
      if (!s.dirty) continue
      s.dirty = false
      roots.push(sessionSpan(s))
      rooted.push(s)
    }
    if (buffer.length === 0 && roots.length === 0) return pending
    const spans = buffer
    buffer = []
    pending = pending.then(async () => {
      if (await post([...spans, ...roots])) return
      const again = spans.filter((span) => !retried.has(span))
      for (const span of again) retried.add(span)
      buffer.unshift(...again)
      for (const s of rooted) if (again.some((span) => span.traceId === s.traceId)) s.dirty = true
    })
    return pending
  }

  function onMessage(info: any) {
    if (!info?.id || !info?.sessionID) return
    if (finished.has(`turn:${info.id}`) || finished.has(`llm:${info.id}`)) return
    const s = session(info.sessionID)
    if (info.role === "user") {
      let turn = turns.get(info.id)
      if (!turn) {
        const created = info.time?.created ?? now()
        // A message typed while OpenCode is still working is queued and joins
        // the running loop. The previous turn closes when its last model step
        // ends, not now, so that step keeps its tokens and finish reason.
        const previous = s.currentTurn ? turns.get(s.currentTurn) : undefined
        s.turns += 1
        s.idle = false
        turn = {
          id: info.id,
          sessionId: s.id,
          spanId: spanId(`${info.id}:turn`),
          index: s.turns,
          start: created,
          promptParts: new Map(),
          emitted: false,
        }
        turns.set(info.id, turn)
        s.currentTurn = info.id
        if (previous && !previous.emitted) closeTurn(previous, previous.lastEnd ?? created)
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
        spanId: spanId(`${info.id}:llm`),
        start: info.time?.created ?? now(),
        modelStep: false,
        skipped: false,
        emitted: false,
      }
      llms.set(info.id, l)
    }
    l.info = info
    if ((info.time?.completed || info.error) && l.end === undefined) {
      const end: number = info.time?.completed ?? now()
      l.end = end
      for (const t of tools.values()) if (t.messageId === l.id && t.end !== undefined) emitTool(t)
      emitLlm(l)
      const turn = l.turnId ? turns.get(l.turnId) : undefined
      if (turn && (s.currentTurn !== turn.id || s.idle)) closeTurn(turn, turn.lastEnd ?? end)
    }
  }

  function findTool(callId: string): ToolState | undefined {
    return tools.get(callId) ?? tools.get(toolAlias.get(callId) ?? "")
  }

  function hookTool(callId: string, sessionId: string, name: string): ToolState {
    let t = findTool(callId)
    if (!t) {
      session(sessionId)
      t = { callId, sessionId, name, spanId: spanId(`${sessionId}:${callId}:tool`), partBacked: false, emitted: false }
      tools.set(callId, t)
    }
    return t
  }

  function onPart(part: any) {
    if (!part?.sessionID) return
    if ((part.type === "step-start" || part.type === "step-finish") && part.messageID) {
      const l = llms.get(part.messageID)
      if (l) l.modelStep = true
      return
    }
    if (part.type === "tool" && part.callID) {
      if (finished.has(`tool:${part.sessionID}:${part.callID}`)) return
      let t = tools.get(part.callID)
      // OpenCode's subtask command fires the hooks with the part id as call id.
      const hookOnly = part.id ? tools.get(part.id) : undefined
      if (!t && hookOnly && !hookOnly.partBacked) {
        tools.delete(part.id)
        hookOnly.callId = part.callID
        hookOnly.spanId = spanId(`${part.sessionID}:${part.callID}:tool`)
        t = hookOnly
        tools.set(part.callID, t)
      }
      if (!t) {
        session(part.sessionID)
        t = {
          callId: part.callID,
          sessionId: part.sessionID,
          name: part.tool ?? "unknown",
          spanId: spanId(`${part.sessionID}:${part.callID}:tool`),
          partBacked: true,
          emitted: false,
        }
        tools.set(part.callID, t)
      }
      t.partBacked = true
      t.name = part.tool ?? t.name
      if (part.id) {
        t.partId = part.id
        toolAlias.set(part.id, part.callID)
      }
      t.messageId = part.messageID ?? t.messageId
      const state = part.state ?? {}
      if (state.time?.start) t.start = state.time.start
      // Arguments are known once the tool runs (a pending part has `{}`).
      if (state.status && state.status !== "pending" && state.input !== undefined) {
        t.inputBytes = byteLength(state.input)
        if (capture) t.input = bounded(state.input)
      }
      if (state.status === "completed" || state.status === "error") {
        t.status = state.status
        t.end = state.time?.end ?? now()
        if (state.status === "completed" && t.outputBytes === undefined && state.output !== undefined) {
          t.outputBytes = byteLength(state.output)
          if (capture) t.output = bounded(state.output)
        }
        if (state.status === "error") {
          const error = state.error
          // Tools interrupted by an abort (Esc) are cancelled, not failed.
          t.aborted =
            state.metadata?.interrupted === true || error === "Tool execution aborted" || error === "Cancelled"
          t.outputBytes = byteLength(error)
          t.errorDetail = error
          if (capture) t.output = bounded(error)
        }
        emitTool(t)
      } else if (state.status) {
        t.status = state.status
      }
      return
    }
    if (part.type === "text" && part.messageID && !part.synthetic && typeof part.text === "string") {
      // The prompt: text parts of a user message. Only its size is exported
      // unless content capture is on.
      const turn = turns.get(part.messageID)
      if (turn) {
        if (!turn.emitted) turn.promptParts.set(part.id ?? String(turn.promptParts.size), part.text)
        return
      }
      const l = llms.get(part.messageID)
      if (l && capture) l.text = bounded(part.text)
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
            const turn = s.currentTurn ? turns.get(s.currentTurn) : undefined
            if (!turn) break
            const name = errorName(p.error?.name)
            // An abort is not a failure. A context overflow is recovered by
            // compaction; when it is not, the model step carries the error.
            if (name === ABORTED) turn.aborted = true
            else if (name === CONTEXT_OVERFLOW) turn.contextOverflow = true
            else if (!turn.errorType) {
              turn.errorType = name
              turn.errorDetail = p.error?.data?.message
            }
          }
          break
        case "session.idle":
          if (p.sessionID) {
            const s = sessions.get(p.sessionID)
            if (s) s.idle = true
            settle(p.sessionID, false)
            await flush()
          }
          break
        case "session.deleted":
          if (p.info?.id) {
            settle(p.info.id, true)
            await flush()
            sessions.delete(p.info.id)
          }
          break
      }
    }),
    // Runs after the tool returned; reads its output, never changes it.
    "tool.execute.after": guard(async (input: any, output: any) => {
      if (!input?.callID || !input?.sessionID) return
      if (finished.has(`tool:${input.sessionID}:${input.callID}`)) return
      const t = hookTool(input.callID, input.sessionID, input.tool ?? "unknown")
      if (t.inputBytes === undefined && input.args !== undefined) {
        t.inputBytes = byteLength(input.args)
        if (capture) t.input = bounded(input.args)
      }
      t.outputBytes = byteLength(output?.output)
      if (capture) t.output = bounded(output?.output ?? "")
      t.end = t.end ?? now()
      t.status = t.status ?? "completed"
    }),
    // Final refresh: close what is still open and send it with its session
    // span. Waits at most two export timeouts so OpenCode can exit.
    dispose: guard(async () => {
      for (const id of sessions.keys()) settle(id, true)
      let timer: ReturnType<typeof setTimeout> | undefined
      const deadline = new Promise<void>((resolve) => {
        timer = setTimeout(resolve, 2 * timeoutMs)
        ;(timer as any).unref?.()
      })
      await Promise.race([flush().then(() => flush()), deadline])
      clearTimeout(timer)
    }),
  }
}
