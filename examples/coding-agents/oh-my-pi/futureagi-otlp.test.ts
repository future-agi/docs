// Contract tests for the Oh My Pi tracing hook. No network: fetch is injected.
// Run: node --test futureagi-otlp.test.ts   (Node 22.18+ strips the TypeScript types)

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"
import { createFutureAGIHook } from "./futureagi-otlp.ts"

const fixture = JSON.parse(readFileSync(new URL("./fixtures/omp-18.11.0-print-session.json", import.meta.url), "utf8"))
const ENV = {
  FI_API_KEY: "test-api-key",
  FI_SECRET_KEY: "test-secret-key",
  FI_PROJECT_NAME: "omp-contract",
  FI_OTLP_ENDPOINT: "http://collector.test/v1/traces",
}

type Captured = { url: string; headers: Record<string, string>; body: any }

function harness(
  env: Record<string, string> = ENV,
  fetchImpl?: (url: string, init: any) => Promise<any>,
  baseCtx: Record<string, unknown> = fixture.ctx,
) {
  const handlers = new Map<string, Array<(event: any, ctx: any) => unknown>>()
  const pi = { on: (name: string, fn: any) => handlers.set(name, [...(handlers.get(name) ?? []), fn]) }
  const requests: Captured[] = []
  const fetch = async (url: string, init: any) => {
    requests.push({ url, headers: init.headers, body: JSON.parse(init.body) })
    return fetchImpl ? fetchImpl(url, init) : { ok: true, status: 200 }
  }
  let clock = 1_792_031_900_000
  createFutureAGIHook({ env, fetch: fetch as any, now: () => (clock += 5) })(pi as any)
  const returns: unknown[] = []
  async function emit(event: any, sessionId: string | undefined = fixture.sessionId) {
    const ctx = { ...baseCtx, sessionManager: { getSessionId: () => sessionId } }
    for (const fn of handlers.get(event.type) ?? []) returns.push(await fn(event, ctx))
  }
  async function replay(events: any[] = fixture.events, sessionId?: string) {
    for (const event of events) await emit(event, sessionId)
  }
  const spans = () => {
    // Latest export of a span id wins, like the collector's ReplacingMergeTree.
    const byId = new Map<string, any>()
    for (const r of requests) for (const s of r.body.resourceSpans[0].scopeSpans[0].spans) byId.set(s.spanId, s)
    return [...byId.values()]
  }
  return { handlers, requests, returns, emit, replay, spans }
}

const attr = (span: any, key: string) => {
  const found = span.attributes.find((a: any) => a.key === key)
  if (!found) return undefined
  const v = found.value
  return v.stringValue ?? (v.intValue !== undefined ? Number(v.intValue) : (v.doubleValue ?? v.boolValue ?? v.arrayValue))
}
const byName = (spans: any[], name: string) => spans.filter((s) => s.name === name)

test("default export: one trace, session > prompt > turn > llm/tool, no content", async () => {
  const h = harness()
  await h.replay()
  const spans = h.spans()
  assert.deepEqual(
    spans.map((s) => s.name).sort(),
    ["chat gpt-6-luna", "chat gpt-6-luna", "execute_tool glob", "execute_tool read", "omp.prompt", "omp.session", "omp.turn", "omp.turn"].sort(),
  )
  assert.equal(new Set(spans.map((s) => s.traceId)).size, 1)
  const [root] = byName(spans, "omp.session")
  const [prompt] = byName(spans, "omp.prompt")
  const turns = byName(spans, "omp.turn")
  assert.equal(root.parentSpanId, undefined)
  assert.equal(prompt.parentSpanId, root.spanId)
  for (const t of turns) assert.equal(t.parentSpanId, prompt.spanId)
  const firstTurn = turns.find((t) => attr(t, "omp.turn.index") === 0)
  for (const s of [...byName(spans, "execute_tool glob"), ...byName(spans, "execute_tool read")]) {
    assert.equal(s.parentSpanId, firstTurn.spanId)
    assert.equal(attr(s, "fi.span.kind"), "TOOL")
    assert.equal(attr(s, "gen_ai.operation.name"), "execute_tool")
    assert.equal(s.status.code, 1)
  }
  for (const s of spans) {
    assert.equal(attr(s, "session.id"), fixture.sessionId)
    assert.ok(attr(s, "fi.span.kind"))
  }
  assert.equal(attr(root, "fi.span.kind"), "AGENT")
  assert.equal(attr(root, "gen_ai.agent.name"), "oh-my-pi")
  assert.equal(attr(root, "omp.tool.count"), 2)
  assert.equal(attr(root, "omp.session.open"), undefined, "final root replaces the open snapshot")
  // The backend labels any span with a request model as LLM: keep models off non-LLM spans.
  for (const s of [root, prompt, ...turns]) assert.equal(attr(s, "gen_ai.request.model"), undefined)

  const body = JSON.stringify(h.requests.map((r) => r.body))
  assert.ok(!body.includes("FIXTURE-SECRET"), "no prompt, answer, thinking, tool args, intents or results by default")
  assert.ok(!body.includes("input.value") && !body.includes("output.value"))
  assert.ok(!body.includes("sk-fixture"))
  // No local paths (they carry the OS user name).
  assert.ok(!body.includes("/tmp/omp-fixture-project"), "the working directory leaked into the default export")
  assert.ok(!body.includes("omp.cwd"))
})

