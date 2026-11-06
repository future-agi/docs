import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/coding-agents/hermes-agent.mdx', import.meta.url), 'utf8');

test('Hermes guide uses both released installation routes and scopes the setup to CLI', () => {
  const entry = integrations.find(item => item.id === 'hermes-agent');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/hermes-agent');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'traceAI plugin');
  assert.match(page, /Hermes CLI.*v2026\.9\.24.*0\.21\.5/);
  assert.match(page, /Python 3\.12/);
  assert.match(page, /CLI sessions, not Desktop or messaging-platform gateway sessions/);
  assert.match(page, /hermes plugins install future-agi\/traceAI\/python\/frameworks\/hermes-agent\/hermes-plugin\/futureagi/);
  assert.match(page, /\/path\/to\/hermes\/python -m pip install 'traceAI-hermes-agent==0\.1\.0'/);
  assert.match(page, /hermes plugins enable futureagi/);
  assert.match(page, /hermes chat -q "List the files in this folder and read README\.md"/);
  assert.doesNotMatch(page, /run_e2e\.sh|PLUGIN_SPEC|gateway\.multiplex_profiles|gateway sends|traced the same way|tested with|in our test|read 2026|verified live/i);
});

test('Hermes guide preserves authentication, metadata disclosure and content opt-in', () => {
  for (const name of ['FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME']) {
    assert.ok(page.includes(`export ${name}=`), name);
  }
  assert.match(page, /https:\/\/api\.futureagi\.com/);
  assert.match(page, /appends `\/tracer\/v1\/traces`/);
  assert.match(page, /Content capture is off by default/);
  assert.match(page, /hostname can be internal/);
  assert.match(page, /error text are excluded by default/);
  assert.match(page, /FI_HERMES_CAPTURE_CONTENT=true/);
  assert.match(page, /local paths, file contents and provider responses/);
  assert.match(page, /not a redaction mechanism/);
  assert.match(page, /tool still running at process exit has no span/);
  assert.match(page, /Each turn has its own trace, grouped by the shared `session\.id`/);
});
