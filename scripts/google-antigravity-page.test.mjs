import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/google-antigravity.mdx', import.meta.url), 'utf8');

test('Antigravity remains discoverable through the maintained CLI plugin', () => {
  const entry = integrations.find(item => item.id === 'google-antigravity');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/google-antigravity');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'traceAI plugin');
  assert.match(entry.summary, /Linux CLI/);
  assert.match(entry.summary, /macOS desktop-app/);
  assert.match(page, /Antigravity CLI 1\.x on Linux/);
  assert.match(page, /Node\.js 22\.16\+ within 22\.x, or 24\.x/);
  assert.match(page, /Antigravity desktop app on macOS/);
  assert.match(page, /## Desktop app[\s\S]*only a turn's final model response includes response text/);
  assert.match(page, /The desktop app on Windows and Linux is \*\*not yet available\*\*/);
  assert.doesNotMatch(page, /setup antigravity-ide|CLI 1\.4\.2 on macOS/);
});

test('Antigravity quick start requires keys, one setup command and an ordinary agent run', () => {
  const start = page.split('## Quick start')[1]?.split('## Configuration')[0];
  assert.ok(start);
  // Three-step layout is enforced by coding-agents-contract.test.mjs.
  for (const text of [
    'https://app.futureagi.com/dashboard/keys',
    'npx @traceai/agents setup antigravity --project coding-agents',
    'hidden terminal prompts', 'agy plugin install',
    'agy -p "Read README.md and summarize the project"',
    '**Observe**', '**Sessions**', '--conversation <conversation-id>',
  ]) assert.ok(start.includes(text), text);
  assert.doesNotMatch(page, /git clone|emit\.py|install\.sh|FI_HOOK_CAPTURE_CONTENT|verified live|qualification|run ids|E2B|QA harness/i);
});

test('Antigravity describes prompt traces, transcript generations and nested subagents honestly', () => {
  for (const text of [
    'one trace per prompt', 'same conversation share a session',
    'Generations reconstructed from the CLI transcript',
    'Child work nested under the invoking tool',
    'Tokens are counted once', 'not a complete provider request',
    'Unavailable costs and token breakdowns are left absent',
    'completion-only tool hook does not establish tool execution duration',
    '**incomplete**, not successful',
  ]) assert.ok(page.includes(text), text);
  assert.doesNotMatch(page, /one trace per conversation|Token counts and cost\.\*\* Hook payloads do not include them/);
});

test('Antigravity keeps content on by default and gives privacy, scope and lifecycle controls', () => {
  for (const text of [
    'Content capture is on by default', '--no-capture-content',
    'FI_AGENT_CAPTURE_CONTENT=false', 'FI_AGENT_ENABLED=false',
    'FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'FI_USER_ID',
    'FI_BASE_URL', 'FI_OTLP_ENDPOINT', 'FI_AGENT_CONFIG_DIR',
    'futureagi/agents/credentials.json', '0600', '~/.gemini/config/futureagi.json',
    '.futureagi/agents.json', '--scope project', '--project-dir <path>', '--user-only',
    'registration remains user-global', 'multi-root sessions use user settings',
    'redaction is best effort', 'expires after 24 hours',
    'PROJECT_CONFIG_IGNORED', 'PINNED_NODE_MISSING', 'PENDING_TURNS', '--replace-credentials',
  ]) assert.ok(page.includes(text), text);
  for (const command of ['status', 'doctor', 'disable', 'enable', 'update', 'uninstall']) {
    assert.ok(page.includes(`npx @traceai/agents ${command} antigravity`), command);
  }
  assert.match(page, /status antigravity --check/);
  assert.match(page, /Saved credentials still require destination approval/);
  assert.match(page, /A repository cannot turn content capture back on/);
  assert.match(page, /native installer does not support `--scope project`/);
  const projectSettings = JSON.parse(page.match(/```json\n([\s\S]*?)\n```/)?.[1]);
  assert.deepEqual(projectSettings, { antigravity: { schemaVersion: 1, captureContent: false } });
  assert.doesNotMatch(page, /off by default|never exported.*secret/i);
});
