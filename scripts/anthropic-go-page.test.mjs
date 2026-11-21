import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/go/anthropic.mdx', import.meta.url), 'utf8');
const example = page.match(/```go\n([\s\S]*?)\n```/)?.[1];

test('Anthropic Go uses published packages and the module Go minimum', () => {
  assert.match(page, /Go \*\*1\.26\.0 or later\*\*/);
  assert.match(page, /go get github\.com\/future-agi\/traceAI\/go\/anthropic@v0\.1\.0/);
  assert.match(page, /go get github\.com\/anthropics\/anthropic-sdk-go@v1\.82\.0/);
  assert.match(page, /go run github\.com\/future-agi\/traceAI\/go\/anthropic\/example@v0\.1\.0 -model claude-haiku-5-5 -stream -fail -session demo-1/);
  assert.doesNotMatch(page, /@latest|@dev|git clone/);
  assert.ok(example);
});

test('Anthropic Go snippet flushes on API errors and uses stock OTLP', () => {
  assert.match(example, /func main\(\) \{[\s\S]*?if err := run\(\); err != nil/);
  const run = example.slice(example.indexOf('func run()'));
  assert.match(run, /defer func\(\) \{\s*if err := tp\.Shutdown\(context\.Background\(\)\)/);
  assert.doesNotMatch(run, /log\.Fatal|os\.Exit/);
  for (const required of ['X-Api-Key', 'X-Secret-Key', 'project_name', 'project_type', 'otlptracehttp.NoCompression', '/tracer/v1/traces', 'FI_BASE_URL']) {
    assert.ok(example.includes(required), required);
  }
  assert.match(example, /option\.WithMiddleware\(traceaianthropic\.Middleware\(\)\)/);
});

test('Anthropic Go keeps privacy controls and customer-facing wording', () => {
  assert.match(page, /FI_HIDE_INPUTS=true/);
  assert.match(page, /FI_HIDE_OUTPUTS=true/);
  assert.match(page, /Leave `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE` unset/);
  assert.match(page, /error bodies as application content/);
  assert.match(page, /Consume the stream to completion or close it/);
  assert.doesNotMatch(page, /live verification|STANDIN|CLIProxy|not yet been run|2026-10-19|17,102-token/i);
});

test('Anthropic Go is discoverable in the integration catalog', () => {
  const item = integrations.find(i => i.id === 'anthropic-go');
  assert.equal(item?.href, '/docs/integrations/traceai/go/anthropic');
  assert.equal(item?.category, 'providers');
  assert.equal(item?.method, 'traceAI SDK');
});
