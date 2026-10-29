// Unit and wire tests for the Future AGI destination. No network beyond a
// loopback recorder, no model, no keys. Run: npm test (Node >= 24).
import assert from "node:assert/strict";
import { after, before, describe, test } from "node:test";

import type { Context } from "@opentelemetry/api";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { BasicTracerProvider, type ReadableSpan, type Span, type SpanProcessor } from "@opentelemetry/sdk-trace-base";
import { isOtelDeclaration, isOtelIntegration } from "eve/instrumentation/otel";

import {
  DROPPED_SCOPES,
  PRINCIPAL_ID_KEYS,
  ScopeFilterSpanProcessor,
  captureContentEnabled,
  futureAGIExportPolicy,
  futureAGIExporter,
  futureAGISpanProcessor,
  futureAGITracesUrl,
  scopeName,
} from "../agent/lib/futureagi.ts";
import { startRecorder } from "../scripts/recorder.mjs";

const SECRET = { FI_API_KEY: "test-api-key-123", FI_SECRET_KEY: "test-secret-key-456" };
const MARKER = "PRIVACYMARKER7f3a";

function fakeSpan(scope: string, legacy = false): ReadableSpan {
  return (legacy ? { instrumentationLibrary: { name: scope } } : { instrumentationScope: { name: scope } }) as unknown as ReadableSpan;
}

class RecordingProcessor implements SpanProcessor {
  started: string[] = [];
  ended: string[] = [];
  flushed = 0;
  shut = 0;
  onStart(span: Span, _ctx: Context): void { this.started.push(scopeName(span)); }
  onEnd(span: ReadableSpan): void { this.ended.push(scopeName(span)); }
  async forceFlush(): Promise<void> { this.flushed++; }
  async shutdown(): Promise<void> { this.shut++; }
}

describe("scopeName", () => {
  test("reads OTel JS SDK 2.x instrumentationScope", () => assert.equal(scopeName(fakeSpan("eve.agent")), "eve.agent"));
  test("reads SDK 1.x instrumentationLibrary", () => assert.equal(scopeName(fakeSpan("workflow", true)), "workflow"));
  test("empty when absent", () => assert.equal(scopeName({} as ReadableSpan), ""));
});

describe("captureContentEnabled", () => {
  for (const v of ["1", "true", "TRUE", "yes", "on", " 1 "]) test(`"${v}" opts in`, () => assert.equal(captureContentEnabled({ FI_CAPTURE_CONTENT: v }), true));
  for (const v of [undefined, "", "0", "false", "off", "no", "2"]) test(`${JSON.stringify(v)} stays off`, () => assert.equal(captureContentEnabled({ FI_CAPTURE_CONTENT: v }), false));
});

describe("ScopeFilterSpanProcessor", () => {
  test("drops workflow and @vercel/otel/fetch, forwards everything else", () => {
    const next = new RecordingProcessor();
    const p = new ScopeFilterSpanProcessor(next);
    for (const scope of ["workflow", "eve.agent", "@vercel/otel/fetch", "@opentelemetry/instrumentation-pg", ""]) {
      p.onStart(fakeSpan(scope) as unknown as Span, {} as Context);
      p.onEnd(fakeSpan(scope));
    }
    assert.deepEqual(next.started, ["eve.agent", "@opentelemetry/instrumentation-pg", ""]);
    assert.deepEqual(next.ended, ["eve.agent", "@opentelemetry/instrumentation-pg", ""]);
  });
  test("forwards forceFlush and shutdown (eve flushes per tool call and step)", async () => {
    const next = new RecordingProcessor();
    const p = new ScopeFilterSpanProcessor(next);
    await p.forceFlush();
    await p.shutdown();
    assert.equal(next.flushed, 1);
    assert.equal(next.shut, 1);
  });
  test("dropped set is exactly workflow and @vercel/otel/fetch", () => assert.deepEqual([...DROPPED_SCOPES].sort(), ["@vercel/otel/fetch", "workflow"]));
});

