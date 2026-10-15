// Contract tests for futureagi-otlp.ts. No network: a fake fetch records every
// OTLP request. Run with Node >= 23.6 (built-in TypeScript type stripping):
//   node --test futureagi-otlp.test.ts
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { FutureAGITracing } from "./futureagi-otlp.ts"

const fixture = JSON.parse(readFileSync(new URL("./fixtures/opencode-1.19.0-session.json", import.meta.url), "utf8"))
const page = readFileSync(new URL("../../../src/pages/docs/integrations/coding-agents/opencode.mdx", import.meta.url), "utf8")
const BASE_ENV = { FI_API_KEY: "test-api-key", FI_SECRET_KEY: "test-secret-key", FI_PROJECT_NAME: "my-opencode-project" }
const SEAM = Symbol.for("futureagi.opencode.test")
const SID = "ses_ec2fe9a12ffeVh3mBpczIXJ4AG"

type Request = { url: string; headers: Record<string, string>; body: any; raw: string }

function harness(env: Record<string, string> = {}, failFetch: boolean | number = false) {
  const requests: Request[] = []
  let calls = 0
  const fakeFetch = async (url: string, init: any) => {
    calls += 1
    if (failFetch === true || (typeof failFetch === "number" && calls <= failFetch)) throw new TypeError("network down")
    requests.push({ url, headers: init.headers, body: JSON.parse(init.body), raw: init.body })
    return { ok: true, status: 200 } as Response
  }
  let clock = 1792024860000
  const now = () => (clock += 5)
  const ctx = { directory: "/home/dev/demo", worktree: "/home/dev/demo" } as any
  const hooksPromise = FutureAGITracing(ctx, { [SEAM]: { env: { ...BASE_ENV, ...env }, fetch: fakeFetch, now } } as any)
  return { requests, hooksPromise }
}

// Replays recorded steps. Hooks the plugin does not register (the fixture also
// records `chat.message` and `tool.execute.before`) are skipped, as OpenCode does.
async function replay(hooks: any, steps: any[]) {
  for (const step of steps.flat()) {
    if (step.event) await hooks.event({ event: step.event })
    else if (step.hook === "dispose") await hooks.dispose()
    else if (hooks[step.hook]) await hooks[step.hook](structuredClone(step.input), structuredClone(step.output))
  }
}

function spansOf(requests: Request[]) {
  return requests.flatMap((r) => r.body.resourceSpans.flatMap((rs: any) => rs.scopeSpans.flatMap((ss: any) => ss.spans)))
}

// The latest copy of each span id, as Future AGI stores it.
function latest(requests: Request[]) {
  const byId = new Map<string, any>()
  for (const span of spansOf(requests)) byId.set(span.spanId, span)
  return [...byId.values()]
}

const attr = (span: any, key: string) => {
  const found = span.attributes.find((a: any) => a.key === key)
  if (!found) return undefined
  const v = found.value
  return v.stringValue ?? (v.intValue !== undefined ? Number(v.intValue) : undefined) ?? v.boolValue ?? v.doubleValue ?? v.arrayValue
}

// Small builders for synthetic event sequences (shapes from OpenCode 1.19.0).
const ev = (type: string, properties: any) => ({ event: { type, properties } })
const sessionCreated = (id = "ses_1", extra: any = {}) =>
  ev("session.created", { info: { id, version: "1.19.0", slug: "calm-fox", projectID: "global", time: { created: 1000 }, ...extra } })
// A user message as OpenCode publishes it: the message, then its text part.
const userMsg = (id: string, created: number, sessionID = "ses_1", text = "hello") => [
  ev("message.updated", { info: { id, role: "user", sessionID, agent: "build", model: { providerID: "p", modelID: "m" }, time: { created } } }),
  ev("message.part.updated", { part: { id: `prt_text_${id}`, messageID: id, sessionID, type: "text", text } }),
]
const assistant = (id: string, parentID: string, time: any, extra: any = {}, sessionID = "ses_1") =>
  ev("message.updated", {
    info: {
      id,
      parentID,
      role: "assistant",
      sessionID,
      modelID: "m",
      providerID: "p",
      agent: "build",
      tokens: { input: 0, output: 0, reasoning: 0, cache: { read: 0, write: 0 } },
      time,
      ...extra,
    },
  })
const stepStart = (messageID: string, sessionID = "ses_1") =>
  ev("message.part.updated", { part: { id: `prt_ss_${messageID}`, messageID, sessionID, type: "step-start" } })
const toolPart = (callID: string, messageID: string, state: any, extra: any = {}, sessionID = "ses_1") =>
  ev("message.part.updated", { part: { id: `prt_${callID}`, messageID, sessionID, type: "tool", tool: "bash", callID, state, ...extra } })
const idle = (sessionID = "ses_1") => ev("session.idle", { sessionID })
const usage = (input: number, output: number) => ({ tokens: { total: input + output, input, output, reasoning: 0, cache: { read: 0, write: 0 } } })

test("inert without credentials", async () => {
  const hooks = await FutureAGITracing({} as any, { [SEAM]: { env: {} } } as any)
  assert.deepEqual(hooks, {})
})

