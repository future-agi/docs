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
  assert.match(page, /does not infer a tool type from `gen_ai\.tool\.name`/);
  assert.match(page, /not promoted to the Input and Output fields/);
});

test("native export trade-off states the user-visible filtering limitation", () => {
  assert.match(page, /deliberately keeps OpenLLMetry's native export/);
  assert.match(page, /no automatic decorator classification/);
  assert.match(page, /observation-type filter for `tool` will not include the unannotated/);
  assert.match(page, /classification limitation, not a missing span/);
});

test("optional tool classification annotates the existing span without another SDK", () => {
  const python = [...page.matchAll(/```python\n([\s\S]*?)```/g)].map((match) => match[1]);
  assert.equal(python.length, 3);
  assert.match(python[2], /from opentelemetry import trace/);
  assert.match(python[2], /@tool\(name="lookup_policy"\)/);
  assert.match(python[2], /trace\.get_current_span\(\)\.set_attribute\("gen_ai\.operation\.name", "execute_tool"\)/);
  assert.doesNotMatch(python[2], /start_span|start_as_current_span|TracerProvider|Exporter|Processor|Traceloop\.init/);
  assert.match(page, /Replace `lookup_policy` in step 4/);
  assert.match(page, /v1\.58\.0 maps `gen_ai\.operation\.name=execute_tool` to `tool`/);
  assert.match(page, /annotation changes classification only, not content capture or Input\/Output mapping/);
  assert.match(page, /other decorator spans remain `unknown`/);
});
