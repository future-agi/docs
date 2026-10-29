// Measured on @apollo/server 4.13.0 + @opentelemetry/instrumentation-graphql 0.71.0 (TH-8279, E-APO-2):
// ignoreTrivialResolveSpans does NOT drop the default-resolver field spans; depth does.
// If an upgrade changes this, this test fails and the page must be updated.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const count = (mode) => {
  const out = execFileSync(process.execPath, [path.join(root, "tests", "trivial-spans.mjs"), mode], { cwd: root, encoding: "utf8" });
  return JSON.parse(out.split("\n").find((l) => l.startsWith("RESULT ")).slice(7));
};

test("E-APO-2: field spans for 20 default-resolved scalars", () => {
  const none = count("none"), trivial = count("ignoreTrivial"), depth = count("depth");
  assert.equal(none.resolveSpans, 21, "unbounded: the wide resolver plus 20 scalar fields");
  assert.equal(trivial.resolveSpans, none.resolveSpans, "ignoreTrivialResolveSpans:true drops nothing on Server 4.13.0");
  assert.equal(depth.resolveSpans, 1, "depth:1 keeps only the top-level field span");
});