test("plugin options from opencode.json cannot replace the environment or fetch", async () => {
  const saved = { ...process.env }
  for (const key of Object.keys(process.env)) if (key.startsWith("FI_")) delete process.env[key]
  try {
    let called = false
    const options = JSON.parse(JSON.stringify({ env: BASE_ENV, now: 1 }))
    const hooks = await FutureAGITracing({} as any, { ...options, fetch: async () => ((called = true), { ok: true }) } as any)
    assert.deepEqual(hooks, {}, "options.env must be ignored: plugin stays inert without FI_* in the environment")
    assert.equal(called, false)
  } finally {
    process.env = saved
  }
})

test("default export: one trace, session > turn > llm > tool, no bodies", async () => {
  const { requests, hooksPromise } = harness()
  await replay(await hooksPromise, fixture.steps)
  const spans = spansOf(requests)
  assert.ok(requests.length >= 1)
  for (const r of requests) {
    assert.equal(r.url, "https://api.futureagi.com/tracer/v1/traces")
    assert.equal(r.headers["X-Api-Key"], "test-api-key")
    assert.equal(r.headers["X-Secret-Key"], "test-secret-key")
    const resource = Object.fromEntries(r.body.resourceSpans[0].resource.attributes.map((a: any) => [a.key, a.value.stringValue]))
    assert.equal(resource.project_name, "my-opencode-project")
    assert.equal(resource.project_type, "observe")
    assert.equal(resource["service.name"], "opencode")
    // Privacy default: nothing from any prompt, argument, output, answer or title.
    assert.ok(!r.raw.includes("SECRET-MARKER"), "a body leaked into the default export")
    assert.ok(!r.raw.includes("input.value") && !r.raw.includes("output.value"))
    // No local paths (they carry the OS user name).
    assert.ok(!r.raw.includes("/home/dev"), "a local path leaked into the default export")
    assert.ok(!r.raw.includes("opencode.directory"))
  }

  assert.equal(new Set(spans.map((s) => s.traceId)).size, 1, "one trace per session")
  const byName = (name: string) => spans.filter((s) => s.name === name)
  const [root] = byName("opencode.session")
  const [turn] = byName("opencode.turn")
  const llm = byName("chat gpt-6-luna")
  const toolSpans = byName("execute_tool read")
  assert.equal(spans.length, 6, "dispose with nothing new does not re-send the session span")
  assert.equal(byName("opencode.session").length, 1)
  assert.equal(root.parentSpanId, undefined)
  assert.equal(attr(root, "fi.span.kind"), "AGENT")
  assert.equal(attr(root, "session.id"), SID)
  assert.equal(attr(root, "opencode.tool.count"), 2)
  assert.equal(attr(root, "opencode.turn.count"), 1)
  assert.equal(attr(root, "opencode.session.slug"), "sunny-wolf")
  assert.equal(root.startTimeUnixNano, "1792024864237000000", "session span starts at the session's creation time")
  assert.equal(attr(root, "gen_ai.request.model"), undefined, "root must not look like an LLM span")
  assert.equal(turn.parentSpanId, root.spanId)
  assert.equal(attr(turn, "fi.span.kind"), "CHAIN")
  assert.equal(attr(turn, "opencode.prompt.bytes") > 0, true)
  assert.equal(llm.length, 2)
  for (const span of llm) {
    assert.equal(span.parentSpanId, turn.spanId)
    assert.equal(attr(span, "fi.span.kind"), "LLM")
    assert.equal(attr(span, "gen_ai.provider.name"), "cliproxy")
    assert.equal(attr(span, "opencode.incomplete"), undefined)
  }
  const [first, second] = llm
  assert.equal(attr(first, "gen_ai.usage.input_tokens"), 5243)
  assert.equal(attr(first, "gen_ai.usage.output_tokens"), 192)
  assert.equal(attr(second, "gen_ai.usage.input_tokens"), 942 + 4608)
  assert.equal(attr(second, "gen_ai.usage.cache_read.input_tokens"), 4608)
  assert.equal(attr(second, "gen_ai.usage.total_tokens"), 5598)
  assert.equal(toolSpans.length, 2)
  for (const span of toolSpans) {
    assert.equal(span.parentSpanId, first.spanId, "tool belongs to the step that called it")
    assert.equal(attr(span, "fi.span.kind"), "TOOL")
    assert.equal(attr(span, "gen_ai.operation.name"), "execute_tool")
    assert.equal(span.status.code, 1)
    assert.ok(attr(span, "opencode.tool.input.bytes") > 0)
  }
  assert.equal(toolSpans[0].startTimeUnixNano, "1792024881036000000")
  assert.equal(toolSpans[0].endTimeUnixNano, "1792024881090000000")
})

