import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/runtimes/vercel.mdx', import.meta.url), 'utf8');

test('Vercel platform is discoverable separately from AI SDK and gateway tracing', () => {
  const platform = integrations.find(item => item.id === 'vercel-platform');
  assert.equal(platform.href, '/docs/integrations/runtimes/vercel');
  assert.equal(platform.method, 'Native OTLP');
  for (const id of ['vercel-ai-sdk', 'vercel-ai-gateway']) {
    assert.notEqual(platform.href, integrations.find(item => item.id === id).href);
  }
});

test('platform setup uses one native trace exporter with explicit project routing', () => {
  const config = page.match(/```javascript title="instrumentation.js"\n([\s\S]*?)```/)[1];
  assert.match(config, /OTLPHttpJsonTraceExporter/);
  assert.match(config, /https:\/\/api\.futureagi\.com\/tracer\/v1\/traces/);
  assert.match(config, /project_name: "vercel-web"/);
  assert.match(config, /project_type: "observe"/);
  assert.match(config, /"X-Api-Key": apiKey, "X-Secret-Key": secretKey/);
  assert.doesNotMatch(config, /isFISpan|FISimpleSpanProcessor|FIBatchSpanProcessor|@traceai\/vercel|startSpan/);
  assert.match(page, /FI_HIDE_\*/);
  assert.match(page, /Do not also forward the same traces through a Vercel Trace Drain/);
  assert.match(page, /not model generations/);
});
