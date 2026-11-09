import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/openclaw.mdx', import.meta.url), 'utf8');

test('OpenClaw has a three-step maintained-package quick start', () => {
  assert.match(page, /https:\/\/app\.futureagi\.com\/dashboard\/keys/);
  assert.match(page, /npx @traceai\/agents setup openclaw --project coding-agents/);
  assert.match(page, /npx @traceai\/agents run openclaw -- agent --local/);
  assert.match(page, /--session-id readme-review/);
  assert.doesNotMatch(page, /curl -fsSLO|git clone|hook-to-otlp|run_e2e\.sh/);
});

test('OpenClaw documents prompt roots, native usage and limited surfaces', () => {
  for (const text of [
    'One `openclaw.prompt` trace per launcher invocation',
    'retries beneath the same root',
    'each prompt remains a separate trace',
    'rollup is removed',
    'prompt root owns that usage once',
    'cost estimates as metrics',
    'Subagent and compaction visibility is limited',
    '**not yet available**',
    'ordinary `openclaw` launch is not redirected',
    'OpenClaw 2026.10.5 or later in the 2026.x line',
    'Node 24.16 or newer in the 24.x line',
  ]) assert.ok(page.includes(text), text);
  assert.doesNotMatch(page, /several native run traces|keeps those roots separate|Only model-request spans contribute/);
});

test('OpenClaw preserves consent, privacy and configuration controls', () => {
  for (const text of [
    'Content capture is on by default', '--no-capture-content',
    'FI_AGENT_CAPTURE_CONTENT=false', 'FI_AGENT_ENABLED=false',
    'FI_API_KEY', 'FI_SECRET_KEY', 'TRUST_REQUIRED',
    '0600', 'X-Project-Name', 'project_type=observe',
    '~/.config/futureagi/agents/credentials.json',
    '~/.openclaw/futureagi.json', '.futureagi/agents.json',
    'OPENCLAW_CONFIG_PATH', 'OPENCLAW_STATE_DIR', 'OPENCLAW_HOME',
    '--scope project', '--project-dir /path/to/repo', '--user-only',
    'PROJECT_CONFIG_IGNORED', 'per-run, memory-only key',
    'cannot reliably detect every application secret',
  ]) assert.ok(page.includes(text), text);
  for (const command of ['status', 'doctor', 'disable', 'enable', 'update', 'uninstall']) {
    assert.ok(page.includes(`npx @traceai/agents ${command} openclaw`), command);
  }
  assert.doesNotMatch(page, /capture.*off by default|verified live|PASS\/FAIL|qualification|release hold|run[_-]id/i);
});

test('OpenClaw remains discoverable without advertising Gateway tracing', () => {
  const entry = integrations.find(({ id }) => id === 'openclaw');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/openclaw');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'traceAI plugin');
  assert.doesNotMatch(entry?.summary ?? '', /Gateway/i);
});