test("the session span is sent at every idle, before dispose, with cumulative latest-wins counts", async () => {
  const { requests, hooksPromise } = harness()
  const h = await hooksPromise
  const turn = async (n: number, at: number) => {
    await replay(h, [
      userMsg(`msg_u${n}`, at),
      assistant(`msg_a${n}`, `msg_u${n}`, { created: at + 1 }),
      stepStart(`msg_a${n}`),
      assistant(`msg_a${n}`, `msg_u${n}`, { created: at + 1, completed: at + 50 }, { ...usage(100 * n, 10), finish: "stop" }),
      idle(),
    ])
  }
  await replay(h, [sessionCreated()])
  await turn(1, 2000)
  const afterFirst = spansOf(requests).filter((s) => s.name === "opencode.session")
  assert.equal(afterFirst.length, 1, "root is exported with the first idle flush, not only at exit")
  await turn(2, 3000)
  await turn(3, 4000)
  // No dispose, no session.deleted: OpenCode was killed or is still running.
  const roots = spansOf(requests).filter((s) => s.name === "opencode.session")
  assert.equal(roots.length, 3, "one fresh copy per idle flush")
  assert.equal(new Set(roots.map((r) => r.spanId)).size, 1, "deterministic span id")
  assert.ok(roots.every((r) => r.startTimeUnixNano === "1000000000"), "start is the session's creation time")
  for (let i = 1; i < roots.length; i++) assert.ok(BigInt(roots[i].endTimeUnixNano) >= BigInt(roots[i - 1].endTimeUnixNano))
  const last = latest(requests).find((s) => s.name === "opencode.session")
  assert.equal(attr(last, "opencode.turn.count"), 3)
  assert.equal(attr(last, "opencode.llm.count"), 3)
  assert.equal(attr(last, "opencode.usage.input_tokens"), 600)
  assert.equal(attr(last, "opencode.usage.output_tokens"), 30)
  // Every child span of the trace is covered by a root copy in the same or an earlier request.
  for (const r of requests) assert.ok(spansOf([r]).some((s) => s.name === "opencode.session"))
  // dispose is a final refresh only when something was still open.
  const before = requests.length
  await h.dispose()
  assert.equal(requests.length, before)
})

test("dispose closes an open turn and refreshes the session span", async () => {
  const { requests, hooksPromise } = harness()
  const h = await hooksPromise
  await replay(h, [sessionCreated(), userMsg("msg_u1", 2000), assistant("msg_a1", "msg_u1", { created: 2001 }), stepStart("msg_a1")])
  assert.equal(requests.length, 0)
  await h.dispose()
  const spans = latest(requests)
  assert.equal(spans.filter((s) => s.name === "opencode.session").length, 1)
  const llm = spans.find((s) => s.name === "chat m")
  assert.equal(attr(llm, "opencode.incomplete"), true)
})

test("a queued follow-up message does not cut the running model step short", async () => {
  const { requests, hooksPromise } = harness()
  const h = await hooksPromise
  await replay(h, [
    sessionCreated(),
    userMsg("msg_A", 1001, "ses_1", "first"),
    assistant("msg_asst1", "msg_A", { created: 1002 }),
    stepStart("msg_asst1"),
    toolPart("call_1", "msg_asst1", { status: "running", input: {}, time: { start: 1100 } }),
    // The user types a follow-up while step 1 is still streaming. OpenCode
    // creates the user message (and fires chat.message) right away.
    userMsg("msg_B", 1500, "ses_1", "second"),
    toolPart("call_1", "msg_asst1", { status: "completed", input: {}, output: "ok", time: { start: 1100, end: 1800 } }),
    assistant("msg_asst1", "msg_A", { created: 1002, completed: 2000 }, { ...usage(1000, 100), finish: "stop" }),
    // The loop picks up the queued message as the next step's parent.
    assistant("msg_asst2", "msg_B", { created: 2001 }),
    stepStart("msg_asst2"),
    assistant("msg_asst2", "msg_B", { created: 2001, completed: 2500 }, { ...usage(50, 5), finish: "stop" }),
    idle(),
  ])
  await h.dispose()
  const spans = latest(requests)
  const llm1 = spans.find((s) => attr(s, "opencode.message.id") === "msg_asst1")
  assert.equal(attr(llm1, "gen_ai.usage.input_tokens"), 1000, "completed step's tokens must be exported")
  assert.equal(attr(llm1, "gen_ai.usage.output_tokens"), 100)
  assert.deepEqual(attr(llm1, "gen_ai.response.finish_reasons"), { values: [{ stringValue: "stop" }] })
  assert.equal(attr(llm1, "opencode.incomplete"), undefined)
  assert.equal(llm1.endTimeUnixNano, "2000000000")
  const [turnA, turnB] = ["msg_A", "msg_B"].map((id) => spans.find((s) => s.name === "opencode.turn" && attr(s, "opencode.message.id") === id))
  assert.equal(llm1.parentSpanId, turnA.spanId)
  assert.ok(BigInt(turnA.endTimeUnixNano) >= BigInt(llm1.endTimeUnixNano), "turn A ends after its step")
  const llm2 = spans.find((s) => attr(s, "opencode.message.id") === "msg_asst2")
  assert.equal(llm2.parentSpanId, turnB.spanId)
  const tool = spans.find((s) => s.name === "execute_tool bash")
  assert.equal(tool.parentSpanId, llm1.spanId)
  assert.ok(BigInt(tool.endTimeUnixNano) <= BigInt(llm1.endTimeUnixNano), "tool ends inside its (still open) step")
  const root = spans.find((s) => s.name === "opencode.session")
  assert.equal(attr(root, "opencode.usage.input_tokens"), 1050)
  assert.equal(attr(root, "opencode.turn.count"), 2)
  assert.equal(spansOf(requests).filter((s) => s.name !== "opencode.session").length, spans.length - 1, "no child span sent twice")
})

