// Contract tests for futureagi-otlp.ts. No network: fetch is injected.
// Run with Node 22.18+ (TypeScript type stripping): node --test futureagi-otlp.test.ts
//
// fixtures/pi-1.2.0-session.jsonl is the event stream of a real `pi -p` run
// (Pi 1.2.0: one prompt, bash + read in parallel, two turns), recorded with a
// throwaway extension. Prompt, answer, tool arguments and tool results were
// replaced with marker strings that also carry a fake API key.

import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import { test } from "node:test"
import { createTracer } from "./futureagi-otlp.ts"

const FIXTURE = readFileSync(new URL("./fixtures/pi-1.2.0-session.jsonl", import.meta.url), "utf8")
  .split("\n")
  .filter(Boolean)
  .map((line) => JSON.parse(line))
const MARKERS = ["FIXTURE-PROMPT-MARKER", "FIXTURE-ANSWER-MARKER", "FIXTURE-ARG-MARKER", "FIXTURE-RESULT-MARKER"]
const SECRET = "sk-fixture0123456789abcdef"
const BASE_ENV = {
  FI_API_KEY: "test-api-key",
  FI_SECRET_KEY: "test-secret-key",
  FI_PROJECT_NAME: "pi-contract",
  FI_OTLP_ENDPOINT: "http://collector.test/v1/traces",
}

type Call = { url: string; init: any; body: any }

function harness(env: Record<string, string> = BASE_ENV, opts: { status?: number; fail?: number } = {}) {
  const handlers = new Map<string, Array<(event: any, ctx: any) => unknown>>()
  const pi: any = {
    on(name: string, handler: (event: any, ctx: any) => unknown) {
      handlers.set(name, [...(handlers.get(name) ?? []), handler])
      return () => {}
    },
  }
  const calls: Call[] = []
  let failures = opts.fail ?? 0
  let clock = 1_800_000_000_000
  const fetch = async (url: string, init: any) => {
    calls.push({ url, init, body: JSON.parse(init.body) })
    if (failures > 0) {
      failures -= 1
      throw new Error(`connect failed ${url} ${init.headers["X-Api-Key"]}`)
    }
    return { ok: (opts.status ?? 200) < 300, status: opts.status ?? 200 } as Response
  }
  const active = createTracer(pi, { env, fetch: fetch as any, now: () => (clock += 5), version: async () => "1.2.0" })
  let ctx: any
  const emit = async (event: any, nextCtx?: any) => {
    if (nextCtx) {
      ctx = {
        cwd: nextCtx.cwd,
        mode: nextCtx.mode,
        sessionManager: {
          getSessionId: () => nextCtx.sessionId,
          getHeader: () => nextCtx.header,
          getSessionName: () => nextCtx.name,
        },
      }
    }
    for (const handler of handlers.get(event.type) ?? []) await handler(event, ctx)
  }
  const spans = () => {
    const byId = new Map<string, any>()
    for (const call of calls) for (const span of call.body.resourceSpans[0].scopeSpans[0].spans) byId.set(span.spanId, span)
    return [...byId.values()]
  }
  return { handlers, calls, emit, spans, active }
}

async function replay(h: ReturnType<typeof harness>, rows = FIXTURE) {
  for (const row of rows) await h.emit(row.event, row.ctx)
}

const attr = (span: any, key: string) => {
  const found = span.attributes.find((a: any) => a.key === key)
  if (!found) return undefined
  const v = found.value
  return v.stringValue ?? (v.intValue !== undefined ? Number(v.intValue) : undefined) ?? v.boolValue ?? v.doubleValue ?? v.arrayValue
}
const byName = (spans: any[], prefix: string) => spans.filter((s) => s.name.startsWith(prefix))

