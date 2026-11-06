import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(
  new URL('../src/pages/docs/integrations/traceai/firecrawl.mdx', import.meta.url),
  'utf8',
);

// Page contracts, not a claim of live API execution. Version and lifecycle
// assertions follow the released traceAI-firecrawl 0.1.1 wheel.
test('Firecrawl setup uses released packages and instruments before client construction', () => {
  assert.match(page, /traceAI-firecrawl==0\.1\.1/);
  assert.match(page, /firecrawl-py==4\.50\.0/);
  assert.match(page, /fi-instrumentation-otel==1\.2\.3/);
  assert.match(page, /Python 3\.10–3\.13/);
  assert.match(page, /firecrawl-py >=4\.46\.2,<5/);
  const example = page.match(/```python\n([\s\S]*?)```/)?.[1];
  assert.ok(example);
  assert.match(example, /from traceai_firecrawl import FirecrawlInstrumentor/);
  assert.match(example, /project_type=ProjectType\.OBSERVE/);
  assert.match(example, /os\.environ\["FIRECRAWL_API_KEY"\]/);
  assert.match(example, /client\.scrape\("https:\/\/example\.com", formats=\["markdown"\]\)/);
  assert.match(example, /client\.search\("OpenTelemetry Python documentation", limit=2\)/);
  assert.ok(example.indexOf('.instrument(') < example.indexOf('client = Firecrawl('));
  assert.match(example, /finally:\n    tracer_provider\.force_flush\(\)\n    tracer_provider\.shutdown\(\)/);
  assert.match(page, /python firecrawl_example\.py/);
  assert.match(page, /Open \*\*Observe\*\*/);
  assert.match(page, /separate root traces/);
});

test('Firecrawl uninstrument disables wrappers held by existing clients', () => {
  assert.match(page, /`FirecrawlInstrumentor\(\)\.uninstrument\(\)` stops tracing subsequent calls, including calls through clients already constructed/);
  assert.match(page, /re-enable instrumentation, construct new clients/);
  assert.doesNotMatch(page, /keep tracing until|remain traced after.*uninstrument/i);
});

test('Firecrawl documents current operation coverage and job error semantics', () => {
  for (const operation of ['extract', 'batch_scrape', 'wait_batch_scrape', 'agent', 'browser_execute']) {
    assert.ok(page.includes('`' + operation + '`'));
  }
  assert.match(page, /`wait_batch_scrape` is async-only/);
  assert.match(page, /one span, not one per page or internal poll/);
  assert.match(page, /successful status poll records the job state without becoming an error itself/);
  assert.match(page, /including `interact` and `parse`, are not instrumented/);
  assert.doesNotMatch(page, /No `agent`/);
});

test('Firecrawl preserves privacy actions and avoids public verification diaries', () => {
  assert.match(page, /Search query text is captured by default/);
  assert.match(page, /FI_HIDE_INPUTS=true/);
  assert.match(page, /does not hide host, format, job or session metadata/);
  assert.match(page, /FI_PII_REDACTION=true/);
  assert.match(page, /browser code or output/);
  assert.match(page, /raw exception text or tracebacks/);
  assert.match(page, /not to separate HTTP instrumentation or your application's logs/);
  assert.doesNotMatch(page, /live vendor verification|fi_verify|168-test|privacy scan|not proven live|Status: beta|fc0dbe7b/i);
});

test('Firecrawl is discoverable through the shared integration catalog', () => {
  const entry = integrations.find(integration => integration.id === 'firecrawl');
  assert.equal(entry?.href, '/docs/integrations/traceai/firecrawl');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'traceAI SDK');
});
