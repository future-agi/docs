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
  for (const text of ['private API key', 'Assistant ID', 'Vapi API key', 'Observability', 'Observe', 'completed call', 'conversation span']) {
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

test('Vapi setup follows the connected-agent hosted-platform flow', () => {
  const page = read('src/pages/docs/integrations/voice/vapi.mdx');
  for (const label of ['Agents', 'Create Agents', 'Connect agents', 'Hosted platform', 'Voice', 'Vapi', 'Run preflight', 'Build environment', 'Connected agents']) {
    assert.ok(page.includes(`**${label}**`), `Missing current setup control: ${label}`);
  }
  assert.doesNotMatch(page, /\*\*Agent Definition\*\*|Provider API Key|Enable observability|create a voice agent definition|edit the agent definition/i);
});

test('Vapi observability is changed on the connected agent Definition tab', () => {
  const page = read('src/pages/docs/integrations/voice/vapi.mdx');
  assert.match(page, /\*\*Definition\*\*.*turn on \*\*Observability\*\*/);
  assert.match(page, /saved automatically/);
  assert.match(page, /stop fetching new calls.*\*\*Definition\*\*.*turn off \*\*Observability\*\*/);
  assert.match(page, /switch is disabled.*permission/i);
});

test('Vapi key rotation uses the environment version credentials drawer', () => {
  const page = read('src/pages/docs/integrations/voice/vapi.mdx');
  const rotation = page.split('## Rotate your Vapi key')[1]?.split('\n## ')[0];
  assert.ok(rotation, 'Missing credential-update instructions');
  for (const label of ['Environments', 'Overview', 'Manage versions', 'Credentials', 'Change values', 'Save values']) {
    assert.ok(rotation.includes(`**${label}**`), `Missing rotation control: ${label}`);
  }
  assert.ok(rotation.includes('`VAPI_API_KEY`'));
  assert.match(rotation, /check.*pass.*default/i);
  assert.match(rotation, /does not have.*credential editor/);
});

test('Voice concepts distinguish managed conversation messages from instrumented turn spans', () => {
  const page = read('src/pages/docs/observe/concepts/voice-observability.mdx');
  assert.match(page, /managed.*conversation span/i);
  assert.match(page, /transcript messages.*not.*child spans/i);
  assert.doesNotMatch(page, /each back-and-forth turn is a span|Managed calls arrive at the turn level/);
  assert.ok(page.includes(route));
});
