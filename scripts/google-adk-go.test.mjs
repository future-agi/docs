import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const page = readFileSync(join(root, 'src/pages/docs/integrations/traceai/go/google-adk.mdx'), 'utf8');
const examples = join(root, 'examples/google-adk-go');

test('customer Go snippets exactly match the runnable major-specific examples', () => {
  const snippets = [...page.matchAll(/```go\n([\s\S]*?)```/g)].map(m => m[1].trim());
  assert.equal(snippets.length, 2);
  for (const [index, major] of ["2-latest", 1].entries()) {
    assert.equal(snippets[index], readFileSync(join(examples, `tests/customer-v${major}/main.go`), 'utf8').trim());
  }
});

test('the documented Collector configuration is the executed privacy profile', () => {
  const config = readFileSync(join(examples, 'collector.yaml'), 'utf8').trim();
  assert.equal(page.match(/```yaml\n([\s\S]*?)```/)[1].trim(), config);
  assert.match(config, /traces_endpoint: https:\/\/api\.futureagi\.com\/tracer\/v1\/traces/);
  assert.match(config, /processors: \[transform\/adk, filter\/events\]/);
  assert.match(config, /error_mode: propagate/);
  assert.match(config, /X-Api-Key: \$\{env:FI_API_KEY\}/);
  assert.match(config, /X-Secret-Key: \$\{env:FI_SECRET_KEY\}/);
});

test('scope and ownership prevent misleading content or duplicate-span instructions', () => {
  assert.match(page, /This configuration excludes prompts, responses and tool payloads/);
  assert.match(page, /instead of replacing it/);
  assert.match(page, /same host/);
  assert.match(page, /SPAN_ONLY/);
  assert.doesNotMatch(page, /telemetry\.New\(|AddLLMAgentCallbacks|BRAINTRUST_OTEL|docker.*:latest/);
});


test('session propagation uses upstream allowlisted baggage rather than a copied processor', () => {
  assert.match(page, /baggagecopy@v0\.16\.2/);
  assert.match(page, /baggagecopy@v0\.17\.0/);
  for (const major of [1, 2]) {
    const source = readFileSync(join(examples, `tests/customer-v${major}/main.go`), 'utf8');
    assert.match(source, /baggagecopy\.NewSpanProcessor/);
    assert.match(source, /return m\.Key\(\) == "adk.session.id"/);
    assert.match(source, /baggage\.FromContext\(ctx\)\.SetMember\(member\)/);
    assert.match(source, /r\.Run\(runCtx, userID, sessionID/);
    assert.doesNotMatch(source, /AllowAllMembers|func .*OnStart/);
  }
});

test('ancestors are sanitized rather than discarded and explicit session IDs win', () => {
  const config = readFileSync(join(examples, 'collector.yaml'), 'utf8');
  assert.doesNotMatch(config, /filter\/adk/);
  assert.match(config, /set\(links, nil\)/);
  assert.match(config, /keep_keys\(attributes, \["session.id", "adk.session.id"\]\)/);
  assert.match(config, /set\(attributes\["session.id"\], attributes\["adk.session.id"\]\) where attributes\["session.id"\] == nil/);
  assert.match(page, /Send all ancestors/);
});
