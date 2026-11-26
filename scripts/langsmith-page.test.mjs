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

test("native TypeScript support excludes async generators before setup", () => {
  const prerequisites = typescript.split("## 1. Install")[0];
  assert.match(prerequisites, /<Warning>[\s\S]*non-streaming functions/);
  assert.match(prerequisites, /async generators[\s\S]*even when fully consumed/);
  assert.match(prerequisites, /early cancellation[\s\S]*errors/);
  assert.match(prerequisites, /\[traceAI LangChain\]\(\/docs\/integrations\/traceai\/langchain\)/);
  assert.match(prerequisites, /instead of[\s\S]*native.*route/);
  assert.match(prerequisites, /not a drop-in replacement for arbitrary.*traceable/);
  assert.match(prerequisites, /consume streams to completion/);
  assert.match(prerequisites, /Early cancellation can leave spans unfinished there too/);
  const captured = typescript.split("## What is captured")[1].split("## Privacy")[0];
  assert.match(captured, /Each traced non-streaming function/);
  assert.match(captured, /Failed non-streaming functions/);
  assert.match(typescript, /\*\*Missing streaming spans or errors\.\*\*/);
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
