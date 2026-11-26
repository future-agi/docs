import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/coding-agents/codex-sdk.mdx', import.meta.url), 'utf8');

test('Codex SDK guide uses released packages and the published compatibility floor', () => {
  assert.match(page, /npm install @traceai\/codex-sdk@0\.1\.1 @traceai\/fi-core@1\.1\.1 @openai\/codex-sdk@0\.162\.1/);
  assert.match(page, /0\.162\.1 or later, below 1\.0/);
  assert.doesNotMatch(page, /0\.44\.0|Tested with|read 2026-|verified live|install.from.source/i);
  assert.match(page, /Node\.js 22 or later/);
  assert.match(page, /node codex-tracing\.mjs/);
  assert.match(page, /import \* as CodexSDK from "@openai\/codex-sdk"/);
  assert.match(page, /apiKey: process\.env\.OPENAI_API_KEY/);
  assert.match(page, /finally\s*\{\s*await shutdown\(tracerProvider\)/);
  assert.deepEqual(
    integrations.filter(entry => entry.id === 'codex-sdk').map(({ href, category, method, logo }) => ({ href, category, method, logo })),
    [{ href: '/docs/integrations/coding-agents/codex-sdk', category: 'coding', method: 'traceAI SDK', logo: 'openai' }],
  );
});

test('Codex SDK guide separates ordinary output capture from error-detail capture', () => {
  const privacy = page.split('## Privacy\n')[1]?.split('## Troubleshooting')[0];
  assert.ok(privacy, 'Privacy settings must be documented');
  assert.match(privacy, /`hideInputs`, `hideOutputs`, and `hideErrorDetails` are all `true`/);
  assert.match(privacy, /no `codex\.error\.message`, error status descriptions, exception messages, or stack traces/);
  assert.match(privacy, /does \*\*not\*\* export fixed error summaries/);
  assert.match(privacy, /traceConfig: \{ hideInputs: false, hideOutputs: false, hideErrorDetails: true \}/);
  assert.match(privacy, /Setting `hideOutputs: false` alone does not expose error details/);
  assert.match(privacy, /\*\*both\*\* `hideOutputs: false` and `hideErrorDetails: false`/);
  assert.match(privacy, /both `FI_HIDE_OUTPUTS=false` and `FI_HIDE_ERROR_DETAILS=false`/);
  assert.match(privacy, /`hideErrorDetails: false` but outputs still hidden/);
  assert.match(privacy, /Explicit `traceConfig` options take precedence/);
  assert.match(privacy, /stderr, provider error bodies, exception stack traces, and failed command or MCP output/);
});

test('Codex SDK guide preserves stream lifecycle and usage limitations without a QA diary', () => {
  assert.match(page, /Dropping an iterator partway leaves the turn unexported/);
  assert.match(page, /close it with `break` or `events\.return\(\)`/);
  assert.match(page, /codex\.cancelled=true/);
  assert.match(page, /codex\.usage\.baseline_unknown=true/);
  assert.match(page, /up to 1,000 threads/);
  assert.match(page, /Failed or cancelled turns report no usage/);
  assert.match(page, /The provider label is always `openai`/);
  assert.doesNotMatch(page, /\b(?:verified|measured|test date|QA runner|PASS|FAIL)\b/);
});