describe("futureAGIExportPolicy", () => {
  test("content off: redact both directions and drop principal ids", () => {
    const [policy, ...rest] = futureAGIExportPolicy({});
    assert.equal(rest.length, 0);
    const span = { attributes: {}, audience: "unknown", name: "chat x", spanId: "a", traceId: "b" } as const;
    assert.deepEqual(policy.span?.(span), { redact: true, inputs: true, outputs: true });
    for (const key of PRINCIPAL_ID_KEYS) assert.deepEqual(policy.attribute?.({ key, span, value: "alice@example.com" }), { emit: false });
    assert.deepEqual(policy.attribute?.({ key: "agent.principal.current.type", span, value: "user" }), { emit: true });
    assert.deepEqual(policy.attribute?.({ key: "gen_ai.request.model", span, value: "m" }), { emit: true });
  });
  test("FI_CAPTURE_CONTENT=1: no policy (content up to eve's own ceiling)", () => assert.deepEqual(futureAGIExportPolicy({ FI_CAPTURE_CONTENT: "1" }), []));
});

describe("exporter on the wire", () => {
  let rec: Awaited<ReturnType<typeof startRecorder>>;
  before(async () => { rec = await startRecorder({ port: 0 }); });
  after(() => rec.server.close());

  test("URL, both headers, protobuf, uncompressed, workflow dropped, project_name on the resource", async () => {
    rec.requests.length = 0;
    const exporter = futureAGIExporter({ FI_BASE_URL: `http://127.0.0.1:${rec.port}/`, ...SECRET });
    const provider = new BasicTracerProvider({
      resource: resourceFromAttributes({ project_name: "unit-project", project_type: "observe" }),
      spanProcessors: [futureAGISpanProcessor(exporter)],
    });
    provider.getTracer("workflow").startSpan("workflow.execute workflowEntry").end();
    provider.getTracer("eve.agent", "0.80.0").startSpan("invoke_agent demo").end();
    await provider.forceFlush();
    await provider.shutdown();

    assert.equal(rec.requests.length, 1);
    const [req] = rec.requests;
    assert.equal(req.url, "/tracer/v1/traces");
    assert.equal(req.rawHeaders["x-api-key"], SECRET.FI_API_KEY);
    assert.equal(req.rawHeaders["x-secret-key"], SECRET.FI_SECRET_KEY);
    assert.equal(req.rawHeaders["content-type"], "application/x-protobuf");
    assert.equal(req.rawHeaders["content-encoding"], undefined);
    assert.deepEqual(req.spans.map((s: { name: string }) => s.name), ["invoke_agent demo"]);
    assert.equal(req.spans[0].scope.name, "eve.agent");
    assert.equal(req.spans[0].resource.project_name, "unit-project");
    // keys travel only as headers, never inside the payload
    assert.equal(req.body.includes(Buffer.from(SECRET.FI_API_KEY)), false);
    assert.equal(req.body.includes(Buffer.from(SECRET.FI_SECRET_KEY)), false);
  });

  test("traces URL: hosted by default, FI_BASE_URL otherwise, trailing slashes trimmed", () => {
    assert.equal(futureAGITracesUrl({}), "https://api.futureagi.com/tracer/v1/traces");
    assert.equal(futureAGITracesUrl({ FI_BASE_URL: "" }), "https://api.futureagi.com/tracer/v1/traces");
    assert.equal(futureAGITracesUrl({ FI_BASE_URL: "http://localhost:14338//" }), "http://localhost:14338/tracer/v1/traces");
  });
});

// The shipped instrumentation files, loaded the way eve loads them, with real
// SDK spans pushed through eve's own destination wrapper (export policy + our
// processor) into the recorder.
async function loadDestination(env: Record<string, string>, tag: string) {
  const saved = { ...process.env };
  Object.assign(process.env, env);
  try {
    const dest = (await import(`../agent/instrumentation/futureagi.ts?${tag}`)).default;
    const decl = (await import(`../agent/instrumentation/otel.ts?${tag}`)).default;
    return { dest, decl };
  } finally {
    for (const k of Object.keys(env)) if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k];
  }
}