test("real 1.2.0 session becomes one trace: session > prompt > turn > llm/tool", async () => {
  const h = harness()
  await replay(h)
  const spans = h.spans()
  const sessionId = FIXTURE[0].ctx.sessionId
  assert.deepEqual(new Set(spans.map((s) => s.traceId)), new Set([createHash("sha256").update(sessionId).digest("hex").slice(0, 32)]))

  const [root] = byName(spans, "pi.session")
  const [prompt] = byName(spans, "pi.prompt")
  const turns = byName(spans, "pi.turn")
  const llms = byName(spans, "chat ")
  const tools = byName(spans, "execute_tool ")
  assert.equal(root.parentSpanId, undefined)
  assert.equal(attr(root, "fi.span.kind"), "AGENT")
  assert.equal(attr(root, "gen_ai.operation.name"), "invoke_agent")
  assert.equal(attr(root, "session.id"), sessionId)
  assert.equal(attr(root, "pi.version"), "1.2.0")
  assert.equal(prompt.parentSpanId, root.spanId)
  assert.equal(turns.length, 2)
  for (const t of turns) assert.equal(t.parentSpanId, prompt.spanId)
  assert.deepEqual(turns.map((t) => attr(t, "pi.turn.index")).sort(), [0, 1])
  assert.equal(llms.length, 2)
  assert.deepEqual(new Set(llms.map((s) => s.parentSpanId)), new Set(turns.map((t) => t.spanId)))
  assert.deepEqual(tools.map((s) => s.name).sort(), ["execute_tool bash", "execute_tool read"])
  const firstTurn = turns.find((t) => attr(t, "pi.turn.index") === 0)
  for (const tool of tools) {
    assert.equal(tool.parentSpanId, firstTurn.spanId)
    assert.equal(attr(tool, "fi.span.kind"), "TOOL")
    assert.ok(attr(tool, "gen_ai.tool.call.id"))
  }
  const first = llms.find((s) => attr(s, "pi.turn.index") === 0)
  assert.equal(attr(first, "gen_ai.request.model"), "gpt-6-luna")
  assert.equal(attr(first, "gen_ai.provider.name"), "cliproxy")
  assert.equal(attr(first, "gen_ai.usage.input_tokens"), 1497)
  assert.equal(attr(first, "gen_ai.usage.output_tokens"), 82)
  const second = llms.find((s) => attr(s, "pi.turn.index") === 1)
  // Pi reports uncached input separately from cache reads; the span adds them back.
  assert.equal(attr(second, "gen_ai.usage.input_tokens"), 164 + 1536)
  assert.equal(attr(second, "gen_ai.usage.cache_read.input_tokens"), 1536)
  // A model id on a non-LLM span would make Future AGI label it LLM.
  for (const s of [root, prompt, ...turns, ...tools]) assert.equal(attr(s, "gen_ai.request.model"), undefined)
  for (const s of spans) assert.equal(s.status.code, 1)

  const call = h.calls[0]
  assert.equal(call.url, BASE_ENV.FI_OTLP_ENDPOINT)
  assert.equal(call.init.headers["X-Api-Key"], "test-api-key")
  assert.equal(call.init.headers["X-Secret-Key"], "test-secret-key")
  const resource = call.body.resourceSpans[0].resource
  assert.equal(attr(resource, "project_name"), "pi-contract")
  assert.equal(attr(resource, "project_type"), "observe")
  assert.equal(attr(resource, "service.name"), "pi")
})

test("default export drops prompt, answer, tool args and tool results", async () => {
  const h = harness()
  await replay(h)
  const wire = JSON.stringify(h.calls.map((c) => c.body))
  for (const marker of [...MARKERS, SECRET]) assert.ok(!wire.includes(marker), `${marker} leaked`)
  assert.ok(!wire.includes("input.value") && !wire.includes("output.value"))
  const [prompt] = byName(h.spans(), "pi.prompt")
  assert.ok(attr(prompt, "pi.prompt.bytes") > 0)
  const [tool] = byName(h.spans(), "execute_tool read")
  assert.ok(attr(tool, "pi.tool.input.bytes") > 0)
  assert.ok(attr(tool, "pi.tool.output.bytes") > 0)
})

test("FI_CAPTURE_CONTENT=true exports bounded content with secrets redacted", async () => {
  const h = harness({ ...BASE_ENV, FI_CAPTURE_CONTENT: "true" })
  await replay(h)
  const wire = JSON.stringify(h.calls.map((c) => c.body))
  for (const marker of MARKERS) assert.ok(wire.includes(marker), `${marker} missing`)
  assert.ok(!wire.includes(SECRET))
  assert.ok(wire.includes("[REDACTED]"))
  const [root] = byName(h.spans(), "pi.session")
  assert.match(attr(root, "input.value"), /FIXTURE-PROMPT-MARKER/)
  assert.match(attr(root, "output.value"), /FIXTURE-ANSWER-MARKER/)
})

