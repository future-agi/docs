import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrationAids } from '../src/lib/integrations.mjs';

const read = route => readFileSync(new URL(`../src/pages/docs/${route}.mdx`, import.meta.url), 'utf8');
const config = read('sdk/tracing/trace-config');
const environment = read('sdk/tracing/environment-variables');
const masking = read('sdk/tracing/mask-span-attributes');
const exceptions = read('sdk/tracing/add-events-exceptions-status');
const troubleshooting = read('observe/troubleshooting/missing-attributes');
const errors = config.split('## Errors and privacy')[1]?.split('## Cap attribute size')[0];

test('error privacy reference is discoverable and uses published core versions', () => {
  assert.ok(integrationAids.some(aid => aid.href === '/docs/sdk/tracing/trace-config'));
  assert.ok(errors, 'Keep the errors and privacy reference');
  for (const page of [config, environment, masking]) {
    assert.match(page, /`fi-instrumentation-otel` 1\.2\.3/);
    assert.match(page, /`@traceai\/fi-core` 1\.1\.1/);
    assert.doesNotMatch(page, /`fi-instrumentation-otel` 1\.2\.0\b/);
  }
  assert.doesNotMatch(errors, /must be published|next release|Fixes for them are being followed up|17 packages|Java and C# don't support it yet|same release/i);
});

test('error privacy retains failure classifications and removes known error text', () => {
  for (const key of ['error.type', 'exception.type', 'exception.escaped']) {
    const row = errors.split('\n').find(line => line.startsWith(`| \`${key}\``));
    assert.ok(row, `Document ${key}`);
    assert.match(row, /\| Kept(?: when set)? \|$/);
  }
  assert.match(errors, /\| Status code \| Span status \| `ERROR` \| `ERROR` \|/);
  assert.match(errors, /\| Status description[^\n]*\| Empty \|/);
  for (const key of ['exception.message', 'exception.stacktrace', 'error.message']) {
    const row = errors.split('\n').find(line => line.startsWith(`| \`${key}\``));
    assert.match(row ?? '', /\| Dropped \|$/);
  }
  for (const suffix of ['.exception.message', '.exception.stacktrace', '.error.message', '.error_message']) {
    assert.ok(errors.includes(`\`${suffix}\``));
  }
  assert.match(errors, /module-qualified in Python, class name in TypeScript/);
  assert.match(errors, /Output of a failed LangChain run[^\n]*\| Dropped \|/);
});

test('derived default uses only the six resolved content flags with explicit overrides', () => {
  const defaults = errors.split('### Default')[1]?.split('### Scope')[0];
  assert.ok(defaults);
  for (const flag of ['hide_inputs', 'hide_outputs', 'hide_input_messages', 'hide_output_messages', 'hide_input_text', 'hide_output_text']) {
    assert.ok(defaults.includes(`\`${flag}\``));
    assert.ok(environment.includes(`\`${flag}\``));
  }
  assert.match(defaults, /Off otherwise/);
  assert.match(defaults, /`hide_input_images`, `hide_embedding_vectors`, `hide_llm_invocation_parameters`, and `pii_redaction` don't affect it/);
  assert.match(defaults, /value set in code takes precedence over the environment variable/);
  assert.match(defaults, /`False` or `FI_HIDE_ERROR_DETAILS=false`[^\n]*Off, even when content is hidden/);
  assert.match(environment, /explicit environment value takes precedence over the derived default/);
  assert.match(troubleshooting, /image-only masking does not enable it/);
});

test('privacy scope does not promise exporter-wide filtering or retain obsolete exclusions', () => {
  assert.match(errors, /not an exporter-wide filter/);
  assert.match(errors, /plain OpenTelemetry tracer is not filtered/);
  assert.match(errors, /Native integrations have their own content controls/);
  assert.match(errors, /redaction in an OpenTelemetry Collector/);
  assert.match(errors, /`traceai-chromadb` 0\.2\.0 use this wrapper/);
  assert.doesNotMatch(errors, /These instrumentors bypass|Python: a2a|TypeScript: `@traceai\/llamaindex`/);
  assert.match(masking, /not an exporter-wide filter/);
  assert.doesNotMatch(masking, /accepted by all traceAI auto-instrumentors|apply globally to all instrumentors/);
  assert.match(exceptions, /Plain OpenTelemetry spans are not filtered/);
});

test('examples hide error details and diagnostics use a maintained exporter', () => {
  const examples = errors.split('### Example')[1];
  assert.ok(examples);
  assert.match(examples, /hide_error_details=True/);
  assert.match(examples, /hideErrorDetails: true/);
  assert.match(examples, /export FI_HIDE_ERROR_DETAILS=true/);
  assert.doesNotMatch(examples, /hide_error_details=False|hideErrorDetails: false|export FI_HIDE_ERROR_DETAILS=false/);
  assert.match(errors, /Error messages can expose prompts and other sensitive data/);
  for (const page of [environment, masking, exceptions, troubleshooting]) {
    assert.ok(page.includes('/docs/sdk/tracing/trace-config#errors-and-privacy'));
  }
  assert.match(troubleshooting, /SimpleSpanProcessor\(ConsoleSpanExporter\(\)\)/);
  assert.match(troubleshooting, /Use synthetic data/);
  assert.doesNotMatch(troubleshooting, /class PrintAttributes/);
});
