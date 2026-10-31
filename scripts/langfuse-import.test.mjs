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
  assert.match(source, /Only import new traces going forward/);
  assert.doesNotMatch(source, /The sync is idempotent|won't create duplicate traces|picked up on the next cycle|metadata edits[^\n]*re-synced|pick up any that were skipped/i);
});
