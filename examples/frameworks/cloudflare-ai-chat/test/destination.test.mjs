// Unit tests for the STANDIN destination (no network). Fixture: spans workerd captured for one real chat turn
// (content off), as the Local Explorer API returns them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { anyValue, chunk, readRows, rowsToOtlp, spanKind } from "../standin/destination.mjs";

const rows = JSON.parse(readFileSync(new URL("./fixtures/local-explorer-rows.json", import.meta.url)));
const spans = (req) => req.resourceSpans.flatMap((rs) => rs.scopeSpans.flatMap((ss) => ss.spans));
const attr = (span, key) => span.attributes.find((a) => a.key === key)?.value;

test("fixture is a real turn: AIChatAgent spans plus the wrapAISDK tree", () => {
  const names = new Set(rows.map((r) => r.name));
  for (const n of ["chat_turn", "invoke_agent support-chat", "chat gpt-6-luna", "execute_tool lookup_order", "hibernatableWebSocket"]) {
    assert.ok(names.has(n), n);
  }
  assert.ok(!names.has("onChatMessage"), "there is no span named onChatMessage");
});

test("rows become one OTLP JSON request with hex ids, parents and nanosecond times", () => {
  const req = rowsToOtlp(rows);
  assert.equal(req.resourceSpans.length, 1);
  assert.deepEqual(req.resourceSpans[0].resource.attributes, [{ key: "service.name", value: { stringValue: "support-chat" } }]);
  const out = spans(req);
  assert.equal(out.length, rows.length);
  const byId = new Map(out.map((s) => [s.spanId, s]));
  for (const s of out) {
    assert.match(s.traceId, /^[0-9a-f]{32}$/);
    assert.match(s.spanId, /^[0-9a-f]{16}$/);
    assert.ok(BigInt(s.endTimeUnixNano) >= BigInt(s.startTimeUnixNano));
  }
  const agent = out.find((s) => s.name === "invoke_agent support-chat");
  assert.equal(byId.get(agent.parentSpanId).name, "chat_turn");
  const roots = out.filter((s) => !s.parentSpanId);
  assert.deepEqual(roots.map((s) => s.name), ["GET"]);
});

test("attribute values keep their types", () => {
  assert.deepEqual(anyValue(true), { boolValue: true });
  assert.deepEqual(anyValue(371), { intValue: "371" });
  assert.deepEqual(anyValue(2.667), { doubleValue: 2.667 });
  assert.deepEqual(anyValue("x"), { stringValue: "x" });
  assert.deepEqual(anyValue({ a: 1 }), { stringValue: '{"a":1}' });
  const chat = spans(rowsToOtlp(rows)).find((s) => s.name === "chat gpt-6-luna");
  assert.deepEqual(attr(chat, "gen_ai.usage.input_tokens"), { intValue: "371" });
  assert.deepEqual(attr(chat, "gen_ai.operation.name"), { stringValue: "chat" });
  assert.deepEqual(attr(chat, "gen_ai.request.stream"), { boolValue: true });
});

test("kinds, failed invocations, open spans and null attributes", () => {
  assert.equal(spanKind("http"), 2);
  assert.equal(spanKind("websocket"), 2);
  assert.equal(spanKind("fetch"), 3);
  assert.equal(spanKind("span"), 1);
  const extra = [
    { trace_id: "a".repeat(32), span_id: "b".repeat(16), parent_id: null, service: "w", name: "GET", kind: "http",
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

test("readRows asks Local Explorer for ended and open spans since a time and maps columns", async () => {
  let seen;
  const fake = async (url, init) => {
    seen = { url, body: JSON.parse(init.body) };
    return { json: async () => ({ success: true, result: { columns: ["trace_id", "name"], rows: [["t", "n"]] } }) };
  };
  const got = await readRows("http://127.0.0.1:8787/", 1792161632472, fake);
  assert.equal(seen.url, "http://127.0.0.1:8787/cdn-cgi/local/explorer/api/local/observability/query");
  assert.match(seen.body.sql, /json\(attributes\) AS attributes FROM spans WHERE start_ms >= 1792161632472/);
  assert.deepEqual(got, [{ trace_id: "t", name: "n" }]);
  await assert.rejects(readRows("http://x", 0, async () => ({ json: async () => ({ success: false, errors: [{ code: 1 }] }) })));
});