test("an abort is not an error, and the session span is not stuck on ERROR", async () => {
  const { requests, hooksPromise } = harness()
  const h = await hooksPromise
  const aborted = { name: "MessageAbortedError", data: { message: "The operation was aborted." } }
  await replay(h, [
    sessionCreated(),
    // Turn 1: the user presses Esc while a tool runs.
    userMsg("msg_u1", 2000),
    assistant("msg_a1", "msg_u1", { created: 2001 }),
    stepStart("msg_a1"),
    toolPart("call_1", "msg_a1", { status: "running", input: {}, time: { start: 2010 } }),
    ev("session.error", { sessionID: "ses_1", error: aborted }),
    toolPart("call_1", "msg_a1", { status: "error", input: {}, error: "Tool execution aborted", metadata: { interrupted: true }, time: { start: 2010, end: 2100 } }),
    assistant("msg_a1", "msg_u1", { created: 2001, completed: 2100 }, { error: aborted }),
    idle(),
  ])
  let spans = latest(requests)
  const llm = spans.find((s) => s.name === "chat m")
  assert.equal(llm.status.code, 1)
  assert.equal(attr(llm, "opencode.aborted"), true)
  assert.equal(attr(llm, "error.type"), undefined)
  const tool = spans.find((s) => s.name === "execute_tool bash")
  assert.equal(tool.status.code, 1)
  assert.equal(attr(tool, "opencode.aborted"), true)
  const turn1 = spans.find((s) => s.name === "opencode.turn")
  assert.equal(turn1.status.code, 1)
  assert.equal(attr(turn1, "opencode.aborted"), true)
  assert.equal(spans.find((s) => s.name === "opencode.session").status.code, 1)

  // Turn 2 fails with an API error; turn 3 succeeds. The session span follows the latest turn.
  const apiError = { name: "APIError", data: { message: "rate limited" } }
  await replay(h, [
    userMsg("msg_u2", 3000),
    assistant("msg_a2", "msg_u2", { created: 3001 }),
    stepStart("msg_a2"),
    ev("session.error", { sessionID: "ses_1", error: apiError }),
    assistant("msg_a2", "msg_u2", { created: 3001, completed: 3100 }, { error: apiError }),
    idle(),
  ])
  spans = latest(requests)
  let root = spans.find((s) => s.name === "opencode.session")
  assert.equal(root.status.code, 2)
  assert.equal(attr(root, "error.type"), "APIError")
  await replay(h, [
    userMsg("msg_u3", 4000),
    assistant("msg_a3", "msg_u3", { created: 4001 }),
    stepStart("msg_a3"),
    assistant("msg_a3", "msg_u3", { created: 4001, completed: 4100 }, { ...usage(5, 5), finish: "stop" }),
    idle(),
  ])
  spans = latest(requests)
  root = spans.find((s) => s.name === "opencode.session")
  assert.equal(root.status.code, 1, "a later successful turn clears the session status")
  assert.equal(attr(root, "error.type"), undefined)
  assert.equal(attr(root, "opencode.turn.error_count"), 1)
  const turn2 = spans.find((s) => s.name === "opencode.turn" && attr(s, "opencode.message.id") === "msg_u2")
  assert.equal(turn2.status.code, 2)
})

test("a context overflow recovered by compaction is not an error", async () => {
  const { requests, hooksPromise } = harness()
  const h = await hooksPromise
  await replay(h, [
    sessionCreated(),
    userMsg("msg_u1", 2000),
    ev("session.error", { sessionID: "ses_1", error: { name: "ContextOverflowError", data: {} } }),
    assistant("msg_a1", "msg_u1", { created: 2001 }),
    stepStart("msg_a1"),
    assistant("msg_a1", "msg_u1", { created: 2001, completed: 2900 }, { ...usage(5, 5), finish: "stop" }),
    idle(),
  ])
  const spans = latest(requests)
  assert.deepEqual(spans.map((s) => s.status.code), spans.map(() => 1))
  assert.equal(attr(spans.find((s) => s.name === "opencode.turn"), "opencode.context_overflow"), true)
})

