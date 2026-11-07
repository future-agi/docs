import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations, integrationSearchText } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/cursor.mdx', import.meta.url), 'utf8');

test('Cursor IDE and CLI retain a discoverable shared route distinct from the SDK', () => {
  const entry = integrations.find(({ id }) => id === 'cursor');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/cursor');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'Cursor plugin');
  assert.match(integrationSearchText(entry), /cursor-agent/i);
  assert.notEqual(entry.href, integrations.find(({ id }) => id === 'cursor-sdk')?.href);
});

test('Cursor quick start uses one maintained setup for IDE and interactive CLI', () => {
  assert.equal((page.match(/^### [123]\. /gm) ?? []).length, 3);
  assert.match(page, /https:\/\/app\.futureagi\.com\/dashboard\/keys/);
  assert.match(page, /npx @traceai\/agents setup cursor --project cursor-sessions/);
  assert.match(page, /Node\.js 22\.16\+/);
  assert.match(page, /```bash\ncursor-agent\n```/);
  assert.match(page, /keep the IDE installed/);
  assert.doesNotMatch(page, /npx @traceai\/agents setup cursor-cli/);
  assert.doesNotMatch(page, /git clone|emit\.py|fi-docs\/examples|FI_HOOK_CAPTURE_CONTENT|FI_HOOK_LOG_FILE/);
});

test('Cursor documents prompt-level traces and honest source-limited usage', () => {
  assert.match(page, /One trace per prompt/);
  assert.match(page, /session\.id/);
  assert.match(page, /LLM spans reconstructed from Cursor's transcript/);
  assert.match(page, /Turn totals are counted once on the final generation/);
  assert.match(page, /not individual model-call token counts/);
  assert.match(page, /both the subagent ID and its parent Task call ID/);
  assert.match(page, /Auto mode reports the model as `default`/);
  assert.match(page, /print mode[\s\S]*partial trace/);
  assert.match(page, /Cursor Cloud tracing is \*\*not yet available\*\*/);
});

test('Cursor provides privacy controls, scope and complete lifecycle commands', () => {
  assert.match(page, /on by default/);
  assert.match(page, /--no-capture-content/);
  assert.match(page, /FI_AGENT_CAPTURE_CONTENT=false/);
  assert.match(page, /redaction cannot guarantee/);
  assert.match(page, /~\/\.cursor\/futureagi\.json/);
  assert.match(page, /~\/\.config\/futureagi\/agents\/credentials\.json/);
  assert.match(page, /0600/);
  assert.match(page, /--scope project/);
  assert.match(page, /changing the user default does not override an existing project setting/);
  assert.match(page, /--user-only/);
  assert.match(page, /Project scope does not install a second set of project hooks/);
  for (const command of ['status', 'doctor', 'disable', 'enable', 'update', 'uninstall']) {
    assert.ok(page.includes(`npx @traceai/agents ${command} cursor`), command);
  }
  assert.doesNotMatch(page, /verified live|QA harness|run ids|NPM_AVAILABILITY_REQUIRED|AUTHORIZED_CLOUD_RUN_REQUIRED/i);
});
