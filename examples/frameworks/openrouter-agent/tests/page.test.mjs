import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const read = (rel) => fs.readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const page = read('../../../../src/pages/docs/integrations/frameworks/openrouter-agent.mdx');

test('the page embeds the helper file exactly', () => {
  assert.ok(page.includes(read('../futureagi-tracing.mjs').trimEnd()));
});

test('the page states the tested versions and the pinned install', () => {
  const pkg = JSON.parse(read('../package.json')).dependencies;
  assert.equal(pkg['@openrouter/agent'], '0.11.0');
  assert.ok(page.includes('`@openrouter/agent` 0.11.0'));
  assert.ok(page.includes('npm install @openrouter/agent@0.11.0 @openrouter/sdk@0.13.67'));
});

test('the page states the privacy default and the opt-in', () => {
  assert.ok(page.includes('**Default: metadata only.**'));
  assert.ok(page.includes('FI_CAPTURE_CONTENT=1'));
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
