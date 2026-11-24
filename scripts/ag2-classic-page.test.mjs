import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/ag2-classic.mdx', import.meta.url), 'utf8');

test('AG2 Classic is discoverable with a released native-telemetry setup', () => {
  const entry = integrations.find(({ id }) => id === 'ag2-classic');
  assert.equal(entry?.href, '/docs/integrations/traceai/ag2-classic');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'OTel + traceAI');
  for (const value of [
    'autogen.opentelemetry', 'traceAI-ag2-classic==0.1.0',
    'autogen[openai]==0.14.1', 'fi-instrumentation-otel==1.2.3',
    'FI_API_KEY', 'FI_SECRET_KEY', 'OPENAI_API_KEY',
    'from traceai_ag2_classic import setup', 'project_type=ProjectType.OBSERVE',
    'project_name="ag2-classic-demo"', 'agents=[assistant, user]',
    'python ag2_classic_example.py', '**Observe**', '**ag2-classic-demo**',
  ]) assert.ok(page.includes(value), value);
  const example = page.match(/```python\n([\s\S]*?)\n```/)?.[1];
  assert.ok(example);
  assert.ok(example.indexOf('trace_provider = register(') < example.indexOf('tracing = setup('));
  assert.ok(example.indexOf('tracing = setup(') < example.indexOf('user.initiate_chat('));
  assert.match(example, /finally:\n\s+trace_provider\.force_flush\(\)/);
  assert.doesNotMatch(example, /class .*Exporter|class .*Processor|add_span_processor|OTLPSpanExporter/);
});

test('AG2 Classic preserves exporter, privacy and compatibility boundaries without QA prose', () => {
  assert.match(page, /With `fi-instrumentation-otel==1\.2\.3`[^\n]*keeps the registered exporter/);
  assert.doesNotMatch(page, /drops the default exporter|Verified on a real run|mapping tests only|unique marker|latest stable on PyPI|## Tested versions|\balpha\b/i);
  for (const value of [
    'Python 3.10–3.13', 'autogen>=0.14.0,<0.15', 'AG2ClassicCompatibilityError',
    'FI_HIDE_INPUTS=true', 'FI_HIDE_OUTPUTS=true', 'before calling `setup()`',
    'SynchronousMultiSpanProcessor', 'ConcurrentMultiSpanProcessor',
    'exception messages or stack traces', 'error events or status descriptions',
    '`FI_HIDE_ERROR_DETAILS` does not sanitize this native route',
    'output messages contain its full history', 'capture_content=True',
    'overrides the config', 'original privacy settings',
    'tracing.instrument_agent(agent)', 'tracing.instrument_pattern(pattern)',
    'tracing.instrument_a2a_server(server)', 'tracing.uninstrument()',
  ]) assert.ok(page.includes(value), value);
  assert.doesNotMatch(page, /Local paths[^\n]*were not exported/);
});
