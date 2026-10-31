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

test('n8n retains native routing, Preview, legacy-node and privacy boundaries', () => {
  assert.ok(page.includes('@future-agi/n8n-nodes-futureagi'));
  assert.ok(page.includes('N8N_OTEL_EXPORTER_OTLP_TRACING_PATH=/tracer/v1/traces'));
  assert.ok(page.includes('OTEL_RESOURCE_ATTRIBUTES="project_name=n8n,project_type=observe"'));
  assert.match(page, /OpenTelemetry tracing Preview/);
  assert.match(page, /Cloud.*project routing/);
  assert.match(page, /older \*\*AI Agent\*\*.*only a `node.execute` span/);
  for (const variable of ['N8N_AGENTS_TRACING_RECORD_INPUTS=false', 'N8N_AGENTS_TRACING_RECORD_OUTPUTS=false', 'N8N_AGENTS_TRACING_ENABLED=false']) {
    assert.ok(page.includes(variable));
  }
  assert.match(page, /tool definitions.*error details/i);
  assert.doesNotMatch(page, /npm (?:install|i) .*@traceai\/n8n/);
});
