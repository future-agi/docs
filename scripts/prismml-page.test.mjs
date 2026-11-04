import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations, integrationSearchText } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/providers/prismml.mdx', import.meta.url), 'utf8');

test('PrismML is discoverable as a local OpenAI-client integration', () => {
  const item = integrations.find(entry => entry.id === 'prismml');
  assert.equal(item.href, '/docs/integrations/providers/prismml');
  assert.equal(item.method, 'OpenAI client');
  assert.equal(item.category, 'providers');
  for (const term of ['bonsai', 'prismml', 'llama.cpp']) {
    assert.ok(integrationSearchText(item).includes(term));
  }
});

test('PrismML guide uses released packages and keeps local model and trace export separate', () => {
  for (const text of [
    'openai==3.42.1', 'traceAI-openai==0.1.12', 'fi-instrumentation-otel==1.2.2',
    'http://localhost:8080/v1', 'https://api.futureagi.com/tracer/v1/traces',
    'FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'PRISMML_BASE_URL',
    'OpenAIInstrumentor().instrument(tracer_provider=provider)', 'provider.force_flush()',
    'FI_HIDE_INPUTS=true', 'FI_HIDE_OUTPUTS=true', 'FI_HIDE_LLM_INVOCATION_PARAMETERS=true',
    '--alias bonsai', 'absolute path', 'does not authenticate requests',
  ]) assert.ok(page.includes(text), text);
  assert.doesNotMatch(page, /verified live|verification|fixture|test dates|QA|span\.set_attribute|class .*Exporter/i);
  assert.equal((page.match(/```python/g) || []).length, 1);
});