test("LLM spans carry model, provider, tokens (cache reads counted in input) and omp's cost", async () => {
  const h = harness()
  await h.replay()
  const llms = byName(h.spans(), "chat gpt-6-luna")
  const second = llms.find((s) => attr(s, "gen_ai.response.finish_reasons")?.values?.[0]?.stringValue === "stop")
  assert.equal(attr(second, "fi.span.kind"), "LLM")
  assert.equal(attr(second, "gen_ai.request.model"), "gpt-6-luna")
  assert.equal(attr(second, "gen_ai.provider.name"), "my-gateway")
  assert.equal(attr(second, "gen_ai.usage.input_tokens"), 1058 + 5632)
  assert.equal(attr(second, "gen_ai.usage.output_tokens"), 37)
  assert.equal(attr(second, "gen_ai.usage.cache_read.input_tokens"), 5632)
  assert.equal(attr(second, "gen_ai.cost.total"), 0.00018062)
  assert.equal(second.startTimeUnixNano, "1792031990860000000")
  assert.equal(second.endTimeUnixNano, "1792032007044000000")
  const first = llms.find((s) => s !== second)
  assert.equal(attr(first, "omp.usage.reasoning_tokens"), 42)
})

test("FI_CAPTURE_CONTENT=true exports bounded content and redacts obvious secrets", async () => {
  const h = harness({ ...ENV, FI_CAPTURE_CONTENT: "true" })
  await h.replay()
  const spans = h.spans()
  const [prompt] = byName(spans, "omp.prompt")
  assert.match(attr(prompt, "input.value"), /FIXTURE-SECRET-PROMPT/)
  const [root] = byName(spans, "omp.session")
  assert.match(attr(root, "input.value"), /FIXTURE-SECRET-PROMPT/, "trace list shows the first prompt")
  assert.match(attr(root, "output.value"), /FIXTURE-SECRET-ANSWER/, "trace list shows the last answer")
  assert.match(attr(prompt, "output.value"), /FIXTURE-SECRET-ANSWER/)
  const [read] = byName(spans, "execute_tool read")
  assert.match(attr(read, "input.value"), /FIXTURE-SECRET-TOOL-ARG/)
  assert.match(attr(read, "output.value"), /FIXTURE-SECRET-TOOL-RESULT/)
  assert.match(attr(read, "omp.tool.intent"), /FIXTURE-SECRET-INTENT/)
  assert.equal(attr(root, "omp.cwd"), "/tmp/omp-fixture-project")
  const body = JSON.stringify(h.requests.map((r) => r.body))
  assert.ok(!body.includes("sk-fixturefixturefixture123"), "API-key-shaped strings are redacted")
  assert.ok(!body.includes("FIXTURE-SECRET-THINKING"), "thinking blocks are never exported")
  assert.ok(!body.includes("FIXTURE-SECRET-SYSTEM"), "the system prompt is never exported")
})

