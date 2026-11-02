import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/crewai.mdx', import.meta.url), 'utf8');
const [native, legacy = ''] = page.split('## Existing traceAI installations');

test('CrewAI leads with the published native lifecycle route', () => {
  assert.match(native, /crewai>=1\.15\.33/);
  assert.match(native, /opentelemetry-exporter-otlp-proto-http/);
  assert.match(native, /from crewai\.telemetry\.tracing import telemetry_session/);
  assert.match(native, /with telemetry_session\(/);
  assert.match(native, /"https:\/\/api\.futureagi\.com\/tracer\/v1\/traces"/);
  assert.match(native, /"X-Api-Key": os\.environ\["FI_API_KEY"\]/);
  assert.match(native, /"X-Secret-Key": os\.environ\["FI_SECRET_KEY"\]/);
  assert.match(native, /"project_name": "crewai_project"/);
  assert.match(native, /"project_type": "observe"/);
  assert.doesNotMatch(native, /CrewAIInstrumentor\(\)|class .*Exporter|def .*export/);
});

test('native privacy and duplicate-span boundaries are actionable', () => {
  assert.match(native, /CREWAI_DISABLE_TELEMETRY=true/);
  assert.match(native, /CREWAI_TRACING_ENABLED=false/);
  assert.match(native, /Do not.*instrumentor.*same execution/s);
  assert.match(native, /FI_HIDE_INPUTS.*FI_HIDE_OUTPUTS.*do not apply/s);
  assert.match(native, /state.*error/s);
});

test('existing package users retain their supported route and scope', () => {
  assert.match(legacy, /traceAI-crewai>=0\.1\.10/);
  assert.match(legacy, /Flow.*standalone.*model/s);
  assert.match(legacy, /0\.41\.1.*telemetry.*upgrade/s);
  assert.match(legacy, /FI_HIDE_INPUTS/);
  assert.doesNotMatch(page, /verified live|PASS\/FAIL|test dates|class SanitizingExporter/i);
});
