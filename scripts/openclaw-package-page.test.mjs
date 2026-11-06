import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/openclaw.mdx', import.meta.url), 'utf8');
test('OpenClaw has a three-step maintained-package quick start', () => {
  assert.match(page, /## 1\. Get your Future AGI keys/);
  assert.match(page, /## 2\. Set up tracing/);
  assert.match(page, /## 3\. Run a local turn/);
  assert.match(page, /npx @traceai\/agents setup openclaw --project coding-agents/);
  assert.match(page, /npx @traceai\/agents run openclaw -- agent --local/);
  assert.doesNotMatch(page, /curl -fsSLO|git clone|hook-to-otlp|run_e2e\.sh/);
});
test('OpenClaw documents privacy, native consent and actual trace shape', () => {
  for (const text of ['Content capture is on by default', '--no-capture-content', 'FI_AGENT_ENABLED=false', 'TRUST_REQUIRED', '0600', 'X-Project-Name', 'project_type=observe', 'rollup', 'several native run traces', 'cost estimates as metrics']) assert.ok(page.includes(text), text);
  assert.doesNotMatch(page, /one trace per user turn|capture.*off by default|verified live|PASS\/FAIL/i);
});
