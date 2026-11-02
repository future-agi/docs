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

test('native error coverage distinguishes cooperative failures from forced interruption', () => {
  assert.match(native, /StandardError/);
  for (const mechanism of ['Timeout.timeout', 'Interrupt', 'Thread#kill']) {
    assert.ok(native.includes(mechanism), `Missing ${mechanism} caveat`);
  }
  assert.match(native, /UNSET.*error\.type/s);
  assert.match(native, /UNSET.*not.*success/s);
  assert.match(native, /config\.request_timeout = 30/);
  assert.match(native, /config\.max_retries = 0/);
  assert.match(native, /not.*wall-clock deadline/s);
  assert.match(native, /chat\.cancel/);
  assert.match(native, /RubyLLM::CancelledError/);
  assert.match(native, /cooperative.*checkpoint/s);
});

test('legacy export is held without telling users to remove only its safeguard', () => {
  assert.match(legacy, /Stop exporting.*1\.x/s);
  assert.match(legacy, /gen_ai\.request\.parameters/);
  assert.match(legacy, /capture_content: false/);
  assert.match(legacy, /Do not remove.*SanitizingExporter.*leaving.*instrumentation/s);
  assert.match(legacy, /stop loading.*futureagi_tracing\.rb/s);
  assert.match(legacy, /restart/i);
  assert.match(legacy, /maintained.*package/s);
  assert.match(legacy, /with_otel_attributes/);
  assert.match(legacy, /invoke_agent/);
  assert.doesNotMatch(page, /class SanitizingExporter|METADATA_PREFIXES|title="futureagi_tracing\.rb"/);
});
