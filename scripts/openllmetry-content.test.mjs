import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../src/pages/docs/integrations/otel/openllmetry.mdx", import.meta.url),
  "utf8",
);

// Page contract only. OTLP wire and collector conversion evidence are recorded
// separately; these checks do not claim that Cloud runs a particular collector.
test("GenAI messages and decorator payloads have distinct storage guidance", () => {
  assert.match(page, /collectors with GenAI message mapping/i);
  assert.match(page, /`gen_ai\.input\.messages` and `gen_ai\.output\.messages`/);
  assert.match(page, /`traceloop\.entity\.input` and `traceloop\.entity\.output`/);
  assert.doesNotMatch(page, /Input and Output columns[^\n]*(?:stay empty|are empty)/i);
  assert.doesNotMatch(page, /collector fills them only from/);
});

test("setup uses native span attributes and disables unsupported signals", () => {
  assert.match(page, /use_attributes=True/);
  assert.match(page, /TRACELOOP_METRICS_ENABLED=false/);
  assert.match(page, /TRACELOOP_LOGGING_ENABLED=false/);
});

test("privacy defaults remain content off without promising error redaction", () => {
  assert.match(page, /TRACELOOP_TRACE_CONTENT=false/);
  assert.match(page, /exception\/status text/);
  assert.match(page, /base64 images/);
  assert.match(page, /telemetry_enabled=False/);
});

test("native SDK initialization is the only instrumentation and export route", () => {
  assert.equal((page.match(/Traceloop\.init\(/g) ?? []).length, 1);
  assert.match(page, /Do not instrument the same client with both/);
  assert.doesNotMatch(page, /pip install[^\n]*(?:traceAI-|openinference-)/i);
  assert.doesNotMatch(page, /class \w+(?:Processor|Exporter)/);
});

test("decorator limitation is explicit rather than hidden by content fix", () => {
  assert.match(page, /does not read `traceloop\.span\.kind`/);
  assert.match(page, /decorator spans show as `unknown`/);
  assert.match(page, /not promoted to the Input and Output fields/);
});
