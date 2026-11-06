import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const read = file => fs.readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/coding-agents/grok-build.mdx');
const hooks = JSON.parse(read('examples/coding-agents/grok-build/futureagi.json'));

test('Grok Build uses the shared installer and a version-scoped POSIX setup', () => {
  const entry = integrations.find(item => item.id === 'grok-build');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/grok-build');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'Hook-to-OTLP');
  assert.match(page, /1\.0\.52 on macOS \(Apple silicon\)/);
  assert.match(page, /POSIX shell commands; Linux, WSL, and native Windows are outside its supported scope/);
  assert.match(page, /Python \*\*3\.9\+\*\*/);
  assert.match(page, /logs and metrics, not traces/);
  assert.match(page, /fi-docs\/examples\/coding-agents\/grok-build\/install\.sh/);
  assert.match(page, /git -C fi-docs pull --ff-only/);
  assert.match(page, /updates the shared emitter and adapter together while preserving your hook file/);
  const installer = read('examples/coding-agents/grok-build/install.sh');
  assert.match(installer, /EMITTER="\$HERE\/\.\.\/hook-to-otlp"/);
  assert.match(installer, /\$EMITTER\/adapters\/grok_build\.py/);
  assert.doesNotMatch(page, /tested with|not tested|verified live|\balpha\b|2026-10-14|test sessions|run_e2e\.sh|in a test/i);
});

test('Grok Build documents the shipped non-blocking hooks and preserves other guards', () => {
  const block = page.match(/```json\n([\s\S]*?)\n```/);
  assert.ok(block, 'Keep the installed hook configuration visible');
  assert.deepEqual(JSON.parse(block[1]), hooks);
  assert.equal(Object.keys(hooks.hooks).length, 12);
  assert.equal(hooks.hooks.PreToolUse, undefined);
  for (const [event, groups] of Object.entries(hooks.hooks)) {
    assert.equal(groups[0].hooks[0].command,
      `(python3 -B "$HOME/.grok/fi-hook-to-otlp/emit.py" grok_build ${event} 2>/dev/null || true)`);
  }
  assert.match(page, /exit 2 from `UserPromptSubmit` blocks the prompt/);
  assert.match(page, /Leave `\[compat\.claude\]` enabled/);
  assert.match(page, /disables \*\*all\*\* Cursor-file hooks inside Grok/);
  assert.match(page, /`durationMs`/);
});

test('Grok Build keeps content opt-in, subagent boundaries and lifecycle caveats', () => {
  for (const term of ['FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'umask 077', 'chmod 600']) {
    assert.ok(page.includes(term), term);
  }
  assert.match(page, /By default only structure and metadata leave your machine/);
  assert.match(page, /FI_HOOK_CAPTURE_CONTENT=1/);
  assert.match(page, /Never exported as metadata/);
  assert.match(page, /emitter never opens the transcript/);
  assert.match(page, /4096 characters/);
  assert.match(page, /each subagent is its own trace/);
  assert.match(page, /grok_build\.subagent\.id/);
  assert.match(page, /Model name, token counts, and cost/);
  assert.match(page, /earlier batch can arrive last/);
  assert.match(page, /session span restarts at the resume time/);
  assert.match(page, /coding_agent\.incomplete=true/);
});
