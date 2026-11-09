import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/goose.mdx', import.meta.url), 'utf8');

test('Goose discovery links to the maintained plugin guide', () => {
  const entry = integrations.find(integration => integration.id === 'goose');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/goose');
  assert.equal(entry?.method, 'traceAI plugin');
});

test('Goose documents scoped settings, file locations and lifecycle controls', () => {
  assert.match(page, /1\.54 or later in the 1\.x line/);
  assert.match(page, /setup goose --user-only --project coding-agents/);
  assert.match(page, /setup goose --scope project --project-dir \. --project my-project/);
  assert.match(page, /If you also have user-scoped Goose setup/);
  for (const path of ['~/.config/goose/futureagi.json', '<project>/.futureagi/agents.json', '~/.config/futureagi/agents/credentials.json', '~/.agents/plugins/futureagi-goose']) {
    assert.ok(page.includes(path), `Missing configuration path: ${path}`);
  }
  for (const command of ['status goose --check', 'doctor goose', 'disable goose', 'enable goose', 'uninstall goose']) {
    assert.ok(page.includes(`npx @traceai/agents ${command}`), `Missing lifecycle command: ${command}`);
  }
  assert.match(page, /Goose Desktop tracing and cross-session subagent nesting are \*\*not yet available\*\*/);
  assert.doesNotMatch(page, /verified live|run ids?|internal hold|QA runner/i);
});
test('Goose starts with keys, native setup and the normal agent command', () => {
  // Three-step layout is enforced by coding-agents-contract.test.mjs.
  assert.match(page, /npx @traceai\/agents setup goose --project coding-agents/);
  assert.match(page, /goose run -t/);
  assert.doesNotMatch(page, /git clone|curl -fsSLO|otelcol-contrib --config|run_e2e\.sh/);
});
test('Goose explains content-on privacy, native-export migration and recorded timing limits', () => {
  assert.match(page, /captured by default/);
  assert.match(page, /FI_AGENT_CAPTURE_CONTENT=false/);
  assert.match(page, /FI_AGENT_ENABLED=false/);
  assert.match(page, /OTEL_TRACES_EXPORTER=none/);
  assert.match(page, /not native request timings/);
  assert.match(page, /not the complete provider context/);
  assert.match(page, /cross-session subagent nesting/);
});
test('Goose explains deferred interactive delivery before opening traces and in troubleshooting', () => {
  const run = page.split('<Step title="Run the agent and open the trace">')[1].split('</Step>')[0];
  assert.match(run, /For your first trace, run a task directly/);
  assert.match(run, /submit another prompt or exit normally/);
  assert.match(run, /exports before the command exits/);
  assert.match(page, /Configured but no traces[^\n]*submit another prompt or exit normally/);
  assert.doesNotMatch(page, /exported when Goose finishes the turn/);
});
test('Goose media is a real Goose trace, accurately captioned', () => {
  const images = [...page.matchAll(/!\[([^\]]*)\]\((\/images\/[^)]+)\)/g)];
  assert.deepEqual(images.map(m => m[2]), ['/images/docs/integrations/coding-agents/goose-trace.png']);
  for (const [, , src] of images) assert.ok(existsSync(fileURLToPath(new URL(`../public${src}`, import.meta.url))));
  assert.match(images[0][1], /Goose turn/);
  assert.ok(page.includes('src="/images/docs/integrations/coding-agents/goose-trace.mp4"'));
  assert.doesNotMatch(page, /general support-agent example|dashboard-trace-detail/);
});
