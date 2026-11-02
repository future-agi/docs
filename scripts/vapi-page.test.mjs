import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations, integrationNavigation } from '../src/lib/integrations.mjs';

const read = file => fs.readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const route = '/docs/integrations/voice/vapi';

test('Vapi discovery leads directly to its managed-ingestion setup', () => {
  const entry = integrations.find(item => item.id === 'vapi');
  assert.equal(entry.href, route);
  assert.equal(entry.method, 'Managed ingestion');
  const flatten = items => items.flatMap(item => [item.href, ...flatten(item.items ?? [])]);
  assert.ok(flatten(integrationNavigation).includes(route));
});

test('Vapi setup uses provider credentials and no tracing adapter', () => {
  const page = read('src/pages/docs/integrations/voice/vapi.mdx');
  for (const text of ['private API key', 'Assistant ID', 'Provider API Key', 'Enable observability', 'Observe', 'completed call', 'conversation span']) {
    assert.ok(page.includes(text), text);
  }
  assert.match(page, /not.*public key/i);
  assert.match(page, /not.*FI_API_KEY/);
  assert.match(page, /recording.*enabled/i);
  assert.match(page, /No SDK installation/);
  assert.doesNotMatch(page, /pip install|npm install|```(?:python|javascript)|tracer\/v1\/traces|verified live|PASS\/FAIL/i);
  for (const [, link] of page.matchAll(/\]\((\/docs\/[^)#]+)(?:#[^)]*)?\)/g)) {
    assert.ok(fs.existsSync(new URL(`../src/pages${link}.mdx`, import.meta.url)), link);
  }
});

test('Voice concepts distinguish managed conversation messages from instrumented turn spans', () => {
  const page = read('src/pages/docs/observe/concepts/voice-observability.mdx');
  assert.match(page, /managed.*conversation span/i);
  assert.match(page, /transcript messages.*not.*child spans/i);
  assert.doesNotMatch(page, /each back-and-forth turn is a span|Managed calls arrive at the turn level/);
  assert.ok(page.includes(route));
});