test("a subtask command gives one task tool span and no 0-token model span", async () => {
  const { requests, hooksPromise } = harness()
  const h = await hooksPromise
  // OpenCode 1.19.0 handleSubtask: synthetic assistant message, tool part with
  // callID ulid(), hooks fired with callID = part.id.
  const taskArgs = { prompt: "do x", description: "x", subagent_type: "general" }
  await replay(h, [
    sessionCreated(),
    userMsg("msg_A", 1001, "ses_1", "@general do x"),
    assistant("msg_asst1", "msg_A", { created: 1002 }, { agent: "general" }),
    ev("message.part.updated", { part: { id: "prt_task", messageID: "msg_asst1", sessionID: "ses_1", type: "tool", tool: "task", callID: "01ULIDCALL", state: { status: "running", input: taskArgs, time: { start: 1003 } } } }),
    { hook: "tool.execute.before", input: { tool: "task", sessionID: "ses_1", callID: "prt_task" }, output: { args: taskArgs } },
    { hook: "tool.execute.after", input: { tool: "task", sessionID: "ses_1", callID: "prt_task", args: taskArgs }, output: { title: "", output: "subagent finished", metadata: {} } },
    assistant("msg_asst1", "msg_A", { created: 1002, completed: 1900 }, { finish: "tool-calls", agent: "general" }),
    ev("message.part.updated", { part: { id: "prt_task", messageID: "msg_asst1", sessionID: "ses_1", type: "tool", tool: "task", callID: "01ULIDCALL", state: { status: "completed", input: taskArgs, output: "done", time: { start: 1003, end: 1800 } } } }),
    idle(),
  ])
  await h.dispose()
  const spans = latest(requests)
  const tasks = spans.filter((s) => s.name === "execute_tool task")
  assert.equal(tasks.length, 1)
  assert.equal(attr(tasks[0], "gen_ai.tool.call.id"), "01ULIDCALL")
  assert.equal(attr(tasks[0], "opencode.tool.input.bytes"), Buffer.byteLength(JSON.stringify(taskArgs)))
  assert.equal(attr(tasks[0], "opencode.tool.output.bytes"), "subagent finished".length, "the after hook keyed by part id enriches the part-backed span")
  const turn = spans.find((s) => s.name === "opencode.turn")
  assert.equal(tasks[0].parentSpanId, turn.spanId)
  assert.equal(spans.filter((s) => s.name.startsWith("chat ")).length, 0, "no model span for a message that made no model call")
  assert.equal(attr(spans.find((s) => s.name === "opencode.session"), "opencode.llm.count"), 0)
})

test("FI_CAPTURE_CONTENT=true exports bounded, redacted bodies", async () => {
  const { requests, hooksPromise } = harness({ FI_CAPTURE_CONTENT: "true" })
  await replay(await hooksPromise, fixture.steps)
  const spans = spansOf(requests)
  const [turn] = spans.filter((s) => s.name === "opencode.turn")
  const tools = spans.filter((s) => s.name === "execute_tool read")
  const [root] = spans.filter((s) => s.name === "opencode.session")
  assert.match(attr(turn, "input.value"), /SECRET-MARKER-prompt/)
  assert.match(attr(turn, "input.value"), /api_key=\[REDACTED\]/)
  assert.match(attr(turn, "output.value"), /SECRET-MARKER-answer/)
  assert.match(attr(tools[0], "input.value"), /SECRET-MARKER-arg/)
  assert.match(attr(tools[0], "output.value"), /SECRET-MARKER-tool-output/)
  assert.ok(!attr(tools[0], "output.value").includes("sk-abcdefghijklmnop"), "secret pattern redacted")
  assert.match(attr(root, "opencode.session.title"), /SECRET-MARKER-title/)
  assert.equal(attr(root, "opencode.directory"), "/home/dev/demo")
  // Tool metadata previews are never exported, even with content on.
  assert.ok(!requests.some((r) => r.raw.includes("SECRET-MARKER-preview")))
})

test("content capture redacts JSON-shaped secret keys in tool arguments", async () => {
  const { requests, hooksPromise } = harness({ FI_CAPTURE_CONTENT: "true" })
  const h = await hooksPromise
  const args = {
    url: "https://example.com",
    api_key: "abc123def456ghi",
    headers: { "x-api-key": "jkl789mno012pqr", Authorization: "Bearer tok_1234567890abcdef" },
    password: "hunter2hunter2",
    client_secret: "s3cr3tvalue99",
    note: "export OPENAI_API_KEY=stu345vwx678yz",
    env: { FI_SECRET_KEY: "fisecret0011223344", AWS_SECRET_ACCESS_KEY: "awssecret5566778899", private_key: "privkey0099887766" },
    max_tokens: 4096,
  }
  await replay(h, [
    sessionCreated(),
    userMsg("msg_u1", 2000),
    assistant("msg_a1", "msg_u1", { created: 2001 }),
    stepStart("msg_a1"),
    toolPart("call_1", "msg_a1", { status: "running", input: args, time: { start: 2010 } }),
    { hook: "tool.execute.after", input: { tool: "bash", sessionID: "ses_1", callID: "call_1", args }, output: { title: "", output: '{"token":"zz9988776655"}', metadata: {} } },
    toolPart("call_1", "msg_a1", { status: "completed", input: args, output: "x", time: { start: 2010, end: 2020 } }),
    assistant("msg_a1", "msg_u1", { created: 2001, completed: 2100 }, usage(1, 1)),
    idle(),
  ])
  const tool = latest(requests).find((s) => s.name === "execute_tool bash")
  const input = attr(tool, "input.value")
  for (const secret of ["abc123def456ghi", "jkl789mno012pqr", "tok_1234567890abcdef", "hunter2hunter2", "s3cr3tvalue99", "stu345vwx678yz", "fisecret0011223344", "awssecret5566778899", "privkey0099887766"]) {
    assert.ok(!requests.some((r) => r.raw.includes(secret)), `${secret} leaked`)
  }
  assert.ok(!requests.some((r) => r.raw.includes("zz9988776655")), "secret in tool output leaked")
  assert.match(input, /"api_key":"\[REDACTED\]"/)
  assert.match(input, /"x-api-key":"\[REDACTED\]"/)
  assert.match(input, /https:\/\/example.com/, "ordinary values are kept")
  assert.match(input, /"max_tokens":4096/, "a key that only contains a keyword is kept")
})

