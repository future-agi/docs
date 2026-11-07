import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const read = file => fs.readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/coding-agents/grok-build.mdx');

test('Grok Build has a discoverable native-plugin three-step quick start', () => {
  const entry = integrations.find(item => item.id === 'grok-build');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/grok-build');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'Native plugin');
  assert.match(page, /@traceai\/grok-plugin/);
  assert.match(page, /1\.0\.77 or later in the 1\.x series/);
  assert.match(page, /Node\.js 22\.16 or later/);
  const quickStart = page.split('## Quick start\n')[1].split('\n## What you see')[0];
  assert.equal((quickStart.match(/^### [123]\. /gm) ?? []).length, 3);
  assert.match(quickStart, /https:\/\/app\.futureagi\.com\/dashboard\/keys/);
  assert.match(quickStart, /npx @traceai\/agents setup grok --project grok-build/);
  assert.match(quickStart, /grok -p "List the files in this folder and read README\.md"/);
  assert.match(quickStart, /\*\*Observe\*\*/);
  assert.doesNotMatch(page, /git clone|install\.sh|emit\.py|FI_HOOK_CAPTURE_CONTENT|```json/);
  assert.doesNotMatch(page, /verified live|run_e2e|test sessions|REGISTRY_PUBLICATION_REQUIRED|\bHOLD\b|placeholder image/i);
});

test('Grok Build describes prompt traces without inventing provider request fidelity', () => {
  assert.match(page, /Each prompt becomes one trace/);
  assert.match(page, /shared session ID/);
  assert.match(page, /Generations reconstructed from Grok's transcript/);
  assert.match(page, /not exact provider request boundaries/);
  assert.match(page, /turn-level usage, recorded once on the root/);
  assert.match(page, /Nested agent spans/);
  assert.match(page, /does not estimate model cost/);
  assert.match(page, /Interactive TUI tracing is not yet available/);
  assert.match(page, /trace may be incomplete or absent/);
  assert.doesNotMatch(page, /one trace per session|each subagent is its own trace|emitter never opens the transcript/);
});

test('Grok Build exposes content defaults, private credentials, and scope boundaries', () => {
  for (const term of ['FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'FI_BASE_URL',
    'FI_OTLP_ENDPOINT', 'FI_AGENT_CAPTURE_CONTENT=false', 'FI_AGENT_ENABLED=false',
    '~/.grok/futureagi.json', '~/.config/futureagi/agents/credentials.json',
    '<repository>/.grok/futureagi.json', '0600', '--user-only', '--project-dir']) {
    assert.ok(page.includes(term), term);
  }
  assert.match(page, /Content capture is \*\*on by default\*\*/);
  assert.match(page, /--no-capture-content/);
  assert.match(page, /hidden input/);
  assert.match(page, /Project-scoped plugin installation with `--scope project` is not yet available/);
  assert.match(page, /`--user-only` applies to that CLI command/);
  assert.match(page, /cannot silently redirect saved credentials/);
  assert.match(page, /cannot re-enable content capture/);
  assert.match(page, /redaction is not a guarantee/);
  assert.match(page, /does not delete earlier exports or Grok's own local transcripts/);
});

test('Grok Build documents lifecycle, explicit trust, and migration without disabling other hooks', () => {
  for (const command of ['status', 'doctor', 'disable', 'enable', 'update', 'uninstall']) {
    assert.ok(page.includes(`npx @traceai/agents ${command} grok`), command);
  }
  assert.match(page, /TRUST_REQUIRED/);
  assert.match(page, /Non-interactive setup does not grant plugin execution trust/);
  assert.match(page, /Do not disable trust checks globally/);
  assert.match(page, /--replace-credentials/);
  assert.match(page, /grok inspect/);
  assert.match(page, /~\/\.grok\/hooks\/futureagi\.json/);
  assert.match(page, /Keep unrelated hooks and permission guards/);
  assert.match(page, /Uninstall preserves credential profiles and plugin data/);
  assert.match(page, /Export failures do not block your Grok prompt/);
});

// Retain safety checks for the legacy example while existing installations migrate.
test('legacy Grok hook example retains non-blocking commands and the shared installer', () => {
  const hooks = JSON.parse(read('examples/coding-agents/grok-build/futureagi.json'));
  assert.equal(Object.keys(hooks.hooks).length, 12);
  assert.equal(hooks.hooks.PreToolUse, undefined);
  for (const [event, groups] of Object.entries(hooks.hooks)) {
    assert.equal(groups[0].hooks[0].command,
      `(python3 -B "$HOME/.grok/fi-hook-to-otlp/emit.py" grok_build ${event} 2>/dev/null || true)`);
  }
  const installer = read('examples/coding-agents/grok-build/install.sh');
  assert.match(installer, /EMITTER="\$HERE\/\.\.\/hook-to-otlp"/);
  assert.match(installer, /\$EMITTER\/adapters\/grok_build\.py/);
});
