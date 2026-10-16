// The stand-in exporter and the Think tree check, against spans recorded from a real Think 0.20.2 turn
// under `wrangler dev` (test/fixtures/*.json, marker text replaced). No network, no workerd.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { PAYLOAD_KEYS, batches, checkTree, readSpans, toOtlpJson } from "../tools/explorer.mjs";
import { forward } from "../tools/standin_destination.mjs";

const load = (name) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));
const off = load("think-0.20.2-payloads-off.json");
const on = load("think-0.20.2-payloads-on.json");
const op = (r) => r.attributes["gen_ai.operation.name"];

test("fixture holds the documented Think tree: invoke_agent > chat + execute_tool", () => {
  const r = checkTree(off, { payloads: "off", tool: true, rootConversation: true, errorType: "Error" });
  assert.deepEqual(r.problems, []);
  assert.ok(r.turns.length >= 1);
  for (const t of r.turns) {
    assert.equal(t.root, "POST");
    assert.ok(t.chats >= 1);
  }
});

test("payloads off: no message, instruction or tool payload attribute on any span", () => {
  for (const row of off) for (const k of PAYLOAD_KEYS) assert.ok(!(k in row.attributes), `${k} on ${row.name}`);
});

test("payloads on: the check fails when it expects them off, and passes when it expects them on", () => {
  assert.equal(checkTree(on, { payloads: "on", tool: true }).ok, true);
  const r = checkTree(on, { payloads: "off" });
  assert.equal(r.ok, false);
  assert.ok(r.problems.some((p) => p.includes("gen_ai.input.messages")));
});

test("checkTree reports a missing turn, a missing chat child and a detached turn", () => {
  assert.equal(checkTree([]).ok, false);
  const noChat = off.filter((r) => op(r) !== "chat");
  assert.ok(checkTree(noChat).problems.some((p) => p.includes("no chat child")));
  const turn = off.find((r) => op(r) === "invoke_agent");
  const detached = off.map((r) => (r.span_id === turn.parent_id ? { ...r, span_id: "ffffffffffffffff" } : r));
  assert.ok(checkTree(detached).problems.some((p) => p.includes("not connected")));
});

test("OTLP JSON: hex ids, parent links, nanosecond times, typed attributes, no project_name", () => {
  const body = toOtlpJson(off);
  assert.equal(body.resourceSpans.length, 1);
  const rs = body.resourceSpans[0];
  const res = Object.fromEntries(rs.resource.attributes.map((a) => [a.key, a.value]));
  assert.deepEqual(res["service.name"], { stringValue: "think-weather" });
  assert.equal(res.project_name, undefined, "the destination cannot set project_name; the collector does");
  const spans = rs.scopeSpans[0].spans;
  assert.equal(spans.length, off.length);
  const byId = new Map(spans.map((s) => [s.spanId, s]));
  for (const s of spans) {
    assert.match(s.traceId, /^[0-9a-f]{32}$/);
    assert.match(s.spanId, /^[0-9a-f]{16}$/);
    if (s.parentSpanId) assert.ok(byId.has(s.parentSpanId), `parent of ${s.name} present`);
    assert.ok(BigInt(s.endTimeUnixNano) >= BigInt(s.startTimeUnixNano));
    assert.match(s.startTimeUnixNano, /^\d{16,}$/);
  }
  const chat = spans.find((s) => s.name.startsWith("chat "));
  const attr = (s, k) => s.attributes.find((a) => a.key === k)?.value;
  assert.deepEqual(attr(chat, "gen_ai.operation.name"), { stringValue: "chat" });
  assert.ok(attr(chat, "gen_ai.usage.input_tokens").intValue, "token counts are OTLP ints");
  assert.equal(typeof attr(chat, "gen_ai.request.stream").boolValue, "boolean");
  const root = spans.find((s) => !s.parentSpanId);
  assert.equal(root.kind, 2, "the Worker request span is SERVER");
});

test("OTLP JSON: a runtime error becomes an exception event and an ERROR status", () => {
  const row = { ...off[0], outcome: "exception", error: "boom" };
  const span = toOtlpJson([row]).resourceSpans[0].scopeSpans[0].spans[0];
  assert.equal(span.status.code, 2);
  assert.equal(span.events[0].name, "exception");
  assert.deepEqual(span.events[0].attributes[0], { key: "exception.message", value: { stringValue: "boom" } });
});

test("batches never exceed the limit and keep a small trace together", () => {
  const two = [...off, ...on];
  const parts = batches(two, 100);
  assert.ok(parts.every((p) => p.length <= 100));
  assert.equal(parts.flat().length, two.length);
  const whole = batches(off, 10_000);
  assert.equal(whole.length, 1);
});

test("forward posts uncompressed OTLP JSON with the bearer header and reports statuses", async () => {
  const calls = [];
  const fakeFetch = async (url, init) => {
    const u = String(url);
    if (u.includes("/cdn-cgi/local/explorer/api/local/observability/query")) {
      const { sql } = JSON.parse(init.body);
      const offset = Number(/OFFSET (\d+)/.exec(sql)[1]);
      const page = offset === 0 ? off : [];
      const columns = ["trace_id", "span_id", "parent_id", "service", "name", "kind", "start_ms", "duration_ms", "outcome", "error", "attributes"];
      return new Response(JSON.stringify({ success: true, result: { columns, rows: page.map((r) => columns.map((c) => (c === "attributes" ? JSON.stringify(r[c]) : r[c]))) } }));
    }
    calls.push({ url: u, init });
    return new Response("{}", { status: 200 });
  };
  const result = await forward({ explorer: "http://127.0.0.1:8787", endpoint: "http://collector/v1/traces", token: "t0ken", max: 500 }, fakeFetch);
  assert.equal(result.spans, off.length);
  assert.deepEqual(result.statuses, calls.map(() => 200));
  for (const c of calls) {
    assert.equal(c.init.headers["content-type"], "application/json");
    assert.equal(c.init.headers.authorization, "Bearer t0ken");
    assert.equal(c.init.headers["content-encoding"], undefined, "Future AGI rejects gzip; nothing here compresses");
    assert.ok(JSON.parse(c.init.body).resourceSpans);
  }
});

test("readSpans pages until a short page", async () => {
  let pages = 0;
  const fakeFetch = async (_url, init) => {
    pages++;
    const offset = Number(/OFFSET (\d+)/.exec(JSON.parse(init.body).sql)[1]);
    const rows = offset < 4 ? [["t", `s${offset}`, null, "w", "n", "span", 1, 1, "ok", null, "{}"], ["t", `s${offset + 1}`, null, "w", "n", "span", 1, 1, "ok", null, "{}"]] : [];
    const columns = ["trace_id", "span_id", "parent_id", "service", "name", "kind", "start_ms", "duration_ms", "outcome", "error", "attributes"];
    return new Response(JSON.stringify({ success: true, result: { columns, rows } }));
  };
  const rows = await readSpans("http://x", fakeFetch, 2);
  assert.equal(rows.length, 4);
  assert.equal(pages, 3);
});
