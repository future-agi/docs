import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Use the production converter, not a duplicate of its semantic mapping.
// Authentication/project resolution are tested separately by the collector;
// this contract verifies that the exact guide's wire spans survive conversion.
const [binary, version] = process.argv.slice(2);
assert.ok(binary && version, 'Usage: node check-ingestion.mjs CONVERTER ELASTICSEARCH_VERSION');
const examples = ['NativeElasticsearchExample', 'AsyncElasticsearchExample', 'KnnElasticsearchExample'];
if (version === '8.12.0') examples.push('OptionalElasticsearchExample');
for (const example of examples) {
  const filename = fileURLToPath(new URL(`./target/wire/${version}/${example}.pb`, import.meta.url));
  const output = execFileSync(binary, [filename], { encoding: 'utf8', timeout: 30_000 });
  const rows = output.trim().split('\n').map(line => JSON.parse(line));
  const optional = example.startsWith('Optional');
  assert.equal(rows.length, optional ? 2 : 1, example);
  const database = rows.find(row => row.name === 'search');
  assert.ok(database, example);
  assert.equal(database.observation_type, 'unknown', 'native database spans are not semantic retrievers');
  assert.equal(database.attrs_string['db.system.name'] ?? database.attrs_string['db.system'], 'elasticsearch');
  assert.equal(database.attrs_string['db.operation.name'] ?? database.attrs_string['db.operation'], 'search');
  assert.equal(database.attrs_string['db.elasticsearch.path_parts.index'], 'documents');
  for (const row of rows) {
    assert.equal(row.service_name, 'elasticsearch-search');
    assert.equal(row.resource_attrs.project_name, 'elasticsearch-native-test');
    assert.equal(row.resource_attrs.project_type, 'observe');
    assert.match(row.id, /^[0-9a-f]{16}$/);
    assert.match(row.trace_id, /^[0-9a-f-]{36}$/);
    assert.ok(row.latency_ms >= 0);
    assert.equal(row.total_tokens, 0);
    assert.equal(row.cost, 0);
    assert.equal(row.input, '');
    assert.equal(row.output, '');
  }
  if (optional) {
    const parent = rows.find(row => row.observation_type === 'retriever');
    assert.ok(parent);
    assert.equal(database.parent_span_id, parent.id);
    assert.equal(database.trace_id, parent.trace_id);
    assert.equal(parent.attrs_number['retriever.top_k'], 5);
    assert.equal(parent.attrs_number['db.vector.results.count'], 1);
    assert.equal(parent.parent_span_id, '');
  } else {
    assert.equal(database.parent_span_id, '');
  }
  for (const canary of ['synthetic-fi-key', 'synthetic-fi-secret', 'synthetic-es-key', 'synthetic-response-content', 'observability']) {
    assert.ok(!output.includes(canary), `Unexpected payload content: ${canary}`);
  }
  console.log(`PASS ${version} ${example}: ${rows.length} production span rows`);
}
