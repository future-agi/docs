import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(fileURLToPath(new URL('../src/pages/docs/integrations/traceai/exa.mdx', import.meta.url)), 'utf8');

test('Exa guide is discoverable and installs the released client wrapper', () => {
  const entry = integrations.find(({ id }) => id === 'exa');
  assert.equal(entry?.href, '/docs/integrations/traceai/exa');
  assert.equal(entry?.method, 'traceAI SDK');
  for (const text of [
    'pip install traceAI-exa', 'exa-py>=2.25.0,<3', 'fi-instrumentation-otel>=1.1.0',
    'ExaInstrumentor().instrument(tracer_provider=trace_provider)', 'trace_provider.force_flush()',
  ]) assert.ok(page.includes(text), text);
});

test('Exa privacy settings apply before the first instrumentation, not as a second call', () => {
  const setup = page.split('## 3. Register and instrument')[1].split('## 4. View the trace')[0];
  const privacy = page.split('## Privacy')[1].split('## Troubleshooting')[0];

  assert.match(setup, /\[privacy settings\]\(#privacy\) before the first `instrument\(\)` call/);
  assert.ok(setup.indexOf('[privacy settings](#privacy)') < setup.indexOf('ExaInstrumentor().instrument('));
  assert.match(privacy, /replace the `ExaInstrumentor\(\)\.instrument\(\.\.\.\)` call in step 3 with the following, before making any Exa requests/);
  assert.match(privacy, /`FI_HIDE_INPUTS=true` before the first `instrument\(\)` call/);
  assert.match(privacy, /Calling `instrument\(\)` again or changing the environment afterward does not reconfigure existing wrappers/);
  assert.match(privacy, /restart your application with the new privacy settings/);
});

test('Exa guide keeps privacy controls and no test diary', () => {
  for (const text of ['FI_HIDE_INPUTS=true', 'TraceConfig(hide_inputs=True)', 'capture_urls=True', '[redacted]']) {
    assert.ok(page.includes(text), text);
  }
  assert.doesNotMatch(page, /Live vendor verification|verified live|Tested versions|live run|fi_verify|trace `?[0-9a-f]{8}-/i);
});
