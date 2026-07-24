import { test } from "node:test";
import assert from "node:assert/strict";
import { transform, insert, escapeMdx } from "./changelog-from-release.mjs";

const RELEASE_BODY = `## [1.23.1](https://github.com/future-agi/future-agi/compare/v1.23.0...v1.23.1) (2026-08-01)

### ⚠ BREAKING CHANGES

* **api:** remove deprecated /v1/eval endpoint

### Features

* **observe:** session-level trace grouping ([#901](https://github.com/future-agi/future-agi/pull/901))
* **gateway:** streaming responses ([#905](https://github.com/future-agi/future-agi/pull/905))

### Bug Fixes

* **tracer:** off-by-one in span pagination ([#903](https://github.com/future-agi/future-agi/pull/903))

### Performance Improvements

* **eval-task:** batch ClickHouse reads ([#907](https://github.com/future-agi/future-agi/pull/907))

### Chores

* bump deps ([#900](https://github.com/future-agi/future-agi/pull/900))
`;

test("transform emits release-notes page format with merged buckets", () => {
  const s = transform("v1.23.1", RELEASE_BODY, new Date("2026-08-01T00:00:00Z"));
  assert.match(s, /^## v1\.23\.1 \(2026-08-01\)/m);
  assert.match(s, /class="mb-12 pb-8 border-b/);
  assert.match(s, /text-lg font-semibold">Features<\/div>/);
  assert.match(s, /session-level trace grouping/);
  // Bug Fixes AND Performance Improvements merge into Bugs/Improvements
  assert.match(s, /text-lg font-semibold">Bugs\/Improvements<\/div>/);
  assert.match(s, /off-by-one in span pagination/);
  assert.match(s, /batch ClickHouse reads/);
  assert.match(s, /text-lg font-semibold">Breaking Changes<\/div>/);
  assert.match(s, /remove deprecated \/v1\/eval endpoint/);
  assert.doesNotMatch(s, /Chores/);
  assert.doesNotMatch(s, /bump deps/);
  assert.match(s, /<\/div>\s*$/);
});

test("transform omits empty subsections", () => {
  const s = transform("v1.23.2", "### Bug Fixes\n\n* **ui:** fix button\n", new Date("2026-08-02T00:00:00Z"));
  assert.doesNotMatch(s, />Features</);
  assert.doesNotMatch(s, />Breaking Changes</);
  assert.match(s, />Bugs\/Improvements</);
});

test("insert places section after marker, above existing weekly entries", () => {
  const page = `---\ntitle: "x"\n---\n\n{/* release-notes:insert-below — automation inserts new releases here; do not remove */}\n\n## Week of 2026-06-18\nold entry\n`;
  const out = insert(page, "## v1.23.1 (2026-08-01)\nnew\n</div>");
  const iMarker = out.indexOf("release-notes:insert-below");
  const iNew = out.indexOf("## v1.23.1");
  const iOld = out.indexOf("## Week of 2026-06-18");
  assert.ok(iMarker < iNew && iNew < iOld);
});

test("insert throws when marker missing", () => {
  assert.throws(() => insert("no marker here", "x"), /marker not found/);
});

test("MDX-significant characters in release bullets are escaped", () => {
  const body = "### Bug Fixes\n\n* **gateway:** handle <Tag> and {expr} in payloads\n";
  const s = transform("v1.23.3", body, new Date("2026-08-03T00:00:00Z"));
  assert.match(s, /&lt;Tag>/);
  assert.match(s, /&#123;expr&#125;/);
  assert.doesNotMatch(s, /<Tag>/);
  assert.doesNotMatch(s, /\{expr\}/);
  assert.equal(escapeMdx("<a>{b}"), "&lt;a>&#123;b&#125;");
});
