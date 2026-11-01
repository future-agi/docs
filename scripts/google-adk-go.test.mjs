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
  for (const [index, major] of [2, 1].entries()) {
    assert.equal(snippets[index], readFileSync(join(examples, `tests/customer-v${major}/main.go`), 'utf8').trim());
  }
});

test('the documented Collector configuration is the executed privacy profile', () => {
  const config = readFileSync(join(examples, 'collector.yaml'), 'utf8').trim();
  assert.equal(page.match(/```yaml\n([\s\S]*?)```/)[1].trim(), config);
  assert.match(config, /traces_endpoint: https:\/\/api\.futureagi\.com\/tracer\/v1\/traces/);
  assert.match(config, /processors: \[filter\/adk, transform\/adk, filter\/events\]/);
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
