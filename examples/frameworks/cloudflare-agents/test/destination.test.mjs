// Unit tests for the STANDIN destination (no network). Fixture: what workerd captured for one real turn of the
// example Agent (content off), as the Local Explorer API returns it: spans plus the log lines attributed to them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { anyValue, chunk, readLogs, readRows, rowsToOtlp, spanKind } from "../standin/destination.mjs";

const { spans: rows, logs } = JSON.parse(readFileSync(new URL("./fixtures/local-explorer-happy.json", import.meta.url)));
const spans = (req) => req.resourceSpans.flatMap((rs) => rs.scopeSpans.flatMap((ss) => ss.spans));
const attr = (span, key) => span.attributes.find((a) => a.key === key)?.value;

test("fixture is a real turn: Agent lifecycle spans plus the wrapAISDK tree", () => {
  const names = new Set(rows.map((r) => r.name));
  for (const n of ["agent_start", "invoke_agent weather-agent", "chat gpt-6-luna", "execute_tool get_weather", "tool_approval get_weather"]) {
    assert.ok(names.has(n), n);
  }
  assert.ok(rows.some((r) => r.name.startsWith("durable_object_storage_")), "storage spans are in what workerd records");
  assert.ok(logs.length > 0);
});

test("rows become one OTLP JSON request with hex ids, parents and nanosecond times", () => {
  const req = rowsToOtlp(rows);
  assert.equal(req.resourceSpans.length, 1);
  assert.deepEqual(req.resourceSpans[0].resource.attributes, [{ key: "service.name", value: { stringValue: "weather-agent" } }]);
  const out = spans(req);
  assert.equal(out.length, rows.length);
  const byId = new Map(out.map((s) => [s.spanId, s]));
  for (const s of out) {
    assert.match(s.traceId, /^[0-9a-f]{32}$/);
    assert.match(s.spanId, /^[0-9a-f]{16}$/);
    assert.ok(BigInt(s.endTimeUnixNano) >= BigInt(s.startTimeUnixNano));
  }
  const agent = out.find((s) => s.name === "invoke_agent weather-agent");
  const parent = byId.get(agent.parentSpanId);
  assert.equal(parent.name, "POST", "invoke_agent runs inside the Agent's request invocation");
  for (const child of ["chat gpt-6-luna", "execute_tool get_weather"]) {
    assert.ok(out.some((s) => s.name === child && s.parentSpanId === agent.spanId), child);
  }
  const tool = out.find((s) => s.name === "execute_tool get_weather");
  assert.equal(out.find((s) => s.name === "tool_approval get_weather").parentSpanId, tool.spanId);
  const roots = out.filter((s) => !s.parentSpanId);
  assert.deepEqual(roots.map((s) => s.name), ["POST"]);
  assert.equal(attr(roots[0], "gen_ai.conversation.id").stringValue, attr(agent, "gen_ai.conversation.id").stringValue,
    "the Worker puts the Agent's conversation id on the trace root");
});

test("attribute values keep their types", () => {
  assert.deepEqual(anyValue(true), { boolValue: true });
  assert.deepEqual(anyValue(365), { intValue: "365" });
  assert.deepEqual(anyValue(2.667), { doubleValue: 2.667 });
  assert.deepEqual(anyValue("x"), { stringValue: "x" });
  assert.deepEqual(anyValue({ a: 1 }), { stringValue: '{"a":1}' });
  const chat = spans(rowsToOtlp(rows)).find((s) => s.name === "chat gpt-6-luna");
  assert.deepEqual(attr(chat, "gen_ai.usage.input_tokens"), { intValue: "365" });
  assert.deepEqual(attr(chat, "gen_ai.operation.name"), { stringValue: "chat" });
});

test("log lines become span events on the span they are attributed to", () => {
  const out = spans(rowsToOtlp(rows, logs));
  const withEvents = out.filter((s) => s.events);
  assert.equal(withEvents.reduce((n, s) => n + s.events.length, 0), logs.filter((l) => l.span_id).length);
  const ev = withEvents[0].events[0];
  assert.equal(ev.name, "log");
  assert.deepEqual(ev.attributes.map((a) => a.key), ["level", "message"]);
  assert.equal(spans(rowsToOtlp(rows)).filter((s) => s.events).length, 0, "no logs, no events");
});

test("kinds, failed invocations, open spans and null attributes", () => {
  assert.equal(spanKind("http"), 2);
  assert.equal(spanKind("do"), 3);
  assert.equal(spanKind("fetch"), 3);
  assert.equal(spanKind("span"), 1);
  const extra = [
    { trace_id: "a".repeat(32), span_id: "b".repeat(16), parent_id: null, service: "w", name: "POST", kind: "http",
      start_ms: 1000, duration_ms: 5, outcome: "exception", error: "boom", attributes: null },
    { trace_id: "a".repeat(32), span_id: "c".repeat(16), parent_id: "b".repeat(16), service: "w", name: "open", kind: "span",
      start_ms: 1001, duration_ms: null, outcome: null, error: null, attributes: "{}" },
  ];
  const out = spans(rowsToOtlp(extra));
  assert.equal(out.length, 1, "a span that has not ended is not exported");
  assert.deepEqual(out[0].status, { code: 2, message: "boom" });
  assert.deepEqual(out[0].attributes, []);
  assert.equal(out[0].startTimeUnixNano, "1000000000");
  assert.equal(out[0].endTimeUnixNano, "1005000000");
});

test("chunking keeps every span once", () => {
  const req = rowsToOtlp(rows);
  const parts = chunk(req, 10);
  assert.equal(parts.length, Math.ceil(rows.length / 10));
  assert.equal(parts.flatMap(spans).length, rows.length);
});

test("readRows / readLogs query the Local Explorer API and map columns", async () => {
  const seen = [];
  const fake = async (url, init) => {
    seen.push({ url, body: JSON.parse(init.body) });
    return { json: async () => ({ success: true, result: { columns: ["trace_id", "name"], rows: [["t", "n"]] } }) };
  };
  assert.deepEqual(await readRows("http://127.0.0.1:8787/", 1792161632472, fake), [{ trace_id: "t", name: "n" }]);
  await readLogs("http://127.0.0.1:8787", 5, fake);
  assert.equal(seen[0].url, "http://127.0.0.1:8787/cdn-cgi/local/explorer/api/local/observability/query");
  assert.match(seen[0].body.sql, /json\(attributes\) AS attributes FROM spans WHERE start_ms >= 1792161632472/);
  assert.match(seen[1].body.sql, /FROM logs WHERE ts_ms >= 5/);
  await assert.rejects(readRows("http://x", 0, async () => ({ json: async () => ({ success: false, errors: [{ code: 1 }] }) })));
});
