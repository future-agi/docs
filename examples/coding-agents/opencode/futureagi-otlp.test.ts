// Contract tests for futureagi-otlp.ts. No network: a fake fetch records every
// OTLP request. Run with Node >= 23.6 (built-in TypeScript type stripping):
//   node --test futureagi-otlp.test.ts
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { FutureAGITracing } from "./futureagi-otlp.ts"

const fixture = JSON.parse(readFileSync(new URL("./fixtures/opencode-1.19.0-session.json", import.meta.url), "utf8"))
const BASE_ENV = { FI_API_KEY: "test-api-key", FI_SECRET_KEY: "test-secret-key", FI_PROJECT_NAME: "my-opencode-project" }

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
  const hooksPromise = FutureAGITracing(ctx, { env: { ...BASE_ENV, ...env }, fetch: fakeFetch, now } as any)
  return { requests, hooksPromise }
}

async function replay(hooks: any, steps: any[]) {
  for (const step of steps) {
    if (step.event) await hooks.event({ event: step.event })
    else if (step.hook === "dispose") await hooks.dispose()
    else await hooks[step.hook](structuredClone(step.input), structuredClone(step.output))
  }
}

function spansOf(requests: Request[]) {
  return requests.flatMap((r) => r.body.resourceSpans.flatMap((rs: any) => rs.scopeSpans.flatMap((ss: any) => ss.spans)))
}

const attr = (span: any, key: string) => {
  const found = span.attributes.find((a: any) => a.key === key)
  if (!found) return undefined
  const v = found.value
  return v.stringValue ?? (v.intValue !== undefined ? Number(v.intValue) : undefined) ?? v.boolValue ?? v.doubleValue ?? v.arrayValue
}

test("inert without credentials", async () => {
  const hooks = await FutureAGITracing({} as any, { env: {} } as any)
  assert.deepEqual(hooks, {})
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
  assert.equal(spans.length, 6)
  assert.equal(root.parentSpanId, undefined)
  assert.equal(attr(root, "fi.span.kind"), "AGENT")
  assert.equal(attr(root, "session.id"), "ses_ec2fe9a12ffeVh3mBpczIXJ4AG")
  assert.equal(attr(root, "opencode.tool.count"), 2)
  assert.equal(attr(root, "gen_ai.request.model"), undefined, "root must not look like an LLM span")
  assert.equal(turn.parentSpanId, root.spanId)
  assert.equal(attr(turn, "fi.span.kind"), "CHAIN")
  assert.equal(attr(turn, "opencode.prompt.bytes") > 0, true)
  assert.equal(llm.length, 2)
  for (const span of llm) {
    assert.equal(span.parentSpanId, turn.spanId)
    assert.equal(attr(span, "fi.span.kind"), "LLM")
    assert.equal(attr(span, "gen_ai.provider.name"), "cliproxy")
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

test("content is capped at 4 KiB", async () => {
  const { requests, hooksPromise } = harness({ FI_CAPTURE_CONTENT: "true" })
  const hooks = await hooksPromise
  const steps = structuredClone(fixture.steps)
  steps[1].output.parts[0].text = "x".repeat(10000)
  await replay(hooks, steps)
  const [turn] = spansOf(requests).filter((s) => s.name === "opencode.turn")
  assert.equal(attr(turn, "input.value").length, 4096)
  assert.equal(attr(turn, "opencode.prompt.bytes"), 10000)
})

test("tool, model and session errors are ERROR without messages", async () => {
  const { requests, hooksPromise } = harness()
  const hooks = await hooksPromise
  const steps = structuredClone(fixture.steps)
  const toolDone = steps.find((s: any) => s.event?.properties?.part?.state?.status === "completed")
  toolDone.event.properties.part.state = { status: "error", input: {}, error: "SECRET-MARKER-tool-error", time: { start: 1792024881036, end: 1792024881090 } }
  const lastAssistant = steps.filter((s: any) => s.event?.properties?.info?.role === "assistant").at(-1)
  lastAssistant.event.properties.info.error = { name: "APIError", data: { message: "SECRET-MARKER-api-error" } }
  steps.splice(steps.length - 1, 0, { event: { type: "session.error", properties: { sessionID: "ses_ec2fe9a12ffeVh3mBpczIXJ4AG", error: { name: "APIError", data: { message: "SECRET-MARKER-api-error" } } } } })
  await replay(hooks, steps)
  const spans = spansOf(requests)
  const failedTool = spans.find((s) => s.name === "execute_tool read" && s.status.code === 2)
  assert.ok(failedTool)
  assert.equal(failedTool.status.message, "error details omitted by default")
  const failedLlm = spans.filter((s) => s.name.startsWith("chat ")).at(-1)
  assert.equal(failedLlm.status.code, 2)
  assert.equal(attr(failedLlm, "error.type"), "APIError")
  assert.equal(spans.find((s) => s.name === "opencode.turn").status.code, 2)
  assert.equal(spans.find((s) => s.name === "opencode.session").status.code, 2)
  assert.ok(!requests.some((r) => r.raw.includes("SECRET-MARKER")))
})

test("hooks never change tool arguments and survive a failing collector", async () => {
  const { requests, hooksPromise } = harness({}, true)
  const hooks = await hooksPromise
  const output = { args: { command: "ls -la" } }
  await hooks["tool.execute.before"]({ tool: "bash", sessionID: "ses_x", callID: "call_1" }, output)
  assert.deepEqual(output, { args: { command: "ls -la" } })
  await replay(hooks, fixture.steps)
  assert.equal(requests.length, 0)
})

test("a subagent session joins its parent's trace", async () => {
  const { requests, hooksPromise } = harness()
  const hooks = await hooksPromise
  await replay(hooks, fixture.steps.slice(0, 3))
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_child", parentID: "ses_ec2fe9a12ffeVh3mBpczIXJ4AG", version: "1.19.0", time: { created: 1792024870000 } } } } })
  await hooks.event({ event: { type: "message.updated", properties: { info: { id: "msg_child_user", role: "user", sessionID: "ses_child", time: { created: 1792024870001 }, agent: "explore" } } } })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: "ses_child" } } })
  await hooks.dispose()
  const spans = spansOf(requests)
  assert.equal(new Set(spans.map((s) => s.traceId)).size, 1)
  const roots = spans.filter((s) => s.name === "opencode.session")
  const parent = roots.find((s) => attr(s, "session.id") === "ses_ec2fe9a12ffeVh3mBpczIXJ4AG")
  const child = roots.find((s) => attr(s, "session.id") === "ses_child")
  assert.equal(child.parentSpanId, parent.spanId)
  assert.equal(attr(child, "opencode.session.parent_id"), "ses_ec2fe9a12ffeVh3mBpczIXJ4AG")
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
  assert.equal(spans.length, 6, "spans from the failed first export arrive with a later flush")
  assert.equal(new Set(spans.map((s) => s.spanId)).size, 6, "no span is sent twice")
})