test("content is capped at 4 KiB", async () => {
  const h = harness({ ...BASE_ENV, FI_CAPTURE_CONTENT: "true" })
  const rows = FIXTURE.map((row) =>
    row.event.type === "tool_execution_end" ? { ...row, event: { ...row.event, result: "x".repeat(10_000) } } : row,
  )
  await replay(h, rows)
  for (const tool of byName(h.spans(), "execute_tool ")) {
    assert.equal(attr(tool, "output.value").length, 4096)
    assert.equal(attr(tool, "pi.tool.output.bytes"), 10_000)
  }
})

test("provider error and failed tool are ERROR without error text", async () => {
  const h = harness()
  const rows = FIXTURE.map((row) => {
    const e = row.event
    if (e.type === "message_end" && e.message.role === "assistant" && e.message.stopReason === "stop") {
      return { ...row, event: { ...e, message: { ...e.message, stopReason: "error", errorMessage: "upstream said FIXTURE-ERROR-TEXT" } } }
    }
    if (e.type === "tool_execution_end" && e.toolName === "bash") return { ...row, event: { ...e, isError: true } }
    if (e.type === "turn_end" && e.turnIndex === 1) return { ...row, event: { ...e, outcome: "error" } }
    return row
  })
  await replay(h, rows)
  const spans = h.spans()
  const failed = spans.filter((s) => s.status.code === 2).map((s) => s.name).sort()
  assert.deepEqual(failed, ["chat gpt-6-luna", "execute_tool bash", "pi.prompt", "pi.session", "pi.turn"])
  for (const s of spans.filter((x) => x.status.code === 2)) assert.equal(s.status.message, "error details omitted by default")
  assert.ok(!JSON.stringify(h.calls.map((c) => c.body)).includes("FIXTURE-ERROR-TEXT"))
})

test("retries keep one prompt span and duplicate turn indexes stay distinct", async () => {
  const h = harness()
  const start = FIXTURE.slice(0, 1)
  const turn0 = FIXTURE.filter((r) => ["turn_start", "turn_end"].includes(r.event.type) && r.event.turnIndex === 0)
  await replay(h, [
    ...start,
    { event: { type: "agent_start" } },
    turn0[0],
    turn0[1],
    { event: { type: "agent_end", messages: [] } },
    // automatic retry: Pi starts the loop again and reuses turnIndex 0
    { event: { type: "agent_start" } },
    turn0[0],
    turn0[1],
    { event: { type: "agent_end", messages: [] } },
    { event: { type: "agent_settled", aborted: false } },
    { event: { type: "session_shutdown", reason: "quit" } },
  ])
  const spans = h.spans()
  const prompts = byName(spans, "pi.prompt")
  assert.equal(prompts.length, 1)
  assert.equal(attr(prompts[0], "pi.prompt.attempts"), 2)
  const turns = byName(spans, "pi.turn")
  assert.equal(turns.length, 2)
  assert.deepEqual(turns.map((t) => attr(t, "pi.turn.index")), [0, 0])
  assert.deepEqual(turns.map((t) => attr(t, "pi.turn.seq")).sort(), [1, 2])
  assert.notEqual(turns[0].spanId, turns[1].spanId)
})

test("nested tool calls hang under the calling tool", async () => {
  const h = harness()
  await replay(h, [
    FIXTURE[0],
    { event: { type: "agent_start" } },
    { event: { type: "turn_start", turnIndex: 0, timestamp: 1 } },
    { event: { type: "tool_execution_start", toolCallId: "c1", toolName: "codemode", args: {} } },
    { event: { type: "tool_execution_start", toolCallId: "c1/1", toolName: "read", args: {}, parentToolCallId: "c1" } },
    { event: { type: "tool_execution_end", toolCallId: "c1/1", toolName: "read", result: "", isError: false, parentToolCallId: "c1" } },
    { event: { type: "tool_execution_end", toolCallId: "c1", toolName: "codemode", result: "", isError: false } },
    { event: { type: "turn_end", turnIndex: 0, outcome: "completed" } },
    { event: { type: "agent_settled", aborted: false } },
    { event: { type: "session_shutdown", reason: "quit" } },
  ])
  const spans = h.spans()
  const [outer] = byName(spans, "execute_tool codemode")
  const [inner] = byName(spans, "execute_tool read")
  assert.equal(inner.parentSpanId, outer.spanId)
  assert.equal(attr(inner, "pi.tool.parent_call.id"), "c1")
})

