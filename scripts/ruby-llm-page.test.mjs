import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/frameworks/ruby-llm.mdx', import.meta.url), 'utf8');
const [native, legacy = ''] = page.split('## Existing RubyLLM 1.x installations');

test('RubyLLM uses released native tracing as the default', () => {
  assert.match(native, /gem "ruby_llm", "2\.1\.1"/);
  assert.match(native, /Ruby 3\.2 or newer/);
  assert.match(native, /RubyLLM::OpenTelemetry\.enable/);
  assert.doesNotMatch(native, /gem "opentelemetry-instrumentation-ruby_llm"|class SanitizingExporter/);
  assert.match(native, /"project_name" =>/);
  assert.match(native, /"project_type" => "observe"/);
  assert.match(native, /"X-Api-Key" => ENV.fetch\("FI_API_KEY"\)/);
  assert.match(native, /"X-Secret-Key" => ENV.fetch\("FI_SECRET_KEY"\)/);
  assert.match(native, /\/tracer\/v1\/traces/);
  assert.match(native, /tracer_provider.shutdown/);
});

test('native setup does not promise legacy content or session parity', () => {
  assert.match(native, /metadata only/i);
  assert.match(native, /does not export prompts, responses, tool arguments or results/);
  assert.match(native, /does not provide.*content-capture/s);
  assert.match(native, /does not add.*session.*user/s);
  assert.match(native, /Do not enable.*third-party.*native/s);
});

test('existing 1.x users retain their bounded compatibility and privacy reference', () => {
  assert.match(legacy, /gem "ruby_llm", "1\.16\.0"/);
  assert.match(legacy, /gem "opentelemetry-instrumentation-ruby_llm", "0\.7\.1"/);
  assert.match(legacy, /class SanitizingExporter/);
  assert.match(legacy, /copy.events = nil/);
  assert.match(legacy, /capture_content: true/);
  assert.match(legacy, /with_otel_attributes/);
  assert.match(legacy, /invoke_agent/);
  assert.match(legacy, /token counts.*inflated/s);
});
