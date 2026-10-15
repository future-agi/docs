// Future AGI tracing extension for Pi (https://pi.dev).
//
// Copy this file to `.pi/extensions/futureagi-otlp.ts` in a project you trust,
// or load it for one run with `pi -e ./futureagi-otlp.ts`. It listens to Pi's
// documented extension events (https://pi.dev/docs/latest/extensions) and
// exports one OTLP trace per Pi session to Future AGI:
//
//   pi.session (AGENT)                 one per Pi session id
//     pi.prompt (CHAIN)                one per agent run (a submitted prompt)
//       pi.turn (CHAIN)                one per Pi turn (model request + its tools)
//         chat <model> (LLM)           the assistant message of that turn
//         execute_tool <tool> (TOOL)   each tool execution in that turn
//
// Default mode exports metadata only: ids, model and provider ids, token
// counts, cost, timings, stop reasons, tool names and byte sizes. Prompt text,
// assistant text, tool arguments, tool results (including a failed tool's
// error text), provider error messages, session names and the working
// directory are dropped unless FI_CAPTURE_CONTENT=true.
//
// The extension only observes. It subscribes to session, agent, turn_start,
// message_end and tool execution events. message_end is the one actionable
// hook among them (a handler may return a replacement message); this
// extension returns nothing from it, so Pi keeps the original. It does not
// subscribe to turn_end (an actionable boundary that makes Pi rebuild the
// session projection every turn), tool_call, tool_result or the provider
// request hooks, and it never reads or writes Pi's session files.
//
// Exports: at most one request is in flight. Pi waits for session_shutdown on
// quit, /new, /resume, /fork and /reload, so the extension stops waiting
// after min(FI_OTLP_TIMEOUT_MS, 3000) ms there and drops what is not sent.
//
// Environment:
//   FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME   required; the extension is inert without them
//   FI_OTLP_ENDPOINT     full traces URL (default: $FI_BASE_URL/tracer/v1/traces)
//   FI_BASE_URL          default https://api.futureagi.com
//   FI_CAPTURE_CONTENT   "true" to export bounded, redacted content (default off)
//   FI_OTLP_TIMEOUT_MS   export timeout (default 10000)
//   FI_OTLP_DEBUG        "true" to print export failures to stderr
//
// This is for the upstream Pi app (`@earendil-works/pi-coding-agent`, binary
// `pi`). Oh My Pi (`omp`) is a different fork with its own hook API.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent"
import { createHash, randomBytes } from "node:crypto"

const SCOPE = { name: "futureagi.pi", version: "1.0.0" }
// Content fields are cut at this many UTF-16 code units (JavaScript string length).
const CONTENT_LIMIT = 4096
const OMITTED = "error details omitted by default"
const TURN_FLUSH_DELAY_MS = 2000
// Pi awaits session_shutdown before it quits or switches sessions.
const SHUTDOWN_BUDGET_MS = 3000
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
type PostResult = "ok" | "failed" | "timeout"

export type TracerDeps = { env?: Env; fetch?: typeof fetch; now?: () => number; version?: () => Promise<string | undefined> }

const truthy = (value: string | undefined) => ["1", "true", "yes", "on"].includes((value ?? "").trim().toLowerCase())
const sha = (value: string) => createHash("sha256").update(value).digest("hex")
const newSpanId = () => randomBytes(8).toString("hex")
const nanos = (ms: number) => `${Math.max(0, Math.round(ms))}000000`

function textOf(value: unknown): string {
  if (value === undefined || value === null) return ""
  if (typeof value === "string") return value
  if (Array.isArray(value)) {
    const parts = value.filter((p: any) => p && p.type === "text" && typeof p.text === "string").map((p: any) => p.text)
    if (parts.length) return parts.join("\n")
  }
  if (typeof value === "object" && Array.isArray((value as any).content)) return textOf((value as any).content)
  return JSON.stringify(value) ?? ""
}

const byteLength = (value: unknown) => {
  if (value === undefined || value === null) return 0
  return Buffer.byteLength(typeof value === "string" ? value : JSON.stringify(value) ?? "", "utf8")
}

