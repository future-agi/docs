import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const read = file => readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/traceai/go/gemini.mdx');
const example = read('examples/traceai/gemini-go/main.go');

// Code lines without blank lines or trailing comments, for in-order comparison.
const codeLines = source => source.split('\n')
  .map(line => line.replace(/\s+\/\/ [^"]*$/, '').trim())
  .filter(line => line && !line.startsWith('//'));

test('Gemini Go guide is discoverable and installs the released module', () => {
  const entry = integrations.find(({ id }) => id === 'gemini-go');
  assert.equal(entry?.href, '/docs/integrations/traceai/go/gemini');
  assert.equal(entry.category, 'providers');
  assert.match(page, /go get github\.com\/future-agi\/traceAI\/go\/genai@v0\.1\.1 /);
  assert.match(page, /HTTPClient: traceaigenai\.NewHTTPClient\(/);
  assert.match(page, /otlptracehttp\.NoCompression/);
});

test('Gemini Go setup snippets are excerpts of the example program', () => {
  const blocks = [...page.matchAll(/```go\n([\s\S]*?)```/g)].map(m => m[1]).filter(b => !b.includes('EmbedContent'));
  assert.ok(blocks.length >= 6);
  const lines = codeLines(example);
  for (const block of blocks) {
    let at = 0;
    for (const line of codeLines(block)) {
      at = lines.indexOf(line, at) + 1;
      assert.ok(at > 0, `Snippet line missing from main.go: ${line}`);
    }
  }
});

test('Gemini Go guide matches released embedding, usage and privacy behavior', () => {
  assert.match(page, /Models\.EmbedContent/);
  assert.match(page, /`gen_ai\.span\.kind` = `EMBEDDING`/);
  assert.match(page, /`promptTokenCount` \+ `toolUsePromptTokenCount`/);
  assert.match(page, /reported zero input, output and total counts are kept/);
  assert.match(page, /`FI_HIDE_ERROR_DETAILS`/);
  assert.match(page, /keeps only each function's name/);
  assert.doesNotMatch(page, /embeddings[^.\n]*pass through|never written as 0/);
});

test('Gemini Go custom spans omit content and explain the released privacy boundary', () => {
  assert.doesNotMatch(example, /traceaigenai\.(?:InputValue|OutputValue|InputMimeType|OutputMimeType)|\.SetAttributes\(/);
  assert.match(example, /func runAgent\(/);
  assert.match(example, /func runTool\(/);
  assert.match(example, /agent\.SetStatus\(codes\.Error, "agent failed"\)/);
  assert.match(page, /custom agent and tool spans contain only identity, session and status metadata/);
  assert.match(page, /`TraceConfig\.SetAttributes` does not apply text-only hiding to arbitrary `input\.value` or `output\.value`/);
  assert.match(page, /transport-generated `input\.value` \/ `output\.value`/);
  assert.match(page, /Direct OpenTelemetry attribute writes bypass traceAI filtering/);
});

test('Gemini Go guide and example carry no internal test narration', () => {
  for (const text of [page, read('examples/traceai/gemini-go/README.md'), example]) {
    assert.doesNotMatch(text, /In our test|verified live|Tested surface|latest on 20|trace id[s]? `[0-9a-f]{16}|th8273|MARK_(?:DEFAULT|HIDDEN)|run_e2e/i);
  }
});
