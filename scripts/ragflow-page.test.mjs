import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/no-code/ragflow.mdx', import.meta.url), 'utf8');
const source = '9b2bcb1d1864c75e35ed7d06d3e750725547290e';
const upstream = 'https://github.com/infiniflow/ragflow/pull/22183';

test('RAGFlow guide makes the upstream review and interim build status prominent', () => {
  assert.ok(page.includes(`[infiniflow/ragflow#22183](${upstream})`));
  assert.ok(page.indexOf(upstream) < page.indexOf('## Prerequisites'));
  assert.match(page, /under review/);
  assert.match(page, /Until it is merged and released, use the Future AGI-enabled build below/);
  assert.match(page, /If the contribution ships in a RAGFlow release, stock images of that release will include/);
  assert.match(page, /Stock RAGFlow \*\*v1\.0\.0\*\* images do not include this exporter/);
});

test('RAGFlow guide pins the hardened fork and its matching deployment dependencies', () => {
  const blocks = [...page.matchAll(/```bash\n([\s\S]*?)\n```/g)];
  assert.equal(blocks.length, 1);
  const build = blocks[0][1];
  assert.ok(build.includes(`fetch --depth 200 origin ${source}\n`));
  assert.ok(build.includes('fetch --depth 200 https://github.com/infiniflow/ragflow.git tag v1.0.0\n'));
  assert.ok(build.includes(`checkout --detach ${source}`));
  assert.ok(build.includes('docker buildx build --load --network host --build-arg GOPROXY=https://proxy.golang.org,direct --target production --tag ragflow-futureagi:9b2bcb1d --file ragflow-futureagi/Dockerfile ragflow-futureagi'));
  assert.ok(page.includes('https://github.com/future-agi/ragflow/tree/contrib/futureagi-tracing'));
  assert.ok(page.includes(`https://github.com/future-agi/ragflow/tree/${source}/docker`));
  assert.match(page, /RAGFLOW_IMAGE=ragflow-futureagi:9b2bcb1d/);
  assert.match(page, /DOC_ENGINE=infinity/);
  assert.match(page, /infiniflow\/infinity:v0\.7\.5-x64-v3/);
  assert.match(page, /Linux x86-64/);
  assert.match(page, /MySQL, Infinity, MinIO, Kvrocks and NATS/);
  assert.match(page, /separate deployment and database before migrating/);
  assert.match(page, /Do not downgrade a database migrated by a newer build/);
  assert.match(page, /Do not disable the database version guard/);
  assert.doesNotMatch(page, /60492deb|v1\.0\.0-rc1|v0\.7\.3|pip install|npx .*traceai|copy.*(?:bridge|exporter class)/i);
  const entry = integrations.find(item => item.id === 'ragflow');
  assert.equal(entry?.method, 'RAGFlow settings');
  assert.match(entry?.summary ?? '', /fork/);
});

test('RAGFlow guide uses the current native settings and saved-key editing flow', () => {
  for (const text of ['avatar menu → API', '**Configuration**', '**API key**', '**SECRET KEY**', '**Observe project**', '**Endpoint**', '**Redact content**', '**Save**']) {
    assert.ok(page.includes(text), text);
  }
  assert.match(page, /Leave blank for `https:\/\/api\.futureagi\.com`/);
  assert.match(page, /\/tracer\/v1\/traces/);
  assert.match(page, /Saved keys are masked/);
  assert.match(page, /Leave the key fields blank to keep the saved keys/);
  assert.match(page, /enter both keys again when changing the endpoint/);
  assert.doesNotMatch(page, /enter both keys again when changing any setting/);
});

test('RAGFlow guide preserves the collector host policy and content privacy constraints', () => {
  assert.match(page, /Private, loopback and link-local collector addresses are \*\*blocked by default\*\*/);
  assert.match(page, /both when saving settings and on every export/);
  assert.match(page, /operator must set `ALLOW_ANY_HOST=true` in the RAGFlow server container's environment/);
  assert.match(page, /--force-recreate ragflow-cpu/);
  assert.match(page, /\*\*deployment-wide\*\*/);
  assert.match(page, /not a tenant setting or a collector-specific allowlist/);
  assert.match(page, /other guarded outbound integrations/);
  assert.match(page, /rejects redirects and does not use environment HTTP proxies/);
  assert.match(page, /Future AGI Cloud does not require this opt-in/);
  assert.match(page, /on by default/);
  assert.match(page, /Enable \*\*Redact content\*\* before sending sensitive data/);
  assert.match(page, /Provider error bodies are \*\*never exported\*\*, even with content capture on/);
  assert.match(page, /fixed failure message/);
  assert.match(page, /plaintext database columns/);
  assert.match(page, /not provider billing totals/);
  assert.match(page, /not a durable audit log/);
  for (const span of ['ragflow.chat', 'ragflow.retrieval', 'ragflow.llm']) assert.ok(page.includes(span));
});

test('RAGFlow customer page does not regress to a prototype or verification diary', () => {
  assert.doesNotMatch(page, /prototype|verified development|mocked|SQLite|E2B|sandbox|release gates|publication hold|TH-8233|trace ids|2026-\d{2}-\d{2}|PR #|pull\/1\)/i);
  assert.match(page, /## Configure trace export/);
  assert.match(page, /## Send a chat and inspect its trace/);
});
