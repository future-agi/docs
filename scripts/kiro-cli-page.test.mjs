import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/kiro-cli.mdx', import.meta.url), 'utf8');
const hooks = JSON.parse(readFileSync(new URL('../examples/coding-agents/kiro-cli/fi-hook-to-otlp-kiro-cli.json', import.meta.url), 'utf8'));

test('Kiro CLI is discoverable with an explicit platform boundary and shared installer', () => {
  const entry = integrations.find(({ id }) => id === 'kiro-cli');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/kiro-cli');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'Hook-to-OTLP');
  assert.match(page, /2\.31\.1 on macOS \(Apple silicon\)/);
  assert.match(page, /Linux, WSL, native Windows, cloud sessions, and Kiro IDE are outside/);
  assert.match(page, /\]\(\/docs\/integrations\/coding-agents\/hook-to-otlp\)/);
  for (const scope of ['/path/to/your/project', '--user', '--agent-profile']) {
    assert.ok(page.includes(`fi-docs/examples/coding-agents/kiro-cli/install.sh ${scope}`));
  }
  const command = hooks.hooks.find(({ trigger }) => trigger === 'PostToolUse').action.command;
  assert.ok(page.includes(command), 'Document the actual shipped guarded command');
  assert.doesNotMatch(page, /```python|cp .*emit\.py/);
});

test('Kiro CLI keeps scope collision, privacy and tool-coverage limits actionable', () => {
  assert.match(page, /CLI and Kiro IDE load the same standalone hook files/);
  assert.match(page, /Use \*\*one scope only\*\*/);
  assert.match(page, /Profile-scoped hooks do not replace standalone hooks/);
  assert.match(page, /kiro-cli chat --v3 --agent my-cli-agent/);
  assert.match(page, /FI_HOOK_CAPTURE_CONTENT=1/);
  assert.match(page, /tool error text, and assistant responses stay off/);
  assert.match(page, /not a data-loss-prevention control/);
  assert.match(page, /Some failed calls also produce no completion event/);
  assert.match(page, /Tool duration is unavailable/);
  assert.match(page, /inactive state files expire after 24 hours/);
  assert.doesNotMatch(page, /https:\/\/docs\.futureagi\.com\/docs\/integrations\/coding-agents\/kiro-ide/);
  assert.doesNotMatch(page, /Live verification|Checked with|read 2026-|fi_verify|run_e2e\.sh|not tested|free tier|Google sign-in/i);
});
