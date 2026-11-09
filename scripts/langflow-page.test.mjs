import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/no-code/langflow.mdx', import.meta.url), 'utf8');
const bash = [...page.matchAll(/```bash\n([\s\S]*?)```/g)].map((match) => match[1]);

// Public setup contract; real Langflow/OTLP qualification is recorded in the PR.
test('Langflow uses released native tracing instead of a fork installation', () => {
  assert.match(page, /langflow==1\.13\.1/);
  assert.match(page, /traceloop-sdk==0\.63\.0/);
  assert.match(page, /built-in.*Traceloop integration/);
  assert.doesNotMatch(bash.join('\n'), /git clone|git checkout|pip install -e|traceAI-|openinference-/);
  assert.doesNotMatch(page, /future-agi\/langflow|a988f35f|class \w+(?:Exporter|Processor)/);
  assert.match(page, /Desktop and managed Langflow Cloud deployments are not covered/);
});

test('native configuration enables Langflow and authenticates the correct endpoint', () => {
  assert.match(page, /export TRACELOOP_API_KEY="langflow-otlp"/);
  assert.match(page, /placeholder, not a Traceloop credential/);
  assert.match(page, /export TRACELOOP_BASE_URL="https:\/\/api\.futureagi\.com\/tracer"/);
  assert.match(page, /x-api-key=\{0\},x-secret-key=\{1\}/);
  assert.match(page, /from urllib\.parse import quote/);
  assert.match(page, /OTEL_RESOURCE_ATTRIBUTES="project_name=my-langflow-app,project_type=observe"/);
  assert.match(page, /TRACELOOP_METRICS_ENABLED=false/);
  assert.match(page, /TRACELOOP_LOGGING_ENABLED=false/);
});

test('privacy guidance distinguishes native component payloads from SDK capture', () => {
  assert.match(page, /TRACELOOP_TRACE_CONTENT=true/);
  assert.match(page, /does \*\*not\*\* remove content from Langflow's own component spans/);
  assert.match(page, /not use it as a server-wide redaction switch/);
  assert.match(page, /exception text and stack traces/);
  assert.match(page, /FI_REDACT` settings do not control this native integration/);
  assert.doesNotMatch(page, /collector does not accept gzip|collector rejects gzip|errors? .*without stack traces/i);
});

test('guide keeps operator telemetry and LLM tracing distinct', () => {
  assert.match(page, /service-health export/);
  assert.match(page, /deliberately excludes prompts, completions and component payloads/);
  assert.match(page, /can create duplicate spans/);
  assert.match(page, /text-only API runs/);
  assert.match(page, /Model calls appear as separate traces, not children of the Langflow component trace/);
  assert.match(page, /does not join them into one end-to-end trace/);
  assert.doesNotMatch(page, /Live vendor verification|verified live|2026-\d{2}-\d{2}|PASS\/FAIL|This was checked, not assumed/);
});

test('catalog links the native guide once without a source-fork badge', () => {
  const entries = integrations.filter((item) => item.id === 'langflow');
  assert.equal(entries.length, 1);
  assert.equal(entries[0].name, 'Langflow');
  assert.equal(entries[0].method, 'Native OTLP');
  assert.equal(entries[0].href, '/docs/integrations/no-code/langflow');
});
