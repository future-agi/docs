import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations, integrationAids, integrationNavigation, integrationDirectoryMarkdown } from '../src/lib/integrations.mjs';

const href = '/docs/integrations/no-code/flowise';
const page = readFileSync(new URL('../src/pages/docs/integrations/no-code/flowise.mdx', import.meta.url), 'utf8');

test('Flowise retirement remains discoverable as a support aid, not an integration card', () => {
  const aid = { name: 'Flowise support status', href, category: 'apps' };
  assert.deepEqual(integrationAids.filter(item => item.href === href), [aid]);
  assert.ok(!integrations.some(item => item.id === 'flowise' || item.href === href));
  const apps = integrationNavigation.find(group => group.title === 'Apps & workflows');
  assert.ok(apps?.items.some(item => item.href === href && item.title === aid.name));
  assert.ok(integrationDirectoryMarkdown().includes(`[${aid.name}](${href})`));
});

test('Flowise support page explains retirement without offering a fork setup', () => {
  assert.match(page, /Future AGI has retired its Flowise integration/);
  assert.match(page, /\[FlowiseAI\/Flowise repository\]\(https:\/\/github\.com\/FlowiseAI\/Flowise\) is archived/);
  assert.match(page, /no supported Flowise-to-Future AGI tracing setup, including fork-based installations/);
  assert.match(page, /Installing a traceAI package in Flowise does not add a supported tracing provider/);
  assert.match(page, /For applications whose model-calling code you control/);
  assert.match(page, /\[traceAI integrations\]\(\/docs\/integrations\/traceai\)/);
  assert.doesNotMatch(page, /```|git clone|git checkout|pnpm|future-agi\/Flowise|FI_HIDE_|overrideConfig|verified live|tested with|41 spans/i);
});