test("content is capped at 4096 characters per attribute", async () => {
  const h = harness({ ...ENV, FI_CAPTURE_CONTENT: "true" })
  const big = "x".repeat(10_000)
  const events = fixture.events.map((e: any) => {
    if (e.type === "tool_execution_start" && e.toolName === "read") return { ...e, args: { path: "README.md", note: big } }
    if (e.type === "tool_execution_end" && e.toolName === "read") return { ...e, result: { content: [{ type: "text", text: big }] } }
    return e
  })
  await h.replay(events)
  const [read] = byName(h.spans(), "execute_tool read")
  assert.equal(attr(read, "output.value").length, 4096)
  assert.equal(attr(read, "omp.tool.output.bytes"), 10_000)
  assert.equal(attr(read, "input.value").length, 4096)
  assert.equal(attr(read, "input.mime_type"), "text/plain", "cut-off JSON is not labelled as JSON")
  const [glob] = byName(h.spans(), "execute_tool glob")
  assert.equal(attr(glob, "input.mime_type"), "application/json")
})

test("with content on, JSON-shaped api keys in tool arguments are redacted", async () => {
  const h = harness({ ...ENV, FI_CAPTURE_CONTENT: "true" })
  const events = fixture.events.map((e: any) =>
    e.type === "tool_execution_start" && e.toolName === "read"
      ? { ...e, args: { path: "README.md", api_key: "abc123def456ghi", headers: { "x-api-key": "jkl789mno012pqr" } } }
      : e,
  )
  await h.replay(events)
  const [read] = byName(h.spans(), "execute_tool read")
  const input = attr(read, "input.value")
  assert.ok(!input.includes("abc123def456ghi") && !input.includes("jkl789mno012pqr"), input)
  assert.match(input, /"api_key":"\[REDACTED\]"/)
  assert.match(input, /"path":"README.md"/)
})

test("the hook only observes: it never registers gate events and every handler returns undefined", async () => {
  const h = harness()
  for (const gate of ["tool_call", "tool_result", "context", "input", "before_agent_start", "before_provider_request", "user_bash", "user_python", "session_stop"]) {
    assert.equal(h.handlers.has(gate), false, `${gate} must not be handled`)
  }
  await h.replay()
  assert.ok(h.returns.length > 0)
  assert.ok(h.returns.every((r) => r === undefined))
})

test("tool and provider failures are ERROR without their messages by default", async () => {
  const h = harness()
  const events = fixture.events.map((e: any) => {
    if (e.type === "tool_execution_end" && e.toolName === "read") return { ...e, isError: true, result: { content: [{ type: "text", text: "FIXTURE-SECRET-ERROR ENOENT" }] } }
    if (e.type === "message_end" && e.message.stopReason === "stop")
      return { ...e, message: { ...e.message, stopReason: "error", errorStatus: 400, errorMessage: "FIXTURE-SECRET-ERROR provider said no", content: [] } }
    return e
  })
  await h.replay(events)
  const spans = h.spans()
  const [read] = byName(spans, "execute_tool read")
  assert.equal(read.status.code, 2)
  assert.equal(read.status.message, "error details omitted by default")
  assert.equal(attr(read, "error.type"), "ToolError")
  const failed = byName(spans, "chat gpt-6-luna").find((s) => s.status.code === 2)
  assert.ok(failed)
  assert.equal(attr(failed, "error.type"), "ProviderError")
  assert.equal(attr(failed, "omp.error.http_status"), 400)
  assert.equal(byName(spans, "omp.prompt")[0].status.code, 2)
  assert.equal(byName(spans, "omp.session")[0].status.code, 1, "a failed prompt does not fail the session")
  assert.equal(attr(byName(spans, "omp.session")[0], "omp.tool.error.count"), 1)
  assert.ok(!JSON.stringify(h.requests.map((r) => r.body)).includes("FIXTURE-SECRET-ERROR"))

  const withContent = harness({ ...ENV, FI_CAPTURE_CONTENT: "true" })
  await withContent.replay(events)
  const spansC = withContent.spans()
  const [readC] = byName(spansC, "execute_tool read")
  assert.match(readC.status.message, /FIXTURE-SECRET-ERROR ENOENT/)
  // With content on, only the tool and model spans carry the error text; the turn and
  // prompt spans keep the fixed message (the page says so).
  const failedC = byName(spansC, "chat gpt-6-luna").find((s) => s.status.code === 2)
  assert.match(failedC.status.message, /FIXTURE-SECRET-ERROR provider said no/)
  const failedTurns = byName(spansC, "omp.turn").filter((s) => s.status.code === 2)
  assert.equal(failedTurns.length, 1)
  const [promptC] = byName(spansC, "omp.prompt")
  for (const s of [...failedTurns, promptC]) {
    assert.deepEqual([s.status.code, s.status.message, attr(s, "error.type")], [2, "error details omitted by default", "ProviderError"])
  }
})

