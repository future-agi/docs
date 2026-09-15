import { test } from "node:test";
import assert from "node:assert/strict";
import { transform, insert, escapeMdx, stripInternalRefs, SECTION_MAP } from "./changelog-from-release.mjs";

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

test("insert is idempotent on redelivered/retried dispatch for same version", () => {
  const page = `{/* release-notes:insert-below — automation inserts new releases here; do not remove */}\n\n## v1.38.2 (2026-09-14)\nexisting\n`;
  const out = insert(page, "## v1.38.2 (2026-09-14)\nagain\n</div>", "v1.38.2");
  assert.equal(out, page);
  assert.equal((out.match(/## v1\.38\.2 \(/g) || []).length, 1);
});

test("stripInternalRefs removes Linear/JIRA ticket refs, parenthesised or bare", () => {
  assert.equal(stripInternalRefs("- **evals:** preserve binding (TH-7897)"), "- **evals:** preserve binding");
  assert.equal(stripInternalRefs("- fix thing TH-7938 now"), "- fix thing now");
  assert.equal(stripInternalRefs("- multi (TH-1, ABC-22)"), "- multi");
  // a version-like vX.Y.Z or an all-caps word is not a ticket ref
  assert.equal(stripInternalRefs("- ship API v2 support"), "- ship API v2 support");
});

test("transform collapses the same change repeated across commits", () => {
  // Real shape from bot PR #862: one dashboards change on three commits, two
  // carrying the internal ticket. After strip+dedup only one bullet survives.
  const body = [
    "### Bug Fixes",
    "",
    "* **dashboards:** apply Dataset and Eval Source filters to eval metric charts ([40d950d](https://github.com/future-agi/future-agi/commit/40d950d))",
    "* **dashboards:** apply Dataset and Eval Source filters to eval metric charts (TH-7938) ([37d07d7](https://github.com/future-agi/future-agi/commit/37d07d7))",
    "* **dashboards:** apply Dataset and Eval Source filters to eval metric charts (TH-7938) ([09046a8](https://github.com/future-agi/future-agi/commit/09046a8))",
    "* **evals:** preserve system eval binding config (TH-7897) ([2a7ced2](https://github.com/future-agi/future-agi/commit/2a7ced2))",
    "",
  ].join("\n");
  const s = transform("v1.38.2", body, new Date("2026-09-14T00:00:00Z"));
  assert.equal((s.match(/apply Dataset and Eval Source filters/g) || []).length, 1);
  assert.doesNotMatch(s, /TH-7938/);
  assert.doesNotMatch(s, /TH-7897/);
  assert.match(s, /preserve system eval binding config/);
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

// Drift guard. release-please emits a bucket heading per VISIBLE changelog
// section in future-agi/future-agi's release-please-config.json. A visible
// section absent from SECTION_MAP (and not "Breaking Changes", handled inline)
// is silently dropped from the public page. This fixture mirrors that config's
// visible sections; if the source config gains a visible section, update both.
// Kept as a fixture rather than a live fetch so the suite stays offline and
// deterministic.
test("every visible release-please section maps to a page subsection", () => {
  const VISIBLE_SOURCE_SECTIONS = ["Features", "Bug Fixes", "Performance Improvements", "Reverts"];
  const VALID_TARGETS = new Set(["Features", "Bugs/Improvements", "Breaking Changes"]);
  for (const section of VISIBLE_SOURCE_SECTIONS) {
    assert.ok(SECTION_MAP.has(section), `visible section "${section}" is not mapped — it would be dropped from the page`);
    assert.ok(VALID_TARGETS.has(SECTION_MAP.get(section)), `"${section}" maps to an unknown subsection`);
  }
  for (const target of SECTION_MAP.values()) {
    assert.ok(VALID_TARGETS.has(target), `SECTION_MAP target "${target}" is not a rendered subsection`);
  }
});
