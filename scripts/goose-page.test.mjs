import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/goose.mdx', import.meta.url), 'utf8');
test('Goose starts with keys, native setup and the normal agent command', () => {
  const steps = [...page.matchAll(/^## (\d+)\. (.+)$/gm)];
  assert.deepEqual(steps.map(m => m[1]), ['1', '2', '3']);
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
test('Goose media is an existing real product view, accurately captioned', () => {
  const images = [...page.matchAll(/!\[[^\]]*\]\((\/images\/[^)]+)\)/g)];
  assert.equal(images.length, 1);
  for (const [, src] of images) assert.ok(existsSync(fileURLToPath(new URL(`../public${src}`, import.meta.url))));
  assert.match(page, /general support-agent example/);
});
