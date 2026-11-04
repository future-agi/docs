import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Documentation contract, not a backend import test. Langfuse's public API
// returns the project associated with the key; organization keys administer
// projects, users and project keys. Sources pinned for this regression:
// https://github.com/langfuse/langfuse-docs/blob/c28ba8e509d332357e3ca2c89833ce9e2c299933/content/docs/api-and-data-platform/features/public-api.mdx#L17-L109
// https://github.com/langfuse/langfuse-docs/blob/c28ba8e509d332357e3ca2c89833ce9e2c299933/content/docs/administration/rbac.mdx#L363-L394
// https://github.com/langfuse/langfuse-docs/blob/c28ba8e509d332357e3ca2c89833ce9e2c299933/content/docs/administration/scim-and-org-api.mdx#L9-L57
const source = readFileSync(
  new URL("../src/pages/docs/integrations/import/langfuse.mdx", import.meta.url),
  "utf8",
);

const section = (start, end) => source.split(start)[1]?.split(end)[0] ?? "";

test("prerequisites use project keys with read access, not ingestion-only keys", () => {
  const prerequisites = section("## Before you start", "## Connect Langfuse");
  assert.match(prerequisites, /Project Settings > API Keys/);
  assert.match(prerequisites, /read access/i);
  assert.match(prerequisites, /Viewer/);
  assert.match(prerequisites, /Ingestion[^\n]*cannot read/i);
});

test("setup distinguishes organization administration from project data access", () => {
  const setup = section('title="Enter your API credentials"', 'title="Configure sync settings"');
  assert.match(setup, /Do not (?:use|substitute)[^\n]*organization/i);
  assert.match(setup, /organization[^\n]*administration/i);
  assert.doesNotMatch(source, /(?:Use|Switch to)\s+(?:\*\*)?(?:an?\s+)?organization-level API keys?[^\n]*all projects/i);
  assert.ok(source.includes("https://langfuse.com/docs/administration/scim-and-org-api"));
});

test("each source project uses its own connection and project key pair", () => {
  const setup = section('title="Map projects"', 'title="Configure sync settings"');
  const troubleshooting = section('<Accordion title="Only one project shows in the dropdown">', "</Accordion>");
  for (const text of [setup, troubleshooting]) {
    assert.match(text, /separate connection/i);
    assert.match(text, /(?:project's|project’s|project) (?:own )?(?:API )?key/i);
  }
});

test("host guidance uses the project's region instead of treating EU as all Cloud", () => {
  const credentials = section('title="Enter your API credentials"', 'title="Map projects"');
  assert.match(credentials, /https:\/\/cloud\.langfuse\.com[^\n]*EU/);
  assert.match(credentials, /https:\/\/us\.cloud\.langfuse\.com[^\n]*US/);
  assert.ok(credentials.includes("https://langfuse.com/docs/api-and-data-platform/features/public-api#base-urls"));
});

test("historical import remains available without unverified replay guarantees", () => {
  assert.match(source, /No re-instrumentation required/);
  assert.match(source, /Import all traces/);
  assert.match(source, /Import from a specific date/);
  assert.doesNotMatch(source, /The sync is idempotent|won't create duplicate traces|picked up on the next cycle|metadata edits[^\n]*re-synced|pick up any that were skipped/i);
});

// These tests prevent unsupported customer promises, not importer defects.
// Source API boundary and future Cloud cutoff:
// https://github.com/langfuse/langfuse-docs/blob/3c188485144598c3c818261362dc269d3f55e4ed/content/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4.mdx#L93-L129
// https://github.com/langfuse/langfuse-docs/blob/3c188485144598c3c818261362dc269d3f55e4ed/lib/v4-migration-dates.ts
// Do not remove the date warnings until product behavioral regressions prove
// pre-connection traces and traces after the requested end are excluded.
test("setup requires legacy trace APIs and excludes v4 events-only deployments", () => {
  const prerequisites = section("## Before you start", "## Connect Langfuse");
  for (const endpoint of ["GET /api/public/traces`", "GET /api/public/traces/{id}"]) {
    assert.ok(prerequisites.includes(endpoint));
  }
  assert.match(prerequisites, /v3[\s\S]*v4[\s\S]*`legacy`[\s\S]*`dual`/);
  assert.match(prerequisites, /LANGFUSE_MIGRATION_V4_WRITE_MODE/);
  assert.match(prerequisites, /`events_only`[^\n]*not supported[^\n]*404/);
  assert.match(prerequisites, /do not create this connection/i);
  assert.match(prerequisites, /live OpenTelemetry[^\n]*does not transfer existing traces/);
  const troubleshooting = section('<Accordion title="Credentials validate, but imports fail with HTTP 404">', "</Accordion>");
  assert.match(troubleshooting, /project API[^\n]*succeed/);
  assert.match(troubleshooting, /zero trace estimate does not prove/i);
  assert.match(troubleshooting, /Rotating valid project keys will not restore/);
});

test("Cloud guidance describes the scheduled cutoff rather than claiming it already occurred", () => {
  const prerequisites = section("## Before you start", "## Connect Langfuse");
  assert.match(prerequisites, /removal is scheduled for[^\n]*November 16, 2026 \(2026-11-16\)/);
  assert.match(prerequisites, /complete historical imports before that date/);
  assert.match(prerequisites, /do not rely on ongoing sync after the cutoff/);
  assert.ok(prerequisites.includes("https://langfuse.com/faq/all/deprecated-api-migration#traces"));
});

test("new-only selection warns about older traces instead of promising a creation-time bound", () => {
  const sync = section('title="Configure sync settings"', 'title="Done"');
  const option = sync.split("| **Only import new traces going forward** |")[1]?.split("\n")[0] ?? "";
  assert.match(option, /Can import traces from before the connection was created/);
  assert.match(option, /Do not use this option to exclude history/);
  assert.match(sync, /strict connection-time cutoff[^\n]*do not connect this importer/);
  assert.doesNotMatch(source, /sync only new traces|Skips history|starts syncing from now/i);
});

test("date selection documents only the enforced start and warns that the end is not enforced", () => {
  const sync = section('title="Configure sync settings"', 'title="Done"');
  const option = sync.split("| **Import from a specific date** |")[1]?.split("\n")[0] ?? "";
  assert.match(option, /chosen start date[^\n]*initial import[^\n]*current sync time/);
  assert.match(option, /end date is not enforced/);
  assert.match(sync, /upper-bound cutoff[^\n]*do not connect this importer/);
  const troubleshooting = section('<Accordion title="Traces are missing after backfill">', "</Accordion>");
  assert.match(troubleshooting, /on or after your selected start date/);
  assert.match(troubleshooting, /end-date field does not limit the import/);
  assert.doesNotMatch(source, /Pick a start and end date|within your selected historical date range/i);
});
