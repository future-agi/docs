import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const read = file => fs.readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/coding-agents/augment-code.mdx');
const template = JSON.parse(read('examples/coding-agents/augment-code/settings.json'));

test('Auggie guide and shipped hooks agree on the session-only macOS scope', () => {
  const sample = page.match(/```json\n([\s\S]*?)\n```/)?.[1];
  assert.ok(sample, 'Show the generated session hook configuration');
  assert.deepEqual(JSON.parse(sample), template);
  assert.deepEqual(Object.keys(template.hooks), ['SessionStart', 'Stop', 'SessionEnd']);
  for (const groups of Object.values(template.hooks)) {
    for (const group of groups) {
      assert.equal(group.metadata, undefined);
      for (const hook of group.hooks) {
        assert.equal(hook.type, 'command');
        assert.equal(hook.timeout, 5000);
        assert.equal(hook.command, '/Users/you/.augment/fi-hook-to-otlp/futureagi-hook.sh');
      }
    }
  }
  assert.match(page, /Auggie CLI 0\.36\.0 on macOS/);
  assert.match(page, /npm install --global @augmentcode\/auggie@0\.36\.0/);
  assert.match(page, /Node\.js 20 or later/);
  assert.match(page, /new CLI sessions only/);
  assert.match(page, /Tool tracing, resumed conversations[^\n]+outside its scope/);
  assert.match(page, /remove its Future AGI `PostToolUse` entry; retain unrelated hooks/);
  assert.match(page, /There are no turn spans or tool spans in this configuration/);
  assert.match(page, /session with no stop event exports nothing/);
});

test('Auggie guide preserves the installer, credential, privacy and removal contract', () => {
  for (const term of [
    'install.sh --project /path/to/your/repo',
    'FI_API_KEY=', 'FI_SECRET_KEY=', 'FI_PROJECT_NAME=auggie-sessions',
    'umask 077', 'chmod 600', 'FI_HOOK_CAPTURE_CONTENT=0',
    '$FI_BASE_URL/tracer/v1/traces', 'FI_HOOK_DISABLED=1',
    '`context`', '`conversation`', '`user_prompt`', '`_exchange`', '`workspace_roots`',
    'includeUserContext', 'includeConversationData',
    'before deleting', 'single quote', 'remove it from tracking',
  ]) assert.ok(page.includes(term), term);
  assert.doesNotMatch(page, /verification status|verified live|documented.shape only|no usage left|read 2026-|fi_verify|run_e2e\.sh/i);
  assert.doesNotMatch(page, /well under a second|more tool spans|with tool calls/);
});

test('Auggie is discoverable as a CLI lifecycle integration, not tool tracing', () => {
  const entry = integrations.find(item => item.id === 'augment-code');
  assert.ok(entry);
  assert.equal(entry.href, '/docs/integrations/coding-agents/augment-code');
  assert.equal(entry.category, 'coding');
  assert.equal(entry.method, 'Hook-to-OTLP');
  assert.match(entry.summary, /new macOS CLI sessions/);
  assert.doesNotMatch(entry.summary, /tool calls|tool spans/);
});
