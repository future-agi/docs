import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/import/openinference.mdx', import.meta.url), 'utf8');
const java = page.split('<Tab title="Java">')[1]?.split('</Tab>')[0] ?? '';

test('OpenInference retains Python and adds a released native Java annotation route', () => {
  assert.match(page, /OpenAIInstrumentor\(\)\.instrument/);
  assert.match(java, /openinference-instrumentation-annotation<\/artifactId>/);
  assert.match(java, /<openinference.version>0\.1\.2<\/openinference.version>/);
  assert.match(java, /OpenInferenceAgentInstaller\.install\(\)/);
  assert.match(java, /OpenInferenceAgent\.register\(new OITracer/);
  assert.match(java, /-javaagent:target\/dependency\/byte-buddy-agent-1\.14\.12\.jar/);
  assert.doesNotMatch(java, /ai\.traceai\.|traceai-java/);
});

test('Java owns one OTLP exporter with project routing and bounded shutdown', () => {
  assert.equal((java.match(/OtlpHttpSpanExporter\.builder\(/g) ?? []).length, 1);
  for (const expected of ['project_name', 'project_type', 'X-Api-Key', 'X-Secret-Key', '/tracer', '/v1/traces']) {
    assert.ok(java.includes(expected), `Missing ${expected}`);
  }
  assert.match(java, /provider\.shutdown\(\)\.join\(10, TimeUnit\.SECONDS\)/);
  assert.match(java, /Do not add.*second exporter/);
});

test('Java exclusion applies only to automatic capture, not explicit mappings', () => {
  assert.match(java, /@ExcludeFromSpan[^\n]*automatic argument capture only/);
  assert.match(java, /@SpanMapping[^\n]*bypasses[^\n]*exclusion/);
  assert.match(java, /Never map sensitive or excluded parameters/);
  assert.doesNotMatch(java, /parameters that must never be captured/);
});

test('Java restricts annotations to non-void methods and explains class-wide failure', () => {
  assert.match(java, /synchronous Java methods with non-void return types/);
  assert.match(java, /annotated `void` method[^\n]*entire class/);
  assert.match(java, /Leave `void` methods unannotated[^\n]*non-void caller/);
  const troubleshooting = java.split('### Java troubleshooting')[1];
  assert.match(troubleshooting, /No spans[^\n]*`void`/);
  assert.match(troubleshooting, /Cannot assign void to class java.lang.Object/);
});

test('Java documents synchronous annotations and its distinct privacy controls', () => {
  assert.match(java, /synchronous/);
  assert.match(java, /\.hideInputs\(true\)/);
  assert.match(java, /\.hideOutputs\(true\)/);
  assert.match(java, /exception.*status.*events/is);
  assert.match(java, /OPENINFERENCE_HIDE_\*/);
  assert.match(java, /@Agent/);
  assert.match(java, /@Tool/);
  assert.doesNotMatch(page, /This recipe supports the Python OpenAI instrumentor only/);
});