test("content is capped at 4096 UTF-8 bytes without splitting a character", async () => {
  const cases = ["x".repeat(10000), "é".repeat(5000), "😀".repeat(3000)]
  for (const text of cases) {
    const { requests, hooksPromise } = harness({ FI_CAPTURE_CONTENT: "true" })
    const steps = structuredClone(fixture.steps)
    steps[3].event.properties.part.text = text
    await replay(await hooksPromise, steps)
    const [turn] = spansOf(requests).filter((s) => s.name === "opencode.turn")
    const value: string = attr(turn, "input.value")
    const bytes = Buffer.byteLength(value, "utf8")
    assert.ok(bytes <= 4096 && bytes > 4090, `${bytes} bytes`)
    assert.ok(text.startsWith(value), "a prefix of the original, no replacement characters")
    assert.equal(attr(turn, "opencode.prompt.bytes"), Buffer.byteLength(text, "utf8"))
  }
})

test("tool, model and session errors are ERROR with the error type only", async () => {
  const { requests, hooksPromise } = harness()
  const hooks = await hooksPromise
  const steps = structuredClone(fixture.steps)
  const toolDone = steps.find((s: any) => s.event?.properties?.part?.state?.status === "completed")
  toolDone.event.properties.part.state = { status: "error", input: {}, error: "SECRET-MARKER-tool-error", time: { start: 1792024881036, end: 1792024881090 } }
  const lastAssistant = steps.filter((s: any) => s.event?.properties?.info?.role === "assistant").at(-1)
  lastAssistant.event.properties.info.error = { name: "APIError", data: { message: "SECRET-MARKER-api-error" } }
  steps.splice(steps.length - 1, 0, { event: { type: "session.error", properties: { sessionID: SID, error: { name: "APIError", data: { message: "SECRET-MARKER-api-error" } } } } })
  await replay(hooks, steps)
  const spans = spansOf(requests)
  const failedTool = spans.find((s) => s.name === "execute_tool read" && s.status.code === 2)
  assert.ok(failedTool)
  assert.equal(failedTool.status.message, "ToolError")
  assert.equal(attr(failedTool, "error.type"), "ToolError")
  const failedLlm = spans.filter((s) => s.name.startsWith("chat ")).at(-1)
  assert.equal(failedLlm.status.code, 2)
  assert.equal(failedLlm.status.message, "APIError")
  assert.equal(attr(failedLlm, "error.type"), "APIError")
  assert.equal(spans.find((s) => s.name === "opencode.turn").status.code, 2)
  assert.equal(latest(requests).find((s) => s.name === "opencode.session").status.code, 2)
  assert.ok(!requests.some((r) => r.raw.includes("SECRET-MARKER")))
})

test("error text with a local path and user name is not exported by default", async () => {
  const leak = "/Users/alice-dev/work/acme/src/app.py"
  const run = async (env: Record<string, string>) => {
    const { requests, hooksPromise } = harness(env)
    const h = await hooksPromise
    await replay(h, [
      sessionCreated(),
      userMsg("msg_u1", 2000),
      assistant("msg_a1", "msg_u1", { created: 2001 }),
      stepStart("msg_a1"),
      toolPart("call_1", "msg_a1", { status: "running", input: {}, time: { start: 2010 } }),
      toolPart("call_1", "msg_a1", { status: "error", input: {}, error: `ENOENT: no such file or directory, open '${leak}' (user alice-dev)`, time: { start: 2010, end: 2020 } }),
      ev("session.error", { sessionID: "ses_1", error: { name: "UnknownError", data: { message: `Error: EACCES ${leak}\n    at /Users/alice-dev/.opencode/bin` } } }),
      assistant("msg_a1", "msg_u1", { created: 2001, completed: 2100 }, { error: { name: "APIError", data: { message: `config ${leak} rejected for alice-dev` } } }),
      // An error whose name is not a class name is reduced to "Error".
      ev("session.error", { sessionID: "ses_1", error: { name: `failed reading ${leak}`, data: {} } }),
      idle(),
    ])
    await h.dispose()
    return requests
  }
  const off = await run({})
  assert.ok(off.length > 0)
  for (const r of off) {
    assert.ok(!r.raw.includes("/Users/"), "a local path leaked through error text")
    assert.ok(!r.raw.includes("alice-dev"), "the user name leaked through error text")
  }
  const statuses = latest(off).filter((s) => s.status.code === 2).map((s) => s.status.message)
  assert.ok(statuses.length >= 3)
  for (const message of statuses) assert.match(message, /^[A-Za-z][A-Za-z0-9_.]*$/)
  // Opt-in: with content capture the error text is exported (bounded, redacted).
  const on = await run({ FI_CAPTURE_CONTENT: "true" })
  const tool = latest(on).find((s) => s.name === "execute_tool bash")
  assert.match(tool.status.message, /ENOENT/)
  assert.match(attr(tool, "output.value"), /ENOENT/)
})

