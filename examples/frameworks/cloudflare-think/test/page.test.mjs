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

test("the page states the live verification and lists the runtime scope", () => {
  assert.match(page, /Live vendor verification \(2026-10-18\)/);
  for (const t of ["useAgentChat", "sub-agents", "`tool_approval`", "sampling below 1", "creating the destination in the dashboard"]) {
    assert.ok(page.includes(t), t);
  }
});

test("the page documents the three fixes the live export needed", () => {
  for (const t of ["filter/preflight", "url.query", "think.turn.input_tokens"]) assert.ok(page.includes(t), t);
});

test("no key-looking literal on the page", () => {
  assert.doesNotMatch(page, /\b(sk-[A-Za-z0-9]{10,}|[0-9a-f]{40,})\b/);
});


test("deploy setup configures the model vars, secret and collector opt-in", () => {
  const config = JSON.parse(readFileSync(here("../wrangler.jsonc"), "utf8"));
  assert.equal(config.vars.MODEL, "gpt-4o-mini");
  assert.equal(config.vars.OPENAI_BASE_URL, "https://api.openai.com/v1");
  assert.ok(!("OPENAI_API_KEY" in config.vars));
  assert.ok(page.indexOf("npx wrangler secret put OPENAI_API_KEY") < page.indexOf("npx wrangler deploy\n"));
  assert.ok(page.includes('-e FI_CAPTURE_CONTENT="${FI_CAPTURE_CONTENT:-false}"'));
  assert.ok(page.includes("docker rm -f futureagi-otelcol"));
  for (const [name, version] of Object.entries(JSON.parse(readFileSync(here("../package.json"), "utf8")).dependencies)) {
    assert.ok(page.includes(`${name}@${version}`));
  }
  assert.doesNotMatch(page, /not tested|untested|unverified/i);
});