// Redacts key-like strings, then cuts to CONTENT_LIMIT characters without
// splitting a surrogate pair.
function clip(value: unknown): { text: string; truncated: boolean } {
  let text = typeof value === "string" ? value : JSON.stringify(value) ?? ""
  for (const [pattern, replacement] of SECRET_PATTERNS) text = text.replace(pattern, replacement)
  if (text.length <= CONTENT_LIMIT) return { text, truncated: false }
  let cut = text.slice(0, CONTENT_LIMIT)
  if (/[\uD800-\uDBFF]$/.test(cut)) cut = cut.slice(0, -1)
  return { text: cut, truncated: true }
}
const bounded = (value: unknown) => clip(value).text

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

type RunState = {
  spanId: string
  index: number
  start: number
  end?: number
  attempts: number
  turns: number
  promptBytes: number
  prompt?: string
  output?: string
  errorType?: string
  aborted?: boolean
}

type TurnState = {
  spanId: string
  index: number
  seq: number
  start: number
  runSpanId: string
  runIndex: number
  // From the stop reason of the turn's assistant message, as Pi computes it.
  outcome?: "completed" | "aborted" | "error"
  last?: number
}

type ToolState = {
  spanId: string
  parentSpanId: string
  name: string
  callId: string
  parentCallId?: string
  start: number
  inputBytes: number
  input?: string
  inputIsJson: boolean
}

async function piVersion(): Promise<string | undefined> {
  try {
    // Resolved by Pi's extension loader; absent outside Pi.
    const mod: any = await import("@earendil-works/pi-coding-agent")
    return typeof mod.VERSION === "string" ? mod.VERSION : undefined
  } catch {
    return undefined
  }
}

