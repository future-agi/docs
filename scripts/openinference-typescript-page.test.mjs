import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/import/openinference.mdx', import.meta.url), 'utf8');
const typescript = page.split('<Tab title="TypeScript">')[1]?.split('</Tab>')[0] ?? '';

test('OpenInference offers released native TypeScript wrappers and standard decorators', () => {
  assert.ok(typescript, 'Missing native TypeScript setup');
  assert.match(typescript, /@arizeai\/openinference-core@2\.8\.1/);
  assert.match(typescript, /2\.8\.0 or later/);
  assert.match(typescript, /traceAgent\(/);
  assert.match(typescript, /@observe\(/);
  assert.match(typescript, /standard decorators/);
  assert.doesNotMatch(typescript, /@traceai\/|class .*Exporter/);
});

test('TypeScript owns one exporter, routes the project, and flushes on exit', () => {
  assert.equal((typescript.match(/new OTLPTraceExporter\(/g) ?? []).length, 1);
  for (const value of ['"project_name": "my-openinference-project"', '"project_type": "observe"',
    '"X-Api-Key": process.env.FI_API_KEY', '"X-Secret-Key": process.env.FI_SECRET_KEY',
    'https://api.futureagi.com/tracer', '/v1/traces']) {
    assert.ok(typescript.includes(value), `Missing ${value}`);
  }
  assert.match(typescript, /finally\s*{\s*await provider\.shutdown\(\)/);
  assert.match(typescript, /Do not.*second exporter/);
  assert.match(typescript, /openinference\.project\.name/);
});

test('TypeScript explains native content controls without promising exception redaction', () => {
  assert.match(typescript, /new OITracer\(/);
  assert.match(typescript, /traceConfig: \{\}/);
  assert.match(typescript, /@observe\(\{ tracer,/);
  assert.match(typescript, /\}, \{ tracer, name: "garden-planner" \}\)/);
  assert.match(typescript, /OPENINFERENCE_HIDE_INPUTS=true/);
  assert.match(typescript, /OPENINFERENCE_HIDE_OUTPUTS=true/);
  assert.match(typescript, /exception messages.*status.*events/is);
  assert.match(typescript, /FI_HIDE_\*/);
  assert.match(typescript, /does not.*model names or token usage/is);
});

test('Existing Python and Java routes remain intact', () => {
  assert.match(page, /<Tab title="Python">/);
  assert.match(page, /OpenAIInstrumentor\(\)\.instrument\(tracer_provider=provider\)/);
  assert.match(page, /<Tab title="Java">/);
  assert.match(page, /OpenInferenceAgent\.register\(new OITracer/);
});
