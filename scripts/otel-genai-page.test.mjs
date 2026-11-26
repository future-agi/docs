import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrationAids, integrations } from '../src/lib/integrations.mjs';

const route = '/docs/integrations/traceai/otel-genai-conformance';
const page = readFileSync(new URL(`../src/pages${route}.mdx`, import.meta.url), 'utf8');

// Mapping source: future-agi/future-agi v1.58.0, fi-collector/pkg/adapter/adapter.go
// and exporter/clickhouse25exporter/converter.go. Gzip and deprecated-token
// support also exist in v1.56.0. These are page contracts, not collector tests.
function rowCells(label) {
  const row = page.split('\n').find(line => line.startsWith(`| ${label} |`));
  assert.ok(row, `Missing reference row: ${label}`);
  return row.split('|').slice(1, -1).map(cell => cell.trim());
}

test('GenAI compatibility is a discoverable reference, not a separate instrumentor', () => {
  assert.deepEqual(integrationAids.find(aid => aid.href === route), {
    name: 'OpenTelemetry GenAI compatibility',
    href: route,
  });
  assert.ok(!integrations.some(integration => integration.href === route));
  assert.match(page, /native OpenTelemetry GenAI spans/);
  assert.match(page, /do not need a second instrumentor or a custom exporter/);
  assert.match(page, /\[integration guide\]\(\/docs\/integrations\)/);
  assert.match(page, /\[OpenInference guide\]\(\/docs\/integrations\/import\/openinference\)/);
});

test('GenAI alias priorities include deprecated tokens without double-counting', () => {
  const aliases = {
    Model: ['llm.model_name', 'gen_ai.request.model', 'gen_ai.response.model', 'llm.request.model'],
    Provider: ['gen_ai.provider.name', 'llm.system', 'gen_ai.system', 'llm.vendor', 'llm.provider'],
    'Input tokens': ['llm.token_count.prompt', 'gen_ai.usage.input_tokens', 'llm.usage.prompt_tokens', 'gen_ai.usage.prompt_tokens'],
    'Output tokens': ['llm.token_count.completion', 'gen_ai.usage.output_tokens', 'llm.usage.completion_tokens', 'gen_ai.usage.completion_tokens'],
    'Total tokens': ['llm.token_count.total', 'gen_ai.usage.total_tokens', 'llm.usage.total_tokens'],
  };
  for (const [field, expected] of Object.entries(aliases)) {
    assert.deepEqual([...rowCells(field)[1].matchAll(/`([^`]+)`/g)].map(match => match[1]), expected, field);
  }
  assert.match(page, /first non-empty string wins/);
  assert.match(page, /first numeric value wins, including an explicit zero/);
  assert.match(page, /If no total-token alias supplies a numeric value, the collector derives the total from input plus output tokens/);
  assert.match(page, /Aliases on the same span are selected, not added/);
  assert.match(page, /does not deduplicate separate spans/);
});

test('GenAI reference documents HTTP gzip support with its release boundary', () => {
  assert.equal(rowCells('Cloud trace endpoint')[1], '`https://api.futureagi.com/tracer/v1/traces`');
  assert.match(rowCells('Authentication headers')[1], /`X-Api-Key` and `X-Secret-Key`/);
  assert.match(rowCells('Resource attributes')[1], /`project_name`.*`project_type=observe`/);
  assert.match(rowCells('Payload format')[1], /application\/x-protobuf.*application\/json/);
  assert.equal(rowCells('HTTP compression')[1], 'Uncompressed or `Content-Encoding: gzip`');
  assert.match(page, /Gzip and the deprecated GenAI token aliases below are supported in self-hosted v1\.56\.0 and later/);
  assert.match(page, /both compressed and decompressed request sizes/);
  assert.doesNotMatch(page, /gzip bodies are rejected|old token names are not read/i);
});

test('GenAI reference preserves type and privacy limits without a fixture diary', () => {
  assert.match(page, /collector mapping in Future AGI v1\.58\.0/);
  assert.equal(rowCells('`chat`, `generate_content`, `text_completion`')[1], '`llm`');
  assert.equal(rowCells('`embeddings`')[1], '`embedding`');
  assert.equal(rowCells('`execute_tool`')[1], '`tool`');
  assert.equal(rowCells('`invoke`')[1], '`chain`');
  assert.equal(rowCells('`invoke_agent`, `retrieval`')[1], '`unknown`');
  assert.match(page, /explicit span-kind attribute takes precedence/);
  assert.match(page, /exception event alone does not set the span's status/);
  assert.match(page, /Disable content capture in that instrumentor or redact sensitive fields in an OpenTelemetry Collector before export/);
  assert.match(page, /hiding message content also removes exception text/);
  assert.doesNotMatch(page, /Tested versions|Verified \d{4}|Run the fixture tests|live_check\.py|pytest|era_[ab]\.json|FI_COLLECTOR_ADAPTER_GO|golden file/i);
});