export function createTracer(pi: ExtensionAPI, deps: TracerDeps = {}) {
  const env: Env = deps.env ?? process.env
  const doFetch = deps.fetch ?? globalThis.fetch
  const now = deps.now ?? Date.now
  const apiKey = env.FI_API_KEY
  const secretKey = env.FI_SECRET_KEY
  const projectName = env.FI_PROJECT_NAME
  if (!apiKey || !secretKey || !projectName) return false

  const capture = truthy(env.FI_CAPTURE_CONTENT)
  const debug = truthy(env.FI_OTLP_DEBUG)
  const timeoutMs = Number(env.FI_OTLP_TIMEOUT_MS ?? "10000") || 10000
  const shutdownBudgetMs = Math.min(timeoutMs, SHUTDOWN_BUDGET_MS)
  const endpoint =
    env.FI_OTLP_ENDPOINT || `${(env.FI_BASE_URL || "https://api.futureagi.com").replace(/\/+$/, "")}/tracer/v1/traces`
  const log = (message: string) => {
    if (debug) console.error(`[futureagi-otlp] ${message}`)
  }

  // One extension instance serves one Pi session: Pi rebuilds the extension
  // runtime on /new, /resume, /fork and /reload, so counters restart there.
  let sessionId: string | undefined
  let traceId = ""
  let rootSpanId = ""
  let rootStart = 0
  let rootAttrs: Attrs = {}
  let sessionName: string | undefined
  let firstPrompt: string | undefined
  let lastOutput: string | undefined
  let serviceVersion = "unknown"
  let runCount = 0
  let turnSeq = 0
  let llmCount = 0
  let toolCount = 0
  let inputTokens = 0
  let outputTokens = 0
  let cost = 0
  let failedRuns = 0
  let run: RunState | undefined
  let turn: TurnState | undefined
  const tools = new Map<string, ToolState>()
  let buffer: Span[] = []
  const retried = new WeakSet<Span>()
  let shutDown = false
  let flushTimer: ReturnType<typeof setTimeout> | undefined
  // Export state: at most one request in flight. A flush requested meanwhile
  // only sets `dirty`; one follow-up export runs when the request finishes.
  let inFlight: Promise<void> | undefined
  let dirty = false
  let lastResult: PostResult = "ok"
  // Aborted at the shutdown deadline; cancels whatever request is in flight.
  const stop = new AbortController()

  const common = (): Attrs => ({ "session.id": sessionId, "gen_ai.conversation.id": sessionId })

  function push(span: Omit<Span, "traceId" | "kind">) {
    buffer.push({ traceId, kind: 1, ...span })
  }

  function rootSpan(end: number): Span {
    return {
      traceId,
      spanId: rootSpanId,
      name: "pi.session",
      kind: 1,
      startTimeUnixNano: nanos(rootStart),
      endTimeUnixNano: nanos(Math.max(end, rootStart)),
      attributes: toAttributes({
        "fi.span.kind": "AGENT",
        "gen_ai.span.kind": "AGENT",
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "pi",
        ...common(),
        ...rootAttrs,
        "pi.prompt.count": runCount,
        "pi.turn.count": turnSeq,
        "pi.llm.count": llmCount,
        "pi.tool.count": toolCount,
        "pi.usage.input_tokens": inputTokens,
        "pi.usage.output_tokens": outputTokens,
        "pi.usage.cost": cost > 0 ? cost : undefined,
        "pi.session.name": capture && sessionName ? bounded(sessionName) : undefined,
        "input.value": capture ? firstPrompt : undefined,
        "input.mime_type": capture && firstPrompt ? "text/plain" : undefined,
        "output.value": capture ? lastOutput : undefined,
        "output.mime_type": capture && lastOutput ? "text/plain" : undefined,
        "error.type": failedRuns > 0 ? "PromptError" : undefined,
      }),
      status: failedRuns > 0 ? { code: 2, message: OMITTED } : { code: 1 },
    }
  }

  function promptSpan(r: RunState, end: number, aborted: boolean, incomplete: boolean): Span {
    return {
      traceId,
      kind: 1,
      spanId: r.spanId,
      parentSpanId: rootSpanId,
      name: "pi.prompt",
      startTimeUnixNano: nanos(r.start),
      endTimeUnixNano: nanos(Math.max(end, r.start)),
      attributes: toAttributes({
        "fi.span.kind": "CHAIN",
        "gen_ai.span.kind": "CHAIN",
        ...common(),
        "pi.prompt.index": r.index,
        "pi.prompt.attempts": r.attempts,
        "pi.prompt.turns": r.turns,
        "pi.prompt.bytes": r.promptBytes,
        "pi.prompt.aborted": aborted || undefined,
        "pi.incomplete": incomplete || undefined,
        "input.value": capture ? r.prompt : undefined,
        "input.mime_type": capture && r.prompt ? "text/plain" : undefined,
        "output.value": capture ? r.output : undefined,
        "output.mime_type": capture && r.output ? "text/plain" : undefined,
        "error.type": r.errorType,
      }),
      status: r.errorType ? { code: 2, message: OMITTED } : { code: 1 },
    }
  }

  function turnSpan(t: TurnState, end: number, incomplete: boolean): Span {
    const failed = t.outcome === "error"
    return {
      traceId,
      kind: 1,
      spanId: t.spanId,
      parentSpanId: t.runSpanId,
      name: "pi.turn",
      startTimeUnixNano: nanos(t.start),
      endTimeUnixNano: nanos(Math.max(end, t.start)),
      attributes: toAttributes({
        "fi.span.kind": "CHAIN",
        "gen_ai.span.kind": "CHAIN",
        ...common(),
        "pi.turn.index": t.index,
        "pi.turn.seq": t.seq,
        "pi.prompt.index": t.runIndex,
        "pi.turn.outcome": t.outcome,
        "pi.incomplete": incomplete || t.outcome === "aborted" || undefined,
        "error.type": failed ? "TurnError" : undefined,
      }),
      status: failed ? { code: 2, message: OMITTED } : { code: 1 },
    }
  }

  async function post(spans: Span[]): Promise<PostResult> {
    const body = {
      resourceSpans: [
        {
          resource: {
            attributes: toAttributes({
              "service.name": "pi",
              "service.version": serviceVersion,
              project_name: projectName,
              project_type: "observe",
            }),
          },
          scopeSpans: [{ scope: SCOPE, spans }],
        },
      ],
    }
    const controller = new AbortController()
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)
    const onStop = () => controller.abort()
    stop.signal.addEventListener("abort", onStop, { once: true })
    if (stop.signal.aborted) controller.abort()
    // Settles on abort even if a fetch implementation ignores the signal.
    let onAbort = () => {}
    const aborted = new Promise<never>((_, reject) => {
      onAbort = () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))
    })
    aborted.catch(() => {})
    controller.signal.addEventListener("abort", onAbort, { once: true })
    if (controller.signal.aborted) onAbort()
    try {
      const request = Promise.resolve().then(() =>
        doFetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Api-Key": apiKey!, "X-Secret-Key": secretKey! },
          body: JSON.stringify(body),
          signal: controller.signal,
        }),
      )
      request.catch(() => {})
      const response = await Promise.race([request, aborted])
      if (!response.ok) {
        log(`collector returned HTTP ${response.status}`)
        return "failed"
      }
      return "ok"
    } catch (error) {
      // Never echo URLs, headers or payloads: they can hold credentials or content.
      log(`export failed: ${(error as Error)?.name ?? "Error"}`)
      return timedOut || stop.signal.aborted ? "timeout" : "failed"
    } finally {
      clearTimeout(timer)
      stop.signal.removeEventListener("abort", onStop)
      controller.signal.removeEventListener("abort", onAbort)
    }
  }

  // Sends the buffered spans plus fresh copies of the open spans: the session,
  // and the running prompt and turn if any (same ids and start times, marked
  // pi.incomplete, so their finished turns and calls always have a parent; the
  // latest copy wins). A failed batch is retried once with a later export.
  function exportNow(): Promise<void> {
    const spans = buffer
    buffer = []
    dirty = false
    const t = now()
    const open: Span[] = []
    if (run) open.push(promptSpan(run, t, run.aborted === true, true))
    if (turn) open.push(turnSpan(turn, t, true))
    const task = (async () => {
      const result = await post([...spans, ...open, rootSpan(t)])
      lastResult = result
      if (result !== "ok") {
        const again = spans.filter((s) => !retried.has(s))
        again.forEach((s) => retried.add(s))
        buffer.unshift(...again)
      }
    })()
    inFlight = task
    void task.then(() => {
      if (inFlight === task) inFlight = undefined
      if (dirty && !shutDown) void flush()
    })
    return task
  }

  function flush(): Promise<void> {
    if (flushTimer) clearTimeout(flushTimer)
    flushTimer = undefined
    // A session with no prompt (Pi opened and closed) exports nothing.
    if (!sessionId || runCount === 0 || buffer.length === 0) return inFlight ?? Promise.resolve()
    if (inFlight) {
      dirty = true
      return inFlight
    }
    return exportNow()
  }

  // Export finished turns of a long run without waiting for it to settle, but
  // coalesce with the settle flush when the run ends right after.
  function scheduleFlush() {
    if (flushTimer || shutDown) return
    flushTimer = setTimeout(() => void flush(), TURN_FLUSH_DELAY_MS)
    flushTimer.unref?.()
  }

  function startRun() {
    runCount += 1
    run = { spanId: newSpanId(), index: runCount, start: now(), attempts: 1, turns: 0, promptBytes: 0 }
  }

  // A turn ends at its last event (assistant message or tool end). Pi does not
  // need a turn_end handler for that: the next turn_start, agent_end,
  // agent_settled or session_shutdown closes it.
  function closeTurn(end: number, incomplete = false) {
    if (!turn) return
    const t = turn
    turn = undefined
    const unfinished = incomplete || t.outcome === undefined
    buffer.push(turnSpan(t, unfinished ? end : (t.last ?? end), unfinished))
    if (!shutDown) scheduleFlush()
  }

  function closeRun(end: number, aborted: boolean, incomplete = false) {
    if (!run) return
    const r = run
    run = undefined
    // Cancelling is not a failure: only a provider error ends a prompt in ERROR.
    if (r.errorType) failedRuns += 1
    if (capture && r.output) lastOutput = r.output
    buffer.push(promptSpan(r, r.end ?? end, aborted || r.aborted === true, incomplete))
  }

  function toolSpan(t: ToolState, end: number, result: unknown, isError: boolean, incomplete = false) {
    const output = result === undefined ? undefined : textOf(result)
    push({
      spanId: t.spanId,
      parentSpanId: t.parentSpanId,
      name: `execute_tool ${t.name}`,
      startTimeUnixNano: nanos(t.start),
      endTimeUnixNano: nanos(Math.max(end, t.start)),
      attributes: toAttributes({
        "fi.span.kind": "TOOL",
        "gen_ai.span.kind": "TOOL",
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": t.name,
        "gen_ai.tool.call.id": t.callId,
        ...common(),
        "pi.tool.parent_call.id": t.parentCallId,
        "pi.tool.input.bytes": t.inputBytes,
        "pi.tool.output.bytes": output === undefined ? undefined : byteLength(output),
        "pi.incomplete": incomplete || undefined,
        "input.value": capture ? t.input : undefined,
        "input.mime_type": capture && t.input ? (t.inputIsJson ? "application/json" : "text/plain") : undefined,
        // A failed tool's result is its error text: content, so opt-in only.
        "output.value": capture && output ? bounded(output) : undefined,
        "output.mime_type": capture && output ? "text/plain" : undefined,
        "error.type": isError ? "ToolError" : undefined,
      }),
      status: isError ? { code: 2, message: OMITTED } : { code: 1 },
    })
  }

  pi.on("session_start", async (event, ctx) => {
    try {
      sessionId = ctx.sessionManager.getSessionId()
    } catch {
      sessionId = undefined
    }
    if (!sessionId) return
    traceId = sha(sessionId).slice(0, 32)
    rootSpanId = sha(`${sessionId}:pi.session`).slice(0, 16)
    let header: any
    try {
      header = ctx.sessionManager.getHeader()
    } catch {
      header = undefined
    }
    const created = header?.timestamp ? Date.parse(header.timestamp) : NaN
    rootStart = Number.isFinite(created) ? created : now()
    try {
      sessionName = ctx.sessionManager.getSessionName() ?? undefined
    } catch {
      sessionName = undefined
    }
    rootAttrs = {
      "pi.session.start_reason": event.reason,
      "pi.session.parent": header?.parentSession ? "true" : undefined,
      // The working directory contains the OS user name, so it is content.
      "pi.cwd": capture ? ctx.cwd : undefined,
      "pi.mode": ctx.mode,
    }
    serviceVersion = (await (deps.version ?? piVersion)()) ?? "unknown"
    rootAttrs["pi.version"] = serviceVersion
  })

  pi.on("session_info_changed", async (event) => {
    sessionName = event.name
  })

  pi.on("agent_start", async () => {
    if (!sessionId) return
    // Pi can restart the loop (automatic retry, compaction recovery, queued
    // messages) before the run settles; keep that inside the same prompt span.
    if (run) {
      run.attempts += 1
      run.end = undefined
      return
    }
    startRun()
  })

  pi.on("turn_start", async (event) => {
    if (!sessionId) return
    if (!run) startRun()
    closeTurn(now())
    turnSeq += 1
    run!.turns += 1
    turn = {
      spanId: newSpanId(),
      index: event.turnIndex,
      seq: turnSeq,
      start: typeof event.timestamp === "number" ? event.timestamp : now(),
      runSpanId: run!.spanId,
      runIndex: run!.index,
    }
  })

  pi.on("message_end", async (event) => {
    if (!sessionId || !run) return
    const message: any = event.message
    if (turn) turn.last = now()
    if (message?.role === "user") {
      const text = textOf(message.content)
      run.promptBytes += byteLength(text)
      // The prompt span shows the message that started the run; steering and
      // follow-up messages still count in pi.prompt.bytes.
      if (capture && run.prompt === undefined) {
        run.prompt = bounded(text)
        if (firstPrompt === undefined) firstPrompt = run.prompt
      }
      return
    }
    if (message?.role !== "assistant") return
    const usage = message.usage ?? {}
    const cacheRead = Number(usage.cacheRead ?? 0)
    const cacheWrite = Number(usage.cacheWrite ?? 0)
    const input = Number(usage.input ?? 0) + cacheRead + cacheWrite
    const output = Number(usage.output ?? 0)
    const callCost = Number(usage.cost?.total ?? 0)
    const start = typeof message.timestamp === "number" ? message.timestamp : now()
    const end = typeof message.durationMs === "number" ? start + message.durationMs : now()
    const stop: string | undefined = message.stopReason
    const failed = stop === "error"
    const aborted = stop === "aborted"
    const text = (message.content ?? [])
      .filter((p: any) => p?.type === "text")
      .map((p: any) => p.text)
      .join("\n")
    const toolCalls = (message.content ?? []).filter((p: any) => p?.type === "toolCall").length
    llmCount += 1
    inputTokens += input
    outputTokens += output
    if (callCost > 0) cost += callCost
    // Same mapping Pi uses for a turn's outcome.
    if (turn) turn.outcome = failed ? "error" : aborted ? "aborted" : "completed"
    // The latest attempt decides the prompt's status.
    run.errorType = failed ? "ProviderError" : undefined
    if (aborted) run.aborted = true
    if (!failed && !aborted && text && capture) run.output = bounded(text)
    const errorText = typeof message.errorMessage === "string" ? message.errorMessage : undefined
    push({
      spanId: newSpanId(),
      parentSpanId: turn?.spanId ?? run.spanId,
      name: `chat ${message.model ?? "unknown"}`,
      startTimeUnixNano: nanos(start),
      endTimeUnixNano: nanos(Math.max(end, start)),
      attributes: toAttributes({
        "fi.span.kind": "LLM",
        "gen_ai.span.kind": "LLM",
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": message.model,
        "gen_ai.response.model": message.responseModel ?? message.model,
        "gen_ai.provider.name": message.provider,
        "gen_ai.response.id": message.responseId,
        "gen_ai.usage.input_tokens": input,
        "gen_ai.usage.output_tokens": output,
        "gen_ai.usage.total_tokens": input + output,
        "gen_ai.usage.cache_read.input_tokens": cacheRead || undefined,
        "gen_ai.usage.cache_creation.input_tokens": cacheWrite || undefined,
        "gen_ai.response.finish_reasons": stop ? [stop] : undefined,
        ...common(),
        "pi.api": message.api,
        "pi.usage.reasoning_tokens": usage.reasoning,
        "pi.usage.cost": callCost > 0 ? callCost : undefined,
        "pi.thinking_level": message.thinkingLevel,
        "pi.llm.tool_calls": toolCalls || undefined,
        "pi.response.bytes": byteLength(text),
        "pi.turn.index": turn?.index,
        "pi.incomplete": aborted || undefined,
        "output.value": capture && text ? bounded(text) : undefined,
        "output.mime_type": capture && text ? "text/plain" : undefined,
        "error.type": failed ? "ProviderError" : undefined,
      }),
      // Provider error bodies can carry paths and account names: opt-in only.
      status: failed ? { code: 2, message: capture && errorText ? bounded(errorText) : OMITTED } : { code: 1 },
    })
  })

  pi.on("tool_execution_start", async (event) => {
    if (!sessionId) return
    const parentTool = event.parentToolCallId ? tools.get(event.parentToolCallId) : undefined
    const input = capture ? clip(event.args) : undefined
    tools.set(event.toolCallId, {
      spanId: newSpanId(),
      parentSpanId: parentTool?.spanId ?? turn?.spanId ?? run?.spanId ?? rootSpanId,
      name: event.toolName,
      callId: event.toolCallId,
      parentCallId: event.parentToolCallId,
      start: now(),
      inputBytes: byteLength(event.args),
      input: input?.text,
      // Truncated JSON is no longer JSON.
      inputIsJson: typeof event.args !== "string" && input?.truncated !== true,
    })
    toolCount += 1
  })

  pi.on("tool_execution_end", async (event) => {
    const t = tools.get(event.toolCallId)
    if (!sessionId || !t) return
    tools.delete(event.toolCallId)
    const end = now()
    if (turn) turn.last = end
    if (typeof event.durationMs === "number") t.start = Math.min(t.start, end - event.durationMs)
    toolSpan(t, end, event.result, event.isError === true)
  })

  pi.on("agent_end", async () => {
    if (!sessionId) return
    closeTurn(now())
    if (run) run.end = now()
  })

  pi.on("agent_settled", async (event) => {
    if (!sessionId) return
    closeTurn(now())
    closeRun(now(), event.aborted === true)
    void flush()
  })

  pi.on("session_shutdown", async () => {
    if (!sessionId || shutDown) return
    shutDown = true
    if (flushTimer) clearTimeout(flushTimer)
    flushTimer = undefined
    const end = now()
    for (const t of tools.values()) toolSpan(t, end, undefined, false, true)
    tools.clear()
    closeTurn(end, true)
    closeRun(end, false, true)
    // Hard deadline: abort the request in flight and send nothing after it.
    let expired = false
    const deadline = setTimeout(() => {
      expired = true
      stop.abort()
    }, shutdownBudgetMs)
    const timeUp = new Promise<void>((resolve) => stop.signal.addEventListener("abort", () => resolve(), { once: true }))
    try {
      if (inFlight) await Promise.race([inFlight, timeUp])
      // Final export, then one retry if it failed fast (never after a timeout).
      for (let attempt = 0; attempt < 2; attempt++) {
        if (expired || runCount === 0 || buffer.length === 0) break
        if (attempt > 0 && lastResult === "timeout") break
        await Promise.race([exportNow(), timeUp])
      }
    } finally {
      clearTimeout(deadline)
    }
  })

  return true
}

export default function futureAgiTracing(pi: ExtensionAPI) {
  createTracer(pi)
}
