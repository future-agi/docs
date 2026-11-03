import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { integrations } from '../src/lib/integrations.mjs';

const page = fileURLToPath(new URL('../src/pages/docs/integrations/frameworks/scalekit.mdx', import.meta.url));
test('Scalekit tool boundary has a discoverable, privacy-conscious tracing route', () => {
  const entry = integrations.find(({ id }) => id === 'scalekit');
  assert.equal(entry?.href, '/docs/integrations/frameworks/scalekit');
  const source = readFileSync(page, 'utf8');
  assert.match(source, /@scalekit-sdk\/node/);
  assert.match(source, /@traceai\/fi-core/);
  assert.match(source, /AsyncLocalStorageContextManager/);
  assert.match(source, /context\.setGlobalContextManager/);
  assert.match(source, /startActiveSpan/);
  assert.match(source, /fi\.span\.kind.*TOOL/);
  assert.match(source, /response\.data\?\.success === false/);
  assert.match(source, /SpanStatusCode\.ERROR/);
  assert.match(source, /finally\s*\{\s*span\.end\(\)/);
  assert.doesNotMatch(source, /recordException|JSON\.stringify\(response|setAttribute\([^\n]*params/);
});
