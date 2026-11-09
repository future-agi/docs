import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/no-code/ragflow.mdx', import.meta.url), 'utf8');
const source = '60492deba70ea7431e13c23de271ab10c3aa0aea';

test('RAGFlow guide scopes onboarding to the pinned fork, not a stock image', () => {
  assert.match(page, /Stock RAGFlow \*\*v1\.0\.0\*\* images do not include this exporter/);
  assert.ok(page.includes(`checkout --detach ${source}`));
  assert.ok(page.includes(`fetch --depth 200 origin ${source} tag v1.0.0-rc1`));
  assert.match(page, /docker buildx build --load --network host --target production/);
  assert.match(page, /Linux x86-64/);
  assert.match(page, /MySQL, Infinity, MinIO, Kvrocks and NATS/);
  assert.match(page, /separate deployment and database/);
  assert.match(page, /Do not disable the database version guard/);
  assert.doesNotMatch(page, /pip install|npx .*traceai|copy.*(?:bridge|exporter class)/i);
  const entry = integrations.find(item => item.id === 'ragflow');
  assert.equal(entry?.method, 'RAGFlow settings');
  assert.match(entry?.summary ?? '', /fork/);
});

test('RAGFlow guide uses the native settings flow and preserves privacy constraints', () => {
  for (const text of ['User settings → API', '**Configuration**', '**API key**', '**Secret key**', '**Observe project**', '**Endpoint**', '**Redact content**', '**Save**']) {
    assert.ok(page.includes(text), text);
  }
  assert.match(page, /https:\/\/api\.futureagi\.com/);
  assert.match(page, /\/tracer\/v1\/traces/);
  assert.match(page, /on by default/);
  assert.match(page, /plaintext database columns/);
  assert.match(page, /enter both keys again/);
  assert.match(page, /not provider billing totals/);
  assert.match(page, /not a durable audit log/);
  for (const span of ['ragflow.chat', 'ragflow.retrieval', 'ragflow.llm']) assert.ok(page.includes(span));
});

test('RAGFlow customer page does not regress to a prototype or verification diary', () => {
  assert.doesNotMatch(page, /prototype|verified development|mocked|SQLite|E2B|sandbox|release gates|publication hold|TH-8233|trace ids|2026-\d{2}-\d{2}|PR #|pull\/1\)/i);
  assert.match(page, /## Configure trace export/);
  assert.match(page, /## Send a chat and inspect its trace/);
});
