import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("the page installs the companion's tested dependency versions", () => {
  const page = readFileSync(
    new URL("../../../../src/pages/docs/integrations/frameworks/apollo-graphql.mdx", import.meta.url),
    "utf8",
  );
  const { dependencies } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  const command = page.match(/```bash\n(npm install[^]*?)\n```/);
  assert.ok(command, "the page must contain its npm install command");
  const packages = command[1].replace(/\\\n/g, " ").trim().split(/\s+/).slice(2);
  const installed = {};
  for (const spec of packages) {
    const at = spec.lastIndexOf("@");
    assert.ok(at > 0, `${spec} must have an explicit version`);
    installed[spec.slice(0, at)] = spec.slice(at + 1);
  }
  assert.deepEqual(installed, dependencies);
});
