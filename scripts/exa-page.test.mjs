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

test('Exa guide keeps privacy controls and no test diary', () => {
  for (const text of ['FI_HIDE_INPUTS=true', 'TraceConfig(hide_inputs=True)', 'capture_urls=True', '[redacted]']) {
    assert.ok(page.includes(text), text);
  }
  assert.doesNotMatch(page, /Live vendor verification|verified live|Tested versions|live run|fi_verify|trace `?[0-9a-f]{8}-/i);
});
