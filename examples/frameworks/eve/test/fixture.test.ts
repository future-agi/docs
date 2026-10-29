// Golden checks on the recorded trace fixture: three real eve 0.80.0 turns
// (tool call, failing tool, failing model call) exported by this recipe with
// content capture off, ids and the model name replaced. See README.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";

import { prepareReplay } from "../scripts/replay_fixture.mjs";

type AnyValue = { stringValue?: string; intValue?: string; doubleValue?: number; boolValue?: boolean; arrayValue?: { values: AnyValue[] } };
type KV = { key: string; value: AnyValue };
type OtlpSpan = {
  traceId: string; spanId: string; parentSpanId?: string; name: string; kind: number;
  startTimeUnixNano: string; endTimeUnixNano: string; attributes: KV[];
  events: { name: string; timeUnixNano: string; attributes: KV[] }[]; status: { code?: number; message?: string };
};

const fixture = JSON.parse(readFileSync(new URL("./fixtures/eve-0.80.0-turns.otlp.json", import.meta.url), "utf8"));
const rs = fixture.resourceSpans;
const spans: OtlpSpan[] = rs.flatMap((r: { scopeSpans: { spans: OtlpSpan[] }[] }) => r.scopeSpans.flatMap((s) => s.spans));
const attr = (s: OtlpSpan, k: string) => {
  const v = s.attributes.find((a) => a.key === k)?.value;
  if (!v) return undefined;
  return v.stringValue ?? (v.intValue !== undefined ? Number(v.intValue) : v.doubleValue ?? v.boolValue ?? v.arrayValue?.values.map((x) => x.stringValue));
};
const traces = new Map<string, OtlpSpan[]>();
for (const s of spans) traces.set(s.traceId, [...(traces.get(s.traceId) ?? []), s]);
const CONTENT_KEYS = [
  "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions", "gen_ai.tool.definitions",
  "gen_ai.tool.call.arguments", "gen_ai.tool.call.result", "agent.session.title", "ai.response.text",
  "ai.response.tool_calls", "agent.principal.current.id", "agent.principal.initiator.id",
];

describe("recorded eve 0.80.0 fixture", () => {
  test("one resource with project_name and project_type, one instrumentation scope eve.agent", () => {
    assert.equal(rs.length, 1);
    const keys = Object.fromEntries(rs[0].resource.attributes.map((a: KV) => [a.key, a.value.stringValue]));
    assert.equal(keys.project_name, "eve-fixture");
    assert.equal(keys.project_type, "observe");
    const scopes = rs[0].scopeSpans.map((s: { scope: { name: string; version: string } }) => s.scope);
    assert.deepEqual(scopes, [{ name: "eve.agent", version: "0.80.0" }]);
  });

  test("ids are lowercase hex of the right length", () => {
    for (const s of spans) {
      assert.match(s.traceId, /^[0-9a-f]{32}$/);
      assert.match(s.spanId, /^[0-9a-f]{16}$/);
      if (s.parentSpanId) assert.match(s.parentSpanId, /^[0-9a-f]{16}$/);
      assert.ok(BigInt(s.endTimeUnixNano) >= BigInt(s.startTimeUnixNano));
    }
  });

  test("three traces, each rooted at invoke_agent with agent.step children", () => {
    assert.equal(traces.size, 3);
    for (const t of traces.values()) {
      const roots = t.filter((s) => !s.parentSpanId);
      assert.equal(roots.length, 1);
      assert.match(roots[0].name, /^invoke_agent /);
      assert.equal(attr(roots[0], "gen_ai.operation.name"), "invoke_agent");
      for (const step of t.filter((s) => s.name === "agent.step")) assert.equal(step.parentSpanId, roots[0].spanId);
      for (const s of t.filter((x) => x.name.startsWith("chat ") || x.name.startsWith("execute_tool "))) {
        assert.equal(t.find((p) => p.spanId === s.parentSpanId)?.name, "agent.step");
      }
    }
  });

  test("chat spans are CLIENT spans with model and token usage", () => {
    const chats = spans.filter((s) => s.name.startsWith("chat "));
    assert.equal(chats.length, 5);
    for (const c of chats) {
      assert.equal(c.kind, 3);
      assert.equal(attr(c, "gen_ai.operation.name"), "chat");
      assert.equal(attr(c, "gen_ai.request.model"), "example-model");
      if (c.status.code !== 2) assert.ok((attr(c, "gen_ai.usage.input_tokens") as number) > 0);
    }
  });

  test("tool spans carry the tool name and call id, not arguments or results", () => {
    const tools = spans.filter((s) => s.name === "execute_tool get_weather");
    assert.equal(tools.length, 2);
    for (const t of tools) {
      assert.equal(attr(t, "gen_ai.tool.name"), "get_weather");
      assert.match(String(attr(t, "gen_ai.tool.call.id")), /^call_\d{4}$/);
    }
  });

  test("failures are ERROR with no message and no exception event", () => {
    const failed = spans.filter((s) => s.status.code === 2);
    assert.deepEqual(failed.map((s) => s.name).sort(), ["agent.step", "chat example-model", "execute_tool get_weather", "invoke_agent eve-futureagi-example"]);
    for (const s of failed) {
      assert.equal(s.status.message, undefined);
      assert.ok(s.events.every((e) => e.name !== "exception"));
    }
    assert.equal(attr(failed.find((s) => s.name.startsWith("execute_tool"))!, "error.type"), "ACTION_RESULT_FAILED");
  });

  test("no content, principal ids, local paths, hosts or users", () => {
    const text = JSON.stringify(fixture);
    for (const s of spans) for (const k of CONTENT_KEYS) assert.equal(attr(s, k), undefined, `${s.name} has ${k}`);
    for (const needle of ["/Users/", "/home/", "127.0.0.1", "localhost", "Traceback", "node_modules", "@", "Bearer"]) {
      assert.equal(text.includes(needle), false, needle);
    }
  });

  test("replay preparation renames the project and issues fresh ids at the current time", () => {
    const now = 2_000_000_000_000_000_000n;
    const { request, traceIds } = prepareReplay(fixture, { projectName: "replayed", nowNs: now });
    const out: OtlpSpan[] = request.resourceSpans[0].scopeSpans[0].spans;
    assert.equal(traceIds.length, 3);
    assert.equal(request.resourceSpans[0].resource.attributes.find((a: KV) => a.key === "project_name").value.stringValue, "replayed");
    assert.equal(out.reduce((m, s) => (BigInt(s.endTimeUnixNano) > m ? BigInt(s.endTimeUnixNano) : m), 0n), now);
    const old = new Set(spans.map((s) => s.spanId));
    assert.ok(out.every((s) => !old.has(s.spanId)));
    const ids = new Set(out.map((s) => s.spanId));
    assert.ok(out.every((s) => !s.parentSpanId || ids.has(s.parentSpanId)), "parent links survive the id rewrite");
    assert.equal(JSON.stringify(fixture).includes("replayed"), false, "the fixture itself is not mutated");
  });
});
