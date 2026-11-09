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
  assert.match(native, /traces_endpoint: https:\/\/api\.futureagi\.com\/tracer\/v1\/traces/);
  assert.match(native, /X-Api-Key: \$\{env:FI_API_KEY\}/);
  assert.match(native, /X-Secret-Key: \$\{env:FI_SECRET_KEY\}/);
  assert.match(native, /OTLPSpanExporter\(endpoint="http:\/\/127\.0\.0\.1:4318\/v1\/traces"\)/);
  assert.doesNotMatch(native, /endpoint="https:\/\/api\.futureagi\.com/);
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

test('the required Collector filters configuration and assigns lifecycle types', () => {
  assert.match(native, /Do not export native sessions directly to Future AGI/);
  assert.match(native, /Collector Contrib 0\.164\.0/);
  assert.match(native, /otelcol-contrib validate --config=crewai-collector\.yaml/);
  assert.match(native, /error_mode: propagate/);
  assert.match(native, /delete_key\(attributes, "crewai\.llm\.available_functions"\)/);
  assert.match(native, /delete_key\(attributes, "crewai\.llm\.callbacks"\)/);
  assert.match(native, /set\(attributes\["fi\.span\.kind"\], "agent"\).*"invoke_agent"/s);
  assert.match(native, /set\(attributes\["fi\.span\.kind"\], "chain"\).*"invoke_workflow".*"execute_task".*"execute_method"/s);
  assert.match(native, /processors: \[transform\/crewai\]/);
  assert.match(native, /Keep the local receiver private/);
  assert.match(native, /FI_HIDE_ERROR_DETAILS/);
});

test('existing package users retain their supported route and scope', () => {
  assert.match(legacy, /traceAI-crewai>=0\.1\.10/);
  assert.match(legacy, /Flow.*standalone.*model/s);
  assert.match(legacy, /0\.41\.1.*telemetry.*upgrade/s);
  assert.match(legacy, /FI_HIDE_INPUTS/);
  assert.doesNotMatch(page, /verified live|PASS\/FAIL|test dates|class SanitizingExporter/i);
});
