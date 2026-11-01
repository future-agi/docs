import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/docs/integrations/langsmith.mdx", import.meta.url), "utf8");
const typescript = page.match(/<Tab title="TypeScript">([\s\S]*?)<\/Tab>/)?.[1] ?? "";

test("LangSmith offers a pinned native TypeScript route, not a wrapper", () => {
  assert.match(typescript, /langsmith@0\.11\.6/);
  assert.match(typescript, /langsmith\/experimental\/otel\/setup/);
  assert.match(typescript, /trace\.setGlobalTracerProvider\(provider\);\s*initializeOTEL\(\{ globalTracerProvider: provider \}\)/);
  assert.match(typescript, /project_name: process\.env\.FI_PROJECT_NAME/);
  assert.match(typescript, /project_type: "observe"/);
  assert.doesNotMatch(typescript, /@traceai\/langsmith|class\s+\w+Exporter/);
});

test("TypeScript shutdown drains the same native client before its provider", () => {
  assert.match(typescript, /tracingMode: "otel"/);
  assert.match(typescript, /run_type: "tool", client/);
  assert.match(typescript, /run_type: "chain", client/);
  assert.match(typescript, /await client\.flush\(\);[\s\S]*await provider\.shutdown\(\);/);
});

test("language-specific discovery, mode and privacy constraints stay visible", () => {
  assert.match(typescript, /\/info/);
  assert.match(typescript, /does not support.*hybrid/);
  assert.match(typescript, /deprecated/);
  assert.match(typescript, /hideInputs: true/);
  assert.match(typescript, /hideOutputs: true/);
  assert.match(typescript, /hideMetadata: true/);
  assert.match(typescript, /exception messages and stack traces/);
  assert.match(page, /<Tab title="Python">/);
  assert.match(page, /langsmith\[otel\]==0\.14\.4/);
});