test("omp's own OTEL_* switches and endpoints do not change what the hook sends", async () => {
  // The page tells users to turn omp's built-in export off with these; the hook must keep working.
  const otel = {
    OTEL_SDK_DISABLED: "true",
    OTEL_TRACES_EXPORTER: "none",
    OTEL_LOGS_EXPORTER: "none",
    OTEL_METRICS_EXPORTER: "none",
    OTEL_EXPORTER_OTLP_ENDPOINT: "http://other-collector.test",
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: "http://other-collector.test/v1/traces",
    OTEL_EXPORTER_OTLP_HEADERS: "X-Api-Key=other-key,X-Secret-Key=other-secret",
    OTEL_RESOURCE_ATTRIBUTES: "project_name=other-project",
  }
  const plain = harness()
  await plain.replay()
  const h = harness({ ...ENV, ...otel })
  await h.replay()
  assert.ok(h.requests.length > 0)
  assert.equal(h.requests.length, plain.requests.length)
  for (const r of h.requests) {
    assert.equal(r.url, "http://collector.test/v1/traces")
    assert.equal(r.headers["X-Api-Key"], "test-api-key")
    assert.equal(r.headers["X-Secret-Key"], "test-secret-key")
    const resource = Object.fromEntries(r.body.resourceSpans[0].resource.attributes.map((a: any) => [a.key, a.value.stringValue]))
    assert.equal(resource.project_name, "omp-contract")
  }
  assert.deepEqual(h.spans().map((s) => s.name).sort(), plain.spans().map((s) => s.name).sort())
  assert.ok(!JSON.stringify(h.requests).includes("other-"))
})

test("shutdown mid-turn closes open spans as incomplete, not as errors", async () => {
  const h = harness()
  const cut = fixture.events.findIndex((e: any) => e.type === "tool_execution_end")
  await h.replay([...fixture.events.slice(0, cut), { type: "session_shutdown" }])
  const spans = h.spans()
  const open = [...byName(spans, "execute_tool glob"), ...byName(spans, "execute_tool read"), ...byName(spans, "omp.turn"), ...byName(spans, "omp.prompt")]
  assert.equal(open.length, 4)
  for (const s of open) {
    assert.equal(attr(s, "omp.incomplete"), true)
    assert.equal(s.status.code, 0)
  }
})

test("a turn's spans leave about a second after the turn, with the open root and prompt", async () => {
  const h = harness()
  const firstTurnEnd = fixture.events.findIndex((e: any) => e.type === "turn_end")
  await h.replay(fixture.events.slice(0, firstTurnEnd + 1))
  assert.equal(h.requests.length, 0)
  await new Promise((resolve) => setTimeout(resolve, 1200))
  assert.equal(h.requests.length, 1)
  const names = h.requests[0].body.resourceSpans[0].scopeSpans[0].spans.map((s: any) => s.name).sort()
  assert.deepEqual(names, ["chat gpt-6-luna", "execute_tool glob", "execute_tool read", "omp.prompt", "omp.session", "omp.turn"].sort())
  const root = h.requests[0].body.resourceSpans[0].scopeSpans[0].spans.find((s: any) => s.name === "omp.session")
  assert.equal(attr(root, "omp.session.open"), true)
})

test("export target, headers and resource attributes", async () => {
  const h = harness()
  await h.replay()
  const r = h.requests[0]
  assert.equal(r.url, "http://collector.test/v1/traces")
  assert.equal(r.headers["X-Api-Key"], "test-api-key")
  assert.equal(r.headers["X-Secret-Key"], "test-secret-key")
  assert.equal(r.headers["Content-Type"], "application/json")
  const resource = Object.fromEntries(r.body.resourceSpans[0].resource.attributes.map((a: any) => [a.key, a.value.stringValue]))
  assert.equal(resource["service.name"], "oh-my-pi")
  assert.equal(resource.project_name, "omp-contract")
  assert.equal(resource.project_type, "observe")

  const viaBase = harness({ FI_API_KEY: "a", FI_SECRET_KEY: "b", FI_PROJECT_NAME: "p", FI_BASE_URL: "https://api.example.test/" })
  await viaBase.replay()
  assert.equal(viaBase.requests[0].url, "https://api.example.test/tracer/v1/traces")
  const defaults = harness({ FI_API_KEY: "a", FI_SECRET_KEY: "b", FI_PROJECT_NAME: "p" })
  await defaults.replay()
  assert.equal(defaults.requests[0].url, "https://api.futureagi.com/tracer/v1/traces")
})

