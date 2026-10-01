import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Source contract only; the site build validates MDX rendering separately.
// Run with: node --test scripts/spring-ai-warning.test.mjs
const source = readFileSync(
  new URL("../src/pages/docs/integrations/traceai/spring-boot.mdx", import.meta.url),
  "utf8",
);
const warning = source.match(/<Warning>([\s\S]*?)<\/Warning>/)?.[1] ?? "";

test("warning identifies the unsupported Spring AI 1.1 path and reported linkage error", () => {
  assert.match(warning, /not a supported integration path for Spring AI `1\.1\.x`/);
  assert.match(warning, /`NoSuchMethodError` involving `Message\.getContent\(\)` has been reported/);
  assert.match(warning, /does not yet provide a verified replacement artifact coordinate/);
});

test("M4 is a historical wrapper compilation target, not a tested support range", () => {
  assert.match(warning, /M4-based traceAI wrapper was compiled against Spring AI `1\.0\.0-M4`/);
  assert.match(warning, /compilation target, not a tested support range/);
  assert.ok(!/source currently targets/i.test(source), "Do not describe the current source target");
});

test("page has no open-ended M4 compatibility range", () => {
  assert.ok(!/M4\s*\+/.test(source), "Remove the M4+ support claim");
});

test("page has no floating main-SNAPSHOT coordinate", () => {
  assert.ok(!/main-SNAPSHOT/i.test(source), "Remove the floating main-SNAPSHOT coordinate");
});

for (const [name, url] of [
  ["Spring AI 1.1 observability", "https://docs.spring.io/spring-ai/reference/1.1/observability/index.html"],
  ["Spring Boot 3.5 tracing", "https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html"],
]) {
  test(`page links to the versioned official ${name} reference`, () => {
    assert.ok(source.includes(`](${url})`), `Missing versioned reference: ${url}`);
  });
}

test("warning replaces obsolete installation examples and provider tables", () => {
  assert.ok(!/^\s*(?:```|~~~|\|)/m.test(source), "Remove code fences and tables from this notice");
  assert.ok(
    !/com\.github\.future-agi\.traceAI|traceai-spring-boot-starter|TracedChatModel|TracedEmbeddingModel/.test(source),
    "Remove obsolete dependency coordinates and wrapper examples",
  );
});