test("observe-only: no pre-prompt or pre-tool hook, tool output untouched, failing collector is harmless", async () => {
  const { requests, hooksPromise } = harness({}, true)
  const hooks = await hooksPromise
  // Hooks that run before a prompt or a tool call (and can block it by throwing) are not registered.
  assert.deepEqual(Object.keys(hooks).sort(), ["dispose", "event", "tool.execute.after"])
  const input = { tool: "bash", sessionID: "ses_x", callID: "call_1", args: { command: "ls -la" } }
  const output = { title: "ls", output: "a\nb", metadata: { exit: 0 } }
  await hooks["tool.execute.after"](input, output)
  assert.deepEqual(input, { tool: "bash", sessionID: "ses_x", callID: "call_1", args: { command: "ls -la" } })
  assert.deepEqual(output, { title: "ls", output: "a\nb", metadata: { exit: 0 } })
  // Malformed input never throws into OpenCode.
  await hooks["tool.execute.after"](undefined, undefined)
  await hooks.event({ event: { type: "message.updated", properties: { info: { id: "m", sessionID: "s", role: "assistant", time: null } } } })
  await hooks.event({ event: null })
  await replay(hooks, fixture.steps)
  assert.equal(requests.length, 0)
})

test("updates OpenCode re-publishes after a turn was sent do not add turns or tools", async () => {
  const { requests, hooksPromise } = harness()
  const h = await hooksPromise
  await replay(h, [
    sessionCreated(),
    userMsg("msg_u1", 2000),
    assistant("msg_a1", "msg_u1", { created: 2001 }),
    stepStart("msg_a1"),
    toolPart("call_1", "msg_a1", { status: "running", input: { command: "ls" }, time: { start: 2010 } }),
    toolPart("call_1", "msg_a1", { status: "completed", input: { command: "ls" }, output: "a", time: { start: 2010, end: 2020 } }),
    assistant("msg_a1", "msg_u1", { created: 2001, completed: 2100 }, { ...usage(10, 1), finish: "stop" }),
    idle(),
    // Session summary updates the user message; compaction pruning updates old
    // tool parts and the assistant message. All of them after the idle flush.
    ev("message.updated", { info: { id: "msg_u1", role: "user", sessionID: "ses_1", time: { created: 2000 }, summary: { diffs: [] } } }),
    toolPart("call_1", "msg_a1", { status: "completed", input: { command: "ls" }, output: "a", time: { start: 2010, end: 2020, compacted: 9000 } }),
    assistant("msg_a1", "msg_u1", { created: 2001, completed: 2100 }, { ...usage(10, 1), finish: "stop" }),
    idle(),
  ])
  await h.dispose()
  const spans = latest(requests)
  const root = spans.find((s) => s.name === "opencode.session")
  assert.equal(attr(root, "opencode.turn.count"), 1)
  assert.equal(attr(root, "opencode.tool.count"), 1)
  assert.equal(attr(root, "opencode.llm.count"), 1)
  assert.equal(attr(root, "opencode.usage.input_tokens"), 10)
  assert.equal(spans.filter((s) => s.name === "opencode.turn").length, 1)
  const llm = spans.find((s) => s.name === "chat m")
  const tool = spans.find((s) => s.name === "execute_tool bash")
  assert.equal(tool.parentSpanId, llm.spanId, "the tool span is not re-sent under another parent")
  assert.equal(spansOf(requests).filter((s) => s.name !== "opencode.session").length, spans.length - 1, "no child span sent twice")
})

test("a subagent session joins its parent's trace", async () => {
  const { requests, hooksPromise } = harness()
  const hooks = await hooksPromise
  await replay(hooks, fixture.steps.slice(0, 3))
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_child", parentID: SID, version: "1.19.0", time: { created: 1792024870000 } } } } })
  await hooks.event({ event: { type: "message.updated", properties: { info: { id: "msg_child_user", role: "user", sessionID: "ses_child", time: { created: 1792024870001 }, agent: "explore" } } } })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: "ses_child" } } })
  // The subagent goes idle while the parent's first turn is still running:
  // its batch already carries the parent session span, the root of the trace.
  assert.equal(requests.length, 1)
  const firstBatch = spansOf(requests)
  assert.deepEqual(firstBatch.filter((s) => s.name === "opencode.session").map((s) => attr(s, "session.id")).sort(), [SID, "ses_child"].sort())
  await hooks.dispose()
  const spans = latest(requests)
  assert.equal(new Set(spans.map((s) => s.traceId)).size, 1)
  const roots = spans.filter((s) => s.name === "opencode.session")
  const parent = roots.find((s) => attr(s, "session.id") === SID)
  const child = roots.find((s) => attr(s, "session.id") === "ses_child")
  assert.equal(child.parentSpanId, parent.spanId)
  assert.equal(attr(child, "opencode.session.parent_id"), SID)
})

