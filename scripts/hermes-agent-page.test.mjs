import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/coding-agents/hermes-agent.mdx', import.meta.url), 'utf8');

test('Hermes guide has a three-step setup and retains a Python-only native route', () => {
  const entry = integrations.find(item => item.id === 'hermes-agent');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/hermes-agent');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'traceAI plugin');
  assert.match(page, /## 1\. Get your keys/);
  assert.match(page, /## 2\. Set up tracing/);
  assert.match(page, /## 3\. Run Hermes and inspect the trace/);
  assert.match(page, /npx @traceai\/agents setup hermes --project coding-agents/);
  assert.match(page, /hermes plugins install future-agi\/traceAI\/python\/frameworks\/hermes-agent\/hermes-plugin\/futureagi --enable/);
  assert.match(page, /hermes chat --oneshot -q/);
  assert.match(page, /Node is not needed while Hermes runs/);
  assert.match(page, /Desktop and messaging-platform gateway integrations are not yet available/);
  assert.match(entry.summary, /content capture on by default/);
  assert.doesNotMatch(entry.summary, /off by default/);
  assert.doesNotMatch(page, /run_e2e|git clone|\/path\/to\/hermes\/python|tested with|verified live/i);
});

test('Hermes guide discloses default capture, protected configuration and controls', () => {
  for (const value of ['FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'FI_OTLP_ENDPOINT', 'FI_AGENT_ENABLED=false', 'FI_AGENT_CAPTURE_CONTENT=false', 'FI_HIDE_ERROR_DETAILS']) {
    assert.ok(page.includes(value), value);
  }
  assert.match(page, /masked prompts/);
  assert.match(page, /\*\*Content capture is on\.\*\*/);
  assert.match(page, /--no-capture-content/);
  assert.match(page, /secrets the agent reads/);
  assert.match(page, /owner-only permissions/);
  assert.match(page, /complete pair/);
  assert.match(page, /cannot raise your saved privacy ceiling/);
  assert.match(page, /fences queued exports/);
  assert.match(page, /dependency consent/);
  assert.match(page, /not a general secret or PII scrubber/);
  assert.match(page, /no completion callback has no tool span/);
  assert.match(page, /Turn summaries do not duplicate model token usage/);
  assert.match(page, /earlier metadata-only default/);
});

test('Hermes guide documents scope, diagnostics and persistent gateway changes', () => {
  for (const command of ['status hermes --check', 'doctor hermes', 'disable hermes', 'enable hermes', 'uninstall hermes']) {
    assert.ok(page.includes(`npx @traceai/agents ${command}`), command);
  }
  assert.match(page, /setup hermes --project coding-agents --user-only/);
  assert.match(page, /--scope project --project-dir \/absolute\/project\/path/);
  assert.match(page, /does not permanently disable project discovery/);
  assert.match(page, /\.futureagi\/agents\.json/);
  assert.match(page, /futureagi\/agents\/credentials\.json/);
  assert.match(page, /`futureagi\.json` profile reference/);
  assert.match(page, /HERMES_HOME/);
  assert.match(page, /hermes gateway restart/);
  assert.match(page, /gateway launch environment/);
});

test('Hermes image and motion references resolve to real committed assets', () => {
  for (const [, url] of page.matchAll(/(?:\]\(|src=["'])(\/images\/[^)"']+)/g)) {
    assert.ok(fs.existsSync(new URL('../public' + url, import.meta.url)), url);
  }
});