test("shutdown mid-turn closes open spans as incomplete, not as errors", async () => {
  const h = harness()
  await replay(h, [
    FIXTURE[0],
    { event: { type: "agent_start" } },
    { event: { type: "turn_start", turnIndex: 0, timestamp: 1 } },
    { event: { type: "tool_execution_start", toolCallId: "c1", toolName: "bash", args: { command: "sleep 100" } } },
    { event: { type: "session_shutdown", reason: "quit" } },
  ])
  const spans = h.spans()
  for (const name of ["execute_tool bash", "pi.turn", "pi.prompt"]) {
    const [s] = byName(spans, name)
    assert.equal(attr(s, "pi.incomplete"), true, name)
    assert.equal(s.status.code, 1, name)
  }
  assert.equal(byName(spans, "pi.session").length, 1)
})

test("a session with no prompt exports nothing", async () => {
  const h = harness()
  await replay(h, [FIXTURE[0], { event: { type: "session_shutdown", reason: "quit" } }])
  assert.equal(h.calls.length, 0)
})

test("without credentials the extension registers no handlers", async () => {
  const h = harness({ FI_API_KEY: "k", FI_SECRET_KEY: "s" } as any)
  assert.equal(h.active, false)
  assert.equal(h.handlers.size, 0)
})

test("export failures never throw, retry once, and never log payloads", async () => {
  const errors: string[] = []
  const original = console.error
  console.error = (...args: unknown[]) => errors.push(args.join(" "))
  try {
    const h = harness({ ...BASE_ENV, FI_OTLP_DEBUG: "true", FI_CAPTURE_CONTENT: "true" }, { fail: 1 })
    await replay(h)
    const turnSpanIds = h.calls.flatMap((c) =>
      c.body.resourceSpans[0].scopeSpans[0].spans.filter((s: any) => s.name === "pi.turn").map((s: any) => s.spanId),
    )
    // the settle batch failed and was sent again by the shutdown flush
    assert.equal(h.calls.length, 2)
    assert.equal(turnSpanIds.length, 4)
    assert.equal(new Set(turnSpanIds).size, 2)
    assert.ok(errors.length > 0)
    for (const line of errors) {
      assert.ok(!line.includes("collector.test") && !line.includes("test-api-key") && !line.includes("FIXTURE"), line)
    }
  } finally {
    console.error = original
  }
})

test("default endpoint is the Future AGI cloud traces URL", async () => {
  const { FI_OTLP_ENDPOINT, ...env } = BASE_ENV
  const h = harness(env)
  await replay(h)
  assert.equal(h.calls[0].url, "https://api.futureagi.com/tracer/v1/traces")
  const h2 = harness({ ...env, FI_BASE_URL: "https://fi.example.com/" })
  await replay(h2)
  assert.equal(h2.calls[0].url, "https://fi.example.com/tracer/v1/traces")
})

test("a finished turn is exported after a short delay while the run continues", async () => {
  const h = harness()
  const firstTurnEnd = FIXTURE.findIndex((r) => r.event.type === "turn_end")
  await replay(h, FIXTURE.slice(0, firstTurnEnd + 1))
  assert.equal(h.calls.length, 0)
  await new Promise((resolve) => setTimeout(resolve, 2200))
  assert.equal(h.calls.length, 1)
  const names = h.calls[0].body.resourceSpans[0].scopeSpans[0].spans.map((s: any) => s.name).sort()
  assert.deepEqual(names, ["chat gpt-6-luna", "execute_tool bash", "execute_tool read", "pi.session", "pi.turn"])
  await replay(h, FIXTURE.slice(firstTurnEnd + 1))
  // the second turn and the prompt go out together when the run settles
  assert.equal(h.calls.length, 2)
  assert.equal(byName(h.spans(), "pi.prompt").length, 1)
})