test("explicit endpoint and FI_BASE_URL are honoured", async () => {
  const a = harness({ FI_OTLP_ENDPOINT: "http://localhost:14338/v1/traces" })
  await replay(await a.hooksPromise, fixture.steps)
  assert.ok(a.requests.every((r) => r.url === "http://localhost:14338/v1/traces"))
  const b = harness({ FI_BASE_URL: "http://localhost:14338/" })
  await replay(await b.hooksPromise, fixture.steps)
  assert.ok(b.requests.every((r) => r.url === "http://localhost:14338/tracer/v1/traces"))
})

test("a failed export is retried once with the next flush", async () => {
  const { requests, hooksPromise } = harness({}, 1)
  await replay(await hooksPromise, fixture.steps)
  const spans = spansOf(requests)
  const children = spans.filter((s) => s.name !== "opencode.session")
  assert.equal(children.length, 5, "spans from the failed first export arrive with a later flush")
  assert.equal(new Set(children.map((s) => s.spanId)).size, 5, "no child span is sent twice")
  assert.equal(spans.filter((s) => s.name === "opencode.session").length, 1, "the session span is re-sent with them")
})

test("dispose returns within two export timeouts when the collector hangs", async () => {
  // A collector that accepts the connection and never answers. Like real
  // fetch, the request only ends when its abort signal fires.
  const hang = (_url: string, init: any) =>
    new Promise<Response>((_, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason)))
  const hooks: any = await FutureAGITracing({} as any, { [SEAM]: { env: { ...BASE_ENV, FI_OTLP_TIMEOUT_MS: "200" }, fetch: hang } } as any)
  // Queue several exports (idle) without waiting for them, as OpenCode does.
  for (const step of fixture.steps.slice(0, -1)) {
    if (step.event) void hooks.event({ event: step.event })
    else if (hooks[step.hook]) await hooks[step.hook](structuredClone(step.input), structuredClone(step.output))
  }
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_2", time: { created: 1 } } } } })
  void hooks.event({ event: { type: "message.updated", properties: { info: { id: "msg_2", role: "user", sessionID: "ses_2", time: { created: 2 } } } } })
  void hooks.event({ event: { type: "session.idle", properties: { sessionID: "ses_2" } } })
  const started = Date.now()
  await hooks.dispose()
  const waited = Date.now() - started
  assert.ok(waited < 2 * 200 + 150, `dispose waited ${waited} ms`)
})

test("every exported attribute is documented on the page", async () => {
  const keys = new Set<string>()
  const collect = (requests: Request[]) => spansOf(requests).forEach((s) => s.attributes.forEach((a: any) => keys.add(a.key)))
  for (const env of [{}, { FI_CAPTURE_CONTENT: "true" }]) {
    const a = harness(env)
    await replay(await a.hooksPromise, fixture.steps)
    collect(a.requests)
  }
  const b = harness()
  const h = await b.hooksPromise
  await replay(h, [
    sessionCreated("ses_1", { parentID: "ses_parent" }),
    userMsg("msg_u1", 2000),
    ev("session.error", { sessionID: "ses_1", error: { name: "ContextOverflowError", data: {} } }),
    assistant("msg_a1", "msg_u1", { created: 2001 }),
    stepStart("msg_a1"),
    toolPart("call_1", "msg_a1", { status: "error", input: {}, error: "Tool execution aborted", metadata: { interrupted: true }, time: { start: 2010, end: 2020 } }),
    toolPart("call_2", "msg_a1", { status: "error", input: {}, error: "boom", time: { start: 2010, end: 2020 } }),
    toolPart("call_3", "msg_a1", { status: "running", input: {}, time: { start: 2030 } }),
    assistant("msg_a1", "msg_u1", { created: 2001, completed: 2100 }, { error: { name: "MessageAbortedError", data: {} } }),
    userMsg("msg_u2", 3000),
    assistant("msg_a2", "msg_u2", { created: 3001 }),
    stepStart("msg_a2"),
    assistant("msg_a2", "msg_u2", { created: 3001, completed: 3100 }, { error: { name: "APIError", data: {} } }),
    userMsg("msg_u3", 4000),
    assistant("msg_a3", "msg_u3", { created: 4001 }),
    stepStart("msg_a3"),
  ])
  await h.dispose()
  collect(b.requests)
  const missing = [...keys].filter((key) => !page.includes(`\`${key}\``))
  assert.deepEqual(missing, [], "attributes exported by the plugin but not listed on the docs page")
})
