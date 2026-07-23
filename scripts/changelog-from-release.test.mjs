import { test } from "node:test";
import assert from "node:assert/strict";
import { transform, insert } from "./changelog-from-release.mjs";

const RELEASE_BODY = `## [2.1.0](https://github.com/future-agi/future-agi/compare/v2.0.0...v2.1.0) (2026-08-01)

### ⚠ BREAKING CHANGES

* **api:** remove deprecated /v1/eval endpoint

### Features

* **observe:** session-level trace grouping ([#901](https://github.com/future-agi/future-agi/pull/901))
* **gateway:** streaming responses ([#905](https://github.com/future-agi/future-agi/pull/905))

### Bug Fixes

* **tracer:** off-by-one in span pagination ([#903](https://github.com/future-agi/future-agi/pull/903))

### Chores

* bump deps ([#900](https://github.com/future-agi/future-agi/pull/900))
`;

test("transform maps release-please sections to changelog sections", () => {
  const s = transform("v2.1.0", RELEASE_BODY, new Date("2026-08-01T00:00:00Z"));
  assert.match(s, /^## v2\.1\.0 - August 2026/m);
  assert.match(s, /^### New Features/m);
  assert.match(s, /session-level trace grouping/);
  assert.match(s, /^### Bug Fixes/m);
  assert.match(s, /^### Breaking Changes/m);
  assert.match(s, /remove deprecated \/v1\/eval endpoint/);
  assert.doesNotMatch(s, /Chores/);
  assert.doesNotMatch(s, /bump deps/);
  assert.match(s, /---\s*$/);
});

test("insert places section after marker and preserves the rest", () => {
  const changelog = `intro\n\n{/* changelog:insert-below — automation inserts new releases here; do not remove */}\n\n## v2.0.0 - July 2026\nold entry\n`;
  const out = insert(changelog, "## v2.1.0 - August 2026\nnew\n\n---");
  const iMarker = out.indexOf("changelog:insert-below");
  const iNew = out.indexOf("## v2.1.0");
  const iOld = out.indexOf("## v2.0.0");
  assert.ok(iMarker < iNew && iNew < iOld);
});

test("insert throws when marker missing", () => {
  assert.throws(() => insert("no marker here", "x"), /marker not found/);
});
