import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/opencode.mdx', import.meta.url), 'utf8');

test('OpenCode has one discoverable V1 and V2 page with three-step maintained-package setup', () => {
  const entry = integrations.find(({ id }) => id === 'opencode');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/opencode');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'OpenCode plugin');
  assert.match(page, /https:\/\/app\.futureagi\.com\/dashboard\/keys/);
  assert.equal((page.match(/<Step title=/g) ?? []).length, 3);
  for (const agent of ['opencode', 'opencode-v1']) {
    assert.ok(page.includes(`npx @traceai/agents setup ${agent} --project coding-agents`));
  }
  for (const pkg of ['@traceai/opencode-plugin', '@traceai/opencode-v1-plugin']) {
    assert.ok(page.includes(pkg));
  }
  assert.match(page, /2\.2\.5/);
  assert.match(page, /1\.19\.0 or newer below 2\.0\.0, on Linux/);
  assert.match(page, /22\.16/);
  assert.match(page, /opencode run "Read README\.md/);
  assert.match(page, /open \*\*Observe\*\*/);
  assert.doesNotMatch(page, /curl -|git clone|mkdir -p .*plugins|```(?:typescript|python)|FI_CAPTURE_CONTENT|fi-docs\/examples/);
});

test('OpenCode documents prompt roots, model usage, subagents and session grouping without old mutable roots', () => {
  for (const text of ['One trace per prompt', 'Model calls', 'token counts', 'Subagents', 'Sessions', 'resumed conversations']) {
    assert.ok(page.includes(text), text);
  }
  assert.match(page, /Usage belongs to model steps, not both the steps and the turn root/);
  assert.match(page, /explicit spawning-tool session ID/);
  assert.match(page, /background children and their continuations stay with the original prompt/);
  assert.match(page, /costs are estimates, not provider billing/);
  assert.match(page, /not a byte-for-byte provider request/);
  assert.doesNotMatch(page, /opencode\.session.*AGENT|updated end time|keeps the latest copy|every OpenCode session becomes one/);
});

test('OpenCode preserves privacy, credential storage and version-specific scope safeguards', () => {
  assert.match(page, /Content capture is \*\*on by default\*\*/);
  for (const text of ['--no-capture-content', 'FI_AGENT_CAPTURE_CONTENT=false', 'FI_AGENT_ENABLED', 'FI_API_KEY', 'FI_SECRET_KEY', 'FI_OTLP_ENDPOINT', 'FI_BASE_URL', 'FI_USER_ID', 'FI_AGENT_CONFIG_DIR', 'credentials.json', '.opencode/futureagi.json', '0600']) {
    assert.ok(page.includes(text), text);
  }
  assert.match(page, /--scope project --project-dir \.[\s\S]*?--project my-project --configure-only/);
  assert.match(page, /--user-only/);
  assert.match(page, /does not disable project settings when OpenCode later runs/);
  assert.match(page, /cannot raise your user-approved privacy ceiling/);
  assert.match(page, /DESTINATION_NOT_APPROVED/);
  assert.match(page, /not a data-loss-prevention guarantee/);
  assert.match(page, /FI_HIDE_\*/);
  assert.match(page, /20,000 characters/);
});

test('OpenCode provides diagnostics and owned lifecycle commands without QA diaries or fabricated media', () => {
  for (const command of ['status opencode --check', 'doctor opencode', 'disable opencode', 'enable opencode', 'update opencode', 'uninstall opencode']) {
    assert.ok(page.includes(`npx @traceai/agents ${command}`), command);
  }
  assert.match(page, /Replace `opencode` with `opencode-v1`/);
  assert.match(page, /opencode service restart/);
  assert.match(page, /historical sessions are not imported/);
  assert.match(page, /PROJECT_CONFIG_IGNORED_UNSAFE/);
  assert.match(page, /OPENCODE_CONFIG_CONTENT/);
  assert.match(page, /forced process kill can lose/);
  assert.doesNotMatch(page, /verified live|E2B|run[_ -]?ids?|release hold|qualification|QA harness|placeholder.*image/i);
  // The only media is the real OpenCode trace capture.
  assert.deepEqual([...page.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)].map(m => m[1]), ['/images/docs/integrations/coding-agents/opencode-trace.png']);
});
