import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/n8n.mdx', import.meta.url), 'utf8');

test('n8n native model coverage distinguishes token-bearing children and aggregate parents', () => {
  for (const value of ['2.45.7', '@n8n/agents', '0.30.6', 'ai.generateText.doGenerate', 'ai.streamText.doStream', 'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens', 'gen_ai.request.model', 'gen_ai.response.model', 'ai.usage.inputTokens', 'ai.usage.outputTokens']) {
    assert.ok(page.includes(value), `Missing native coverage: ${value}`);
  }
  assert.doesNotMatch(page, /agent spans carry no token counts|Observe shows no token usage or cost/);
  assert.match(page, /do not add parent totals/i);
  assert.match(page, /classification.*cost.*depend on/i);
});

test('n8n retains Preview, legacy-node and privacy boundaries', () => {
  assert.ok(page.includes('@future-agi/n8n-nodes-futureagi'));
  assert.match(page, /OpenTelemetry tracing Preview/);
  assert.match(page, /n8n Cloud.*plan and version support/);
  assert.doesNotMatch(page, /Cloud.*resource attribute required/);
  assert.match(page, /older \*\*AI Agent\*\*.*only a `node.execute` span/);
  for (const variable of ['N8N_AGENTS_TRACING_RECORD_INPUTS=false', 'N8N_AGENTS_TRACING_RECORD_OUTPUTS=false', 'N8N_AGENTS_TRACING_ENABLED=false']) {
    assert.ok(page.includes(variable));
  }
  assert.match(page, /tool definitions.*error details/i);
  assert.doesNotMatch(page, /npm (?:install|i) .*@traceai\/n8n/);
});

test('n8n Settings route supplies authentication and project headers without environment access', () => {
  const settings = page.split('#### Settings > OpenTelemetry\n')[1]?.split('\n#### ')[0];
  assert.ok(settings, 'Missing Settings setup');
  for (const value of ['2.27.0', 'owner or admin', 'https://api.futureagi.com', '/tracer/v1/traces', 'http/protobuf', 'X-Api-Key=<your-api-key>,X-Secret-Key=<your-secret-key>,X-Project-Name=n8n']) {
    assert.ok(settings.includes(value), `Missing Settings configuration: ${value}`);
  }
  assert.match(settings, /without a process restart/);
  assert.match(settings, /do not need `OTEL_RESOURCE_ATTRIBUTES`/);
  assert.match(settings, /Environment variables take precedence/);
  assert.match(page, /v1\.58\.0 or later for project-header routing/);
  assert.doesNotMatch(page, /so you still set `OTEL_RESOURCE_ATTRIBUTES`/);
});

test('n8n keeps resource routing as an alternative and limits missing-project failures to neither route', () => {
  const environment = page.split('#### Environment variables (self-hosted alternative)\n')[1]?.split('\n### ')[0];
  assert.ok(environment, 'Missing environment-based alternative');
  assert.ok(environment.includes('N8N_OTEL_EXPORTER_OTLP_TRACING_PATH=/tracer/v1/traces'));
  assert.ok(environment.includes('OTEL_RESOURCE_ATTRIBUTES="project_name=n8n,project_type=observe"'));
  assert.match(environment, /restart n8n/);
  assert.match(environment, /`project_name` resource attribute takes precedence over `X-Project-Name`/);
  assert.match(environment, /neither a `project_name` attribute nor an `X-Project-Name` header.*HTTP 400/);

  const warning = [...page.matchAll(/<Warning>([\s\S]*?)<\/Warning>/g)]
    .map(match => match[1]).find(text => text.includes('Send test trace'));
  assert.ok(warning, 'Missing resource-only test-trace guidance');
  assert.match(warning, /does not include `OTEL_RESOURCE_ATTRIBUTES`/);
  assert.match(warning, /resource-only routing.*neither a `project_name` resource attribute nor an `X-Project-Name` header/);
  assert.match(warning, /Add `X-Project-Name=n8n`.*Send test trace/);
  assert.doesNotMatch(page, /Don't use \*\*Send test trace\*\*/);
});