test("inert without credentials or project; no session id means no spans", async () => {
  for (const missing of ["FI_API_KEY", "FI_SECRET_KEY", "FI_PROJECT_NAME"]) {
    const env: Record<string, string> = { ...ENV }
    delete env[missing]
    const h = harness(env)
    assert.equal(h.handlers.size, 0)
  }
  const h = harness()
  await h.replay(fixture.events, "")
  assert.equal(h.requests.length, 0)
})

test("a failed export never throws and is retried once with the next flush", async () => {
  let calls = 0
  const h = harness(ENV, async () => {
    calls += 1
    if (calls === 1) throw new TypeError("fetch failed")
    return { ok: true, status: 200 }
  })
  await h.replay()
  assert.ok(h.returns.every((r) => r === undefined))
  assert.equal(h.requests.length, 2)
  const firstIds = new Set(h.requests[0].body.resourceSpans[0].scopeSpans[0].spans.map((s: any) => s.spanId))
  const secondIds = new Set(h.requests[1].body.resourceSpans[0].scopeSpans[0].spans.map((s: any) => s.spanId))
  for (const id of firstIds) assert.ok(secondIds.has(id), "spans from the failed batch are sent again")
})

test("a /new switch closes the previous session and starts a second trace", async () => {
  const h = harness()
  const upToEnd = fixture.events.filter((e: any) => e.type !== "session_shutdown")
  await h.replay(upToEnd)
  await h.emit({ type: "session_switch", reason: "new" }, "second-session-id")
  await h.replay([{ type: "agent_start" }, { type: "turn_start", turnIndex: 0, timestamp: 1792032100000 }, { type: "turn_end" }, { type: "agent_end" }, { type: "session_shutdown" }], "second-session-id")
  const roots = byName(h.spans(), "omp.session")
  assert.equal(roots.length, 2)
  assert.notEqual(roots[0].traceId, roots[1].traceId)
  assert.deepEqual(roots.map((r) => attr(r, "session.id")).sort(), [fixture.sessionId, "second-session-id"].sort())
  for (const r of roots) assert.equal(attr(r, "omp.session.open"), undefined)
})

test("a branch into a new session file (session_branch) closes the previous session like a switch", async () => {
  const h = harness()
  assert.ok(h.handlers.has("session_branch"))
  await h.replay(fixture.events.filter((e: any) => e.type !== "session_shutdown"))
  await h.emit({ type: "session_branch", previousSessionFile: "previous.jsonl" }, "branched-session-id")
  await new Promise((resolve) => setTimeout(resolve, 20))
  const before = byName(h.spans(), "omp.session")
  assert.equal(before.length, 1, "the previous session's final root leaves as soon as the branch happens")
  assert.equal(attr(before[0], "omp.session.open"), undefined)
  await h.replay([{ type: "agent_start" }, { type: "turn_start", turnIndex: 0, timestamp: 1792032100000 }, { type: "turn_end" }, { type: "agent_end" }, { type: "session_shutdown" }], "branched-session-id")
  const roots = byName(h.spans(), "omp.session")
  assert.equal(roots.length, 2)
  assert.notEqual(roots[0].traceId, roots[1].traceId)
  const first = roots.find((r) => attr(r, "session.id") === fixture.sessionId)
  const [secondPrompt] = byName(h.spans(), "omp.prompt").filter((p) => attr(p, "session.id") === "branched-session-id")
  assert.ok(BigInt(first.endTimeUnixNano) <= BigInt(secondPrompt.startTimeUnixNano), "the old root ends at the branch, not at process exit")
})

