// The page shows these files in full. Fail when the page and the tested files drift apart.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const here = (p) => new URL(p, import.meta.url);
const page = readFileSync(here("../../../../src/pages/docs/integrations/frameworks/cloudflare-think.mdx"), "utf8");

function block(title) {
  const m = new RegExp("```[a-z]+ title=\"" + title.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&") + "\"\\n([\\s\\S]*?)\\n```").exec(page);
  assert.ok(m, `page has a code block titled ${title}`);
  return m[1];
}

for (const file of ["wrangler.jsonc", "src/agent.ts", "src/index.ts", "otelcol.yaml"]) {
  test(`page block ${file} equals the example file`, () => {
    assert.equal(block(file), readFileSync(here(`../${file}`), "utf8").replace(/\n$/, ""));
  });
}

test("the page states the tested versions that package.json pins", () => {
  const pkg = JSON.parse(readFileSync(here("../package.json"), "utf8"));
  for (const [name, version] of Object.entries({ ...pkg.dependencies, ...pkg.devDependencies })) {
    if (name === "yaml") continue; // test-only
    assert.ok(page.includes(version), `${name} ${version} on the page`);
  }
  assert.ok(page.includes("otel/opentelemetry-collector-contrib:0.162.0"));
});

test("the page flags the stand-in and never claims a live Cloudflare export", () => {
  assert.match(page, /Cloudflare's OTLP destination exporter was a stand-in/);
  assert.match(page, /No Cloudflare account was used/);
});

test("no key-looking literal on the page", () => {
  assert.doesNotMatch(page, /\b(sk-[A-Za-z0-9]{10,}|[0-9a-f]{40,})\b/);
});