async function emitTurn(spanProcessors: SpanProcessor[], projectName: string) {
  const provider = new BasicTracerProvider({
    resource: resourceFromAttributes({ project_name: projectName, project_type: "observe" }),
    spanProcessors,
  });
  provider.getTracer("workflow").startSpan("step.execute turnStep", { attributes: { "workflow.name": "x" } }).end();
  const agent = provider.getTracer("eve.agent", "0.80.0");
  agent.startSpan("invoke_agent demo", {
    attributes: {
      "gen_ai.operation.name": "invoke_agent",
      "gen_ai.input.messages": `[{"role":"user","parts":[{"content":"${MARKER}"}]}]`,
      "agent.session.title": `title ${MARKER}`,
      "agent.principal.current.id": "alice@example.com",
      "agent.principal.current.type": "user",
      "agent.trace.content.input": true,
      "agent.trace.content.output": true,
    },
  }).end();
  const chat = agent.startSpan("chat demo-model", {
    attributes: {
      "gen_ai.operation.name": "chat",
      "gen_ai.request.model": "demo-model",
      "gen_ai.usage.input_tokens": 10,
      "gen_ai.usage.output_tokens": 5,
      "gen_ai.system_instructions": `system ${MARKER}`,
      "gen_ai.output.messages": `out ${MARKER}`,
    },
  });
  chat.end();
  const tool = agent.startSpan("execute_tool get_weather", {
    attributes: { "gen_ai.tool.name": "get_weather", "gen_ai.tool.call.arguments": `{"city":"${MARKER}"}`, "gen_ai.tool.call.result": MARKER },
  });
  tool.recordException(new Error(`boom ${MARKER}`));
  tool.setStatus({ code: 2, message: `weather service unavailable for ${MARKER}` });
  tool.end();
  await provider.forceFlush();
  await provider.shutdown();
}

describe("shipped instrumentation files", () => {
  let rec: Awaited<ReturnType<typeof startRecorder>>;
  before(async () => { rec = await startRecorder({ port: 0 }); });
  after(() => rec.server.close());

  test("otel.ts declares project_name and project_type on the resource", async () => {
    const { decl } = await loadDestination({ FI_PROJECT_NAME: "from-env" }, "decl");
    assert.ok(isOtelDeclaration(decl));
    assert.deepEqual(decl.options.resource, { project_name: "from-env", project_type: "observe" });
    assert.equal(decl.options.tracePolicy, undefined, "the recipe leaves eve's capture ceiling and Workflow retention alone");
  });

  test("default: metadata only, nothing of the marker, principal id or error text leaves the process", async () => {
    rec.requests.length = 0;
    const { dest } = await loadDestination({ FI_BASE_URL: `http://127.0.0.1:${rec.port}`, ...SECRET }, "off");
    assert.ok(isOtelIntegration(dest));
    await emitTurn([...dest.spanProcessors], "unit-off");
    const spans = rec.requests.flatMap((r) => r.spans);
    assert.deepEqual(spans.map((s) => s.name).sort(), ["chat demo-model", "execute_tool get_weather", "invoke_agent demo"]);
    for (const r of rec.requests) assert.equal(r.body.includes(Buffer.from(MARKER)), false, "marker must not be on the wire");
    for (const r of rec.requests) assert.equal(r.body.includes(Buffer.from("alice@example.com")), false, "principal id must not be on the wire");
    const chat = spans.find((s) => s.name === "chat demo-model");
    assert.equal(chat.attributes["gen_ai.request.model"], "demo-model");
    assert.equal(chat.attributes["gen_ai.usage.input_tokens"], 10);
    const tool = spans.find((s) => s.name === "execute_tool get_weather");
    assert.equal(tool.status.code, 2);
    assert.equal(tool.status.message, "");
    assert.equal(tool.events.some((e: { name: string }) => e.name === "exception"), false);
    const root = spans.find((s) => s.name === "invoke_agent demo");
    assert.equal(root.attributes["agent.principal.current.type"], "user");
    assert.equal(root.attributes["agent.trace.content.input"], false);
  });

  test("FI_CAPTURE_CONTENT=1: content, principal id and error text are exported", async () => {
    rec.requests.length = 0;
    const { dest } = await loadDestination({ FI_BASE_URL: `http://127.0.0.1:${rec.port}`, FI_CAPTURE_CONTENT: "1", ...SECRET }, "on");
    await emitTurn([...dest.spanProcessors], "unit-on");
    const spans = rec.requests.flatMap((r) => r.spans);
    assert.equal(spans.some((s) => s.scope.name === "workflow"), false);
    assert.ok(rec.requests.some((r) => r.body.includes(Buffer.from(MARKER))));
    const root = spans.find((s) => s.name === "invoke_agent demo");
    assert.equal(root.attributes["agent.principal.current.id"], "alice@example.com");
    assert.match(root.attributes["gen_ai.input.messages"], new RegExp(MARKER));
    const tool = spans.find((s) => s.name === "execute_tool get_weather");
    assert.match(tool.status.message, new RegExp(MARKER));
  });
});
