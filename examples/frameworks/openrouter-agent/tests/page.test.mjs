import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const read = (rel) => fs.readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const page = read('../../../../src/pages/docs/integrations/frameworks/openrouter-agent.mdx');

test('the page embeds the helper with the clarified privacy comment', () => {
  const helper = read('../futureagi-tracing.mjs').trimEnd().replace(
    '// Privacy: by default only metadata leaves the process. The prompt, tool arguments, tool results\n// and error text are exported only with captureContent / FI_CAPTURE_CONTENT=1. A stack trace is\n// never exported, because it holds absolute local file paths.',
    '// Privacy: prompt, tool payloads and error messages require captureContent / FI_CAPTURE_CONTENT=1.\n// The helper does not read Error.stack. Error messages and custom error names can still\n// contain local paths or sensitive data.',
  );
  assert.ok(page.includes(helper));
});

test('the page states the recipe version and the pinned install', () => {
  const pkg = JSON.parse(read('../package.json')).dependencies;
  assert.equal(pkg['@openrouter/agent'], '0.11.0');
  assert.ok(page.includes('`@openrouter/agent` 0.11.0'));
  assert.ok(page.includes('npm install @openrouter/agent@0.11.0 @openrouter/sdk@0.13.67'));
});

test('the page states the privacy default and the opt-in', () => {
  assert.ok(page.includes('**Default: content capture off.**'));
  assert.ok(page.includes('FI_CAPTURE_CONTENT=1'));
  assert.ok(page.includes('Clipping is not redaction'));
  assert.ok(page.includes('custom error name can itself contain stack text'));
  assert.ok(!page.includes('| Stack traces | Never | Never |'));
});

test('the page describes its scope without a verification diary', () => {
  assert.ok(page.includes('self-hosted Future AGI instance'));
  assert.ok(page.includes('one hooks object for each `callModel()`'));
  assert.ok(!page.includes('Live vendor verification'));
  assert.ok(!page.includes('How this was checked:'));
});

test('the example never uses the OpenAI client or mentions Broadcast', () => {
  for (const file of ['../app.mjs', '../futureagi-tracing.mjs']) {
    const text = read(file);
    assert.ok(!/from 'openai'/.test(text));
    assert.ok(!/broadcast/i.test(text));
  }
});

test('the literal install pins every dependency to the qualified set', () => {
  const dependencies = JSON.parse(read('../package.json')).dependencies;
  const command = page.match(/```bash\nnpm install ([\s\S]*?)```/)[1];
  for (const [name, version] of Object.entries(dependencies)) {
    assert.ok(command.includes(`${name}@${version}`), `${name} must be pinned`);
  }
});

test('supported setup is self-hosted and excludes broader execution modes', () => {
  assert.ok(page.includes('export FI_BASE_URL="http://localhost:4318"'));
  assert.ok(!/not tested|untested|unverified/i.test(page));
});
