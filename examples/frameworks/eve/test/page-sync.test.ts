// The docs page shows the three recipe files in full. Keep them identical to
// the files this example runs, so the tested code is the published code.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

const page = new URL("../../../../src/pages/docs/integrations/frameworks/eve.mdx", import.meta.url);
const FILES = ["agent/instrumentation/otel.ts", "agent/instrumentation/futureagi.ts", "agent/lib/futureagi.ts"];

function firstBlock(mdx: string, title: string): string | undefined {
  const fence = "```ts title=\"" + title + "\"\n";
  const i = mdx.indexOf(fence);
  if (i < 0) return undefined;
  const start = i + fence.length;
  return mdx.slice(start, mdx.indexOf("\n```", start) + 1);
}

test("the docs page shows the shipped recipe files verbatim", { skip: !existsSync(page) && "docs page not present" }, () => {
  const mdx = readFileSync(page, "utf8");
  for (const file of FILES) {
    const shown = firstBlock(mdx, file);
    assert.ok(shown, `${file} is not on the page`);
    assert.equal(shown, readFileSync(new URL(`../${file}`, import.meta.url), "utf8"), `${file} differs from the page`);
  }
});
