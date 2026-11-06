// The run_e2e.sh wire checks, on a synthetic run: all pass on a good run, and
// each guarded defect turns its own check red.
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { checkRun } from "../scripts/check_wire.mjs";

const markers = { project: "p", off: "EVEOFFaaaa", model: "EVEERRbbbb", on: "EVEONcccc" };
const resource = (project = "p") => ({ project_name: project, project_type: "observe" });
const span = (traceId: string, spanId: string, parentSpanId: string, name: string, extra: Record<string, unknown> = {}) => ({
  resource: resource(), scope: { name: "eve.agent", version: "0.80.0" }, traceId, spanId, parentSpanId, name,
  attributes: {}, events: [], status: { code: 0, message: "" }, ...extra,
});
const chat = (t: string, id: string, parent: string, extra = {}) =>
  span(t, id, parent, "chat m", { attributes: { "gen_ai.request.model": "m", "gen_ai.usage.input_tokens": 5 }, ...extra });

function goodRun() {
  const off = [
    span("t1", "r1", "", "invoke_agent a"), span("t1", "s1", "r1", "agent.step"), span("t1", "s2", "r1", "agent.step"),
    chat("t1", "c1", "s1"), chat("t1", "c2", "s2"), span("t1", "x1", "s1", "execute_tool get_weather"),
    span("t2", "r2", "", "invoke_agent a"), span("t2", "s3", "r2", "agent.step"),
    span("t2", "x2", "s3", "execute_tool get_weather", { status: { code: 2, message: "" } }),
    span("t3", "r3", "", "invoke_agent a", { status: { code: 2, message: "" } }),
    chat("t3", "c3", "r3", { status: { code: 2, message: "" } }),
  ];
  const on = [{ ...span("t4", "r4", "", "invoke_agent a"), resource: resource("p-optin") },
    { ...chat("t4", "c4", "r4", { attributes: { "gen_ai.input.messages": markers.on, "gen_ai.request.model": "m", "gen_ai.usage.input_tokens": 5 } }), resource: resource("p-optin") }];
  const req = (spans: unknown[], raw: string) => ({
    file: "req.json",
    meta: { spans, decodeError: null, forwardStatus: 200, headers: { "x-api-key": "<set:13 chars>", "x-secret-key": "<set:16 chars>" } },
    raw: Buffer.from(raw),
  });
  const invokes: Record<string, unknown> = {
    "off.ok": { traceId: "t1", status: "completed" }, "off.toolerr": { traceId: "t2", status: "completed" },
    "model.err": { traceId: "t3", status: "failed" }, "on.ok": { traceId: "t4", status: "completed" },
  };
  return {
    requests: [req(off, "metadata only"), req(on, `content ${markers.on}`)],
    markers,
    invoke: (name: string) => invokes[name] ?? null,
  };
}

const failing = (run: ReturnType<typeof goodRun>) => checkRun(run).filter((r: { ok: boolean }) => !r.ok).map((r: { name: string }) => r.name);

describe("check_wire", () => {
  test("a good run passes every check", () => assert.deepEqual(failing(goodRun()), []));

  test("content-off marker on the wire fails the privacy check", () => {
    const run = goodRun();
    run.requests[0].raw = Buffer.from(`leak ${markers.off}`);
    assert.deepEqual(failing(run), ["off: marker absent from every request body"]);
  });

  test("a workflow span fails the scope check", () => {
    const run = goodRun();
    run.requests[0].meta.spans.push({ ...span("t9", "w1", "", "workflow.execute x"), scope: { name: "workflow", version: "" } });
    assert.ok(failing(run).includes("only eve.agent spans exported (workflow dropped)"));
  });

  test("a tool failure exported as OK fails the error check", () => {
    const run = goodRun();
    const spans = run.requests[0].meta.spans as { spanId: string; status: { code: number } }[];
    spans.find((s) => s.spanId === "x2")!.status.code = 0;
    assert.ok(failing(run).includes("off: failing tool span has status ERROR"));
  });

  test("an exported error message fails the redaction check", () => {
    const run = goodRun();
    const spans = run.requests[0].meta.spans as { spanId: string; status: { message: string } }[];
    spans.find((s) => s.spanId === "x2")!.status.message = "weather service unavailable";
    assert.deepEqual(failing(run), ["off: error text and exception events redacted"]);
  });

  test("a gzip-encoded request fails the compression check", () => {
    const run = goodRun();
    (run.requests[0].meta.headers as Record<string, string>)["content-encoding"] = "gzip";
    assert.deepEqual(failing(run), ["no request is compressed"]);
  });

  test("a missing opt-in marker fails the opt-in check", () => {
    const run = goodRun();
    run.requests[1].raw = Buffer.from("nothing");
    assert.deepEqual(failing(run), ["on: marker exported when FI_CAPTURE_CONTENT=1"]);
  });
});
