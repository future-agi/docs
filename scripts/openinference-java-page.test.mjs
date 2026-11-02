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
