import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const source = readFileSync(
  new URL('../src/pages/docs/integrations/traceai/autogen.mdx', import.meta.url),
  'utf8',
);
const warning = source.match(/<Warning>([\s\S]*?)<\/Warning>/)?.[1] ?? '';

test('AutoGen retirement and security warning appears before installation', () => {
  assert.ok(source.indexOf('<Warning>') < source.indexOf('## 1. Install'));
  assert.match(warning, /no longer maintains AutoGen/);
  assert.match(warning, /bug fixes, security fixes, or support/);
  assert.match(warning, /New projects should use/);
  assert.match(warning, /https:\/\/github\.com\/microsoft\/autogen#readme/);
  assert.match(warning, /https:\/\/github\.com\/microsoft\/agent-framework/);
});

test('migration guidance links upstream and does not promise drop-in telemetry parity', () => {
  assert.match(source, /https:\/\/learn\.microsoft\.com\/en-us\/agent-framework\/migration-guide\/from-autogen\//);
  assert.match(source, /not a drop-in replacement/);
  assert.match(source, /multi-agent/);
  for (const concern of ['tool', 'error', 'privacy']) assert.ok(source.includes(concern));
});

test('existing users retain a pinned published AgentChat setup', () => {
  assert.match(source, /traceAI-autogen==0\.2\.1/);
  assert.match(source, /autogen-agentchat==0\.7\.5/);
  assert.match(source, /autogen-ext\[openai\]==0\.7\.5/);
  assert.match(source, /https:\/\/pypi\.org\/project\/traceAI-autogen\/0\.2\.1\//);
  assert.doesNotMatch(source, /autogen-(?:agentchat|ext[^"\s]*)>=/);
  assert.match(source, /from traceai_autogen import AutogenInstrumentor/);
  assert.match(source, /await team\.run\(/);
  assert.match(source, /trace_provider\.force_flush\(\)/);
  assert.match(source, /trace_provider\.shutdown\(\)/);
});

test('legacy setup retains privacy guidance and avoids overlapping native tracing', () => {
  assert.match(source, /FI_HIDE_INPUTS/);
  assert.match(source, /FI_HIDE_OUTPUTS/);
  assert.match(source, /leave `AutogenInstrumentor` disabled/);
  assert.match(source, /set_global_tracer_provider=False/);
  assert.match(source, /Do not combine this setup with AutoGen native tracing/);
});

test('AutoGen catalog points existing users to migration instead of new onboarding', () => {
  const entry = integrations.find(item => item.id === 'autogen');
  assert.equal(entry.href, '/docs/integrations/traceai/autogen');
  assert.match(entry.summary, /existing AutoGen/);
  assert.match(entry.summary, /migration/);
});