test("a session_branch that keeps the same session id continues the same trace", async () => {
  const h = harness()
  await h.replay(fixture.events.filter((e: any) => e.type !== "session_shutdown"))
  await h.emit({ type: "session_branch", reason: "branch", previousSessionFile: "same.jsonl" })
  await h.replay(fixture.events.filter((e: any) => e.type !== "session_start"))
  const roots = byName(h.spans(), "omp.session")
  assert.equal(new Set(roots.map((r) => r.traceId)).size, 1)
  assert.equal(attr(roots.at(-1), "omp.prompt.count"), 2)
})

test("a session with no prompt, model call or tool call exports nothing", async () => {
  const h = harness()
  await h.replay([{ type: "session_start" }, { type: "session_shutdown" }])
  assert.equal(h.requests.length, 0)

  // Opening omp and immediately starting /new leaves an unused session behind: only the used one is exported.
  const s = harness()
  await s.emit({ type: "session_start" }, "unused-session-id")
  await s.emit({ type: "session_switch", reason: "new" }, fixture.sessionId)
  await s.replay(fixture.events.filter((e: any) => e.type !== "session_start"))
  const roots = byName(s.spans(), "omp.session")
  assert.deepEqual(roots.map((r) => attr(r, "session.id")), [fixture.sessionId])
})

test("events that arrive after session_shutdown do not open a new trace", async () => {
  const h = harness()
  await h.replay()
  const sent = h.requests.length
  const late = fixture.events.filter((e: any) => ["message_end", "turn_end", "agent_end"].includes(e.type)).slice(-3)
  await h.replay(late)
  await new Promise((resolve) => setTimeout(resolve, 1200))
  assert.equal(h.requests.length, sent)
  assert.equal(new Set(h.spans().map((s) => s.traceId)).size, 1)
})

test("fork guard: under upstream Pi (no ctx.agent) the hook exports nothing", async () => {
  // Upstream pi's ExtensionContext (@earendil-works/pi-coding-agent 1.2.0) has mode, cwd, hasUI,
  // model and sessionManager, but no `agent` identity; omp's always has one.
  const { agent: _omit, ...piCtx } = fixture.ctx
  const h = harness(ENV, undefined, piCtx)
  await h.replay()
  await new Promise((resolve) => setTimeout(resolve, 1200))
  assert.equal(h.requests.length, 0)
  assert.ok(h.returns.length > 0 && h.returns.every((r) => r === undefined))
  const nonObject = harness(ENV, undefined, { ...fixture.ctx, agent: "main" })
  await nonObject.replay()
  assert.equal(nonObject.requests.length, 0)
})

test("error text with a local path and user name is not exported by default", async () => {
  const path = "/Users/alice-fixture/projects/acme/.env"
  const h = harness()
  const events = fixture.events.map((e: any) => {
    if (e.type === "tool_execution_end" && e.toolName === "read")
      return {
        ...e,
        isError: true,
        result: { content: [{ type: "text", text: `ENOENT: no such file or directory, open '${path}'` }], details: { path, user: "alice-fixture" } },
      }
    if (e.type === "message_end" && e.message.stopReason === "stop")
      return {
        ...e,
        message: {
          ...e.message,
          stopReason: "error",
          errorStatus: 500,
          errorMessage: `upstream failed reading ${path} for user alice-fixture on alice-fixture-macbook`,
          content: [],
        },
      }
    return e
  })
  await h.replay(events)
  const body = JSON.stringify(h.requests.map((r) => r.body))
  for (const needle of ["/Users/", "alice-fixture", ".env", "ENOENT", "upstream failed"]) {
    assert.ok(!body.includes(needle), `${needle} leaked into the default export`)
  }
  const spans = h.spans()
  const [read] = byName(spans, "execute_tool read")
  assert.deepEqual([read.status.code, read.status.message, attr(read, "error.type")], [2, "error details omitted by default", "ToolError"])
  const failed = byName(spans, "chat gpt-6-luna").find((s) => s.status.code === 2)
  assert.deepEqual([failed.status.message, attr(failed, "error.type"), attr(failed, "omp.error.http_status")], ["error details omitted by default", "ProviderError", 500])

  // The opt-in exports the error text (still subject to the 4096-character cap and key redaction).
  const withContent = harness({ ...ENV, FI_CAPTURE_CONTENT: "true" })
  await withContent.replay(events)
  const optIn = JSON.stringify(withContent.requests.map((r) => r.body))
  assert.ok(optIn.includes(path) && optIn.includes("upstream failed"))
})
