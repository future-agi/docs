import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const route = '/docs/integrations/frameworks/fastmcp';

test('Python FastMCP has its own discoverable native setup', () => {
  assert.ok(integrations.some(item => item.id === 'fastmcp-python' && item.href === route));
  const page = readFileSync(new URL(`../src/pages${route}.mdx`, import.meta.url), 'utf8');
  assert.match(page, /fastmcp>=4\.1\.0,<4\.2/);
  assert.match(page, /trace\.set_tracer_provider\(provider\)/);
  assert.match(page, /project_name/);
  assert.match(page, /project_type.*observe/);
  assert.match(page, /X-Api-Key/);
  assert.match(page, /X-Secret-Key/);
  assert.match(page, /provider\.shutdown\(\)/);
  assert.match(page, /mcp\.session\.id/);
  assert.match(page, /\*\*Unknown\*\*/);
  assert.match(page, /exception messages and stack traces/);
  assert.match(page, /FI_HIDE_INPUTS.*FI_HIDE_OUTPUTS.*FI_HIDE_ERROR_DETAILS/);
  assert.doesNotMatch(page, /MCPInstrumentor\(\)|class .*Exporter|class .*Processor/);
});
