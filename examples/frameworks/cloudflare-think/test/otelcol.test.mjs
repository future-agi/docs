// Static checks on otelcol.yaml. The behaviour (project stamp, span types, content guard) is proven
// end to end by run_e2e.sh; these catch an edit that silently weakens the shipped config.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { parse } from "yaml";

const text = readFileSync(new URL("../otelcol.yaml", import.meta.url), "utf8");
const cfg = parse(text);
const pipeline = cfg.service.pipelines.traces;
const stmts = cfg.processors["transform/think"].trace_statements;
const spanStmts = stmts.find((s) => s.context === "span").statements;
const OFF = '"${env:FI_CAPTURE_CONTENT:-false}" != "true"';
const ON = '"${env:FI_CAPTURE_CONTENT:-false}" == "true"';

test("no self-metrics and no compression towards Future AGI", () => {
  assert.equal(cfg.service.telemetry.metrics.level, "none");
  const exp = cfg.exporters["otlp_http/future_agi"];
  assert.equal(exp.compression, "none");
  assert.deepEqual(Object.keys(exp.headers).sort(), ["X-Api-Key", "X-Secret-Key"]);
  assert.equal(exp.headers["X-Api-Key"], "${env:FI_API_KEY}");
  assert.equal(exp.headers["X-Secret-Key"], "${env:FI_SECRET_KEY}");
  assert.deepEqual(pipeline.exporters, ["otlp_http/future_agi"]);
});

test("the receiver is OTLP/HTTP behind a bearer token, and no key is written in the file", () => {
  assert.equal(cfg.receivers.otlp.protocols.http.auth.authenticator, "bearertokenauth/cloudflare");
  assert.equal(cfg.receivers.otlp.protocols.grpc, undefined);
  assert.equal(cfg.extensions["bearertokenauth/cloudflare"].token, "${env:COLLECTOR_TOKEN}");
  assert.ok(cfg.service.extensions.includes("bearertokenauth/cloudflare"));
  assert.doesNotMatch(text.replace(/\$\{env:[A-Z_]+(:-[a-z]+)?\}/g, ""), /(sk-|Bearer [A-Za-z0-9]{8,})/);
});

test("project_name is set on the RESOURCE, before anything is exported", () => {
  const res = cfg.processors["resource/future_agi"].attributes;
  const pn = res.find((a) => a.key === "project_name");
  assert.equal(pn.value, "${env:FI_PROJECT_NAME}");
  assert.equal(pn.action, "upsert");
  assert.ok(res.find((a) => a.key === "project_type" && a.value === "observe"));
  assert.ok(pipeline.processors.indexOf("resource/future_agi") < pipeline.processors.indexOf("batch"));
});

test("Think's three operations get Observe span types; conversation becomes the session; error.type becomes ERROR", () => {
  for (const [op, kind] of [["invoke_agent", "AGENT"], ["chat", "LLM"], ["execute_tool", "TOOL"]]) {
    assert.ok(spanStmts.includes(`set(attributes["fi.span.kind"], "${kind}") where attributes["gen_ai.operation.name"] == "${op}"`), op);
  }
  assert.ok(spanStmts.some((s) => s.startsWith('set(attributes["session.id"], attributes["gen_ai.conversation.id"])')));
  assert.ok(spanStmts.includes('set(status.code, STATUS_CODE_ERROR) where attributes["error.type"] != nil'));
});

test("content is off unless FI_CAPTURE_CONTENT=true: every payload copy is gated ON, every delete gated OFF", () => {
  const copies = spanStmts.filter((s) => s.startsWith('set(attributes["input.value"]') || s.startsWith('set(attributes["output.value"]'));
  assert.equal(copies.length, 4);
  for (const s of copies) assert.ok(s.endsWith(ON), s);
  const del = spanStmts.find((s) => s.startsWith("delete_matching_keys") && s.includes("messages"));
  for (const k of ["input\\\\.messages", "output\\\\.messages", "system_instructions", "tool\\\\.call\\\\.arguments", "tool\\\\.call\\\\.result"]) {
    assert.ok(del.includes(k), k);
  }
  assert.ok(del.endsWith(OFF));
  assert.ok(spanStmts.some((s) => s.startsWith("set(status.message") && s.endsWith(OFF)));
  const ev = stmts.find((s) => s.context === "spanevent").statements;
  assert.ok(ev.every((s) => s.endsWith(OFF)));
  assert.ok(cfg.processors["filter/span_events"].traces.spanevent[0].endsWith(OFF));
  // the copies must run before the delete, or content ON would copy nothing
  assert.ok(spanStmts.indexOf(copies.at(-1)) < spanStmts.indexOf(del));
});

test("query strings are always cut: from url.full, and url.query is deleted (the real Workers export has both)", () => {
  const s = spanStmts.find((x) => x.startsWith('replace_pattern(attributes["url.full"]'));
  assert.ok(s);
  assert.ok(!s.includes("FI_CAPTURE_CONTENT"), "not tied to the content switch: query strings can hold keys");
  assert.ok(spanStmts.includes('delete_key(attributes, "url.query")'), "unconditional delete of url.query");
});

test("invoke_agent keeps its turn totals under other names, so Future AGI counts tokens once (on chat spans)", () => {
  const agent = 'attributes["gen_ai.operation.name"] == "invoke_agent"';
  for (const k of ["input", "output"]) {
    assert.ok(spanStmts.includes(
      `set(attributes["think.turn.${k}_tokens"], attributes["gen_ai.usage.${k}_tokens"]) where ${agent} and attributes["gen_ai.usage.${k}_tokens"] != nil`), k);
  }
  const del = spanStmts.indexOf(`delete_matching_keys(attributes, "^gen_ai\\\\.usage\\\\.") where ${agent}`);
  assert.ok(del > 0, "gen_ai.usage.* deleted on invoke_agent only");
  assert.ok(spanStmts.findIndex((s) => s.startsWith('set(attributes["think.turn.')) < del, "copied before the delete");
});

test("the destination's pre-flight test span is dropped", () => {
  assert.deepEqual(cfg.processors["filter/preflight"].traces.span, ['resource.attributes["telemetry.sdk.name"] == "pre-flight-check"']);
});

test("pipeline order: drop the pre-flight and storage spans first, guard content before batching", () => {
  assert.deepEqual(pipeline.processors, ["filter/preflight", "filter/storage_spans", "resource/future_agi", "transform/think", "filter/span_events", "batch"]);
  assert.deepEqual(cfg.processors["filter/storage_spans"].traces.span, ['IsMatch(name, "^durable_object_storage_")']);
});
